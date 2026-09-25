"""Plugin system for the launcher slash commands; see the Plugin Development docs."""

from __future__ import annotations

import functools
import importlib.util
import inspect
import os
import sys
import threading
from contextlib import suppress
from typing import Any, ClassVar

from fabric.utils import Gio, GLib, logger

from utils.functions import copy_to_clipboard as copy_to_clipboard_fn
from utils.functions import get_http_client
from utils.ttl_cache import CACHE_MISS, TTLCache

# Module-name prefix used when importing plugin files so that a plugin file
# can never shadow a stdlib or third-party module.
_PLUGIN_MODULE_PREFIX = "tsumiki_plugin_"


class PluginResult:
    """A single selectable row rendered in the launcher for a slash command."""

    __slots__ = ("data", "icon", "subtitle", "title")

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        icon: str | None = None,
        data: Any = None,
    ):
        self.title = title
        self.subtitle = subtitle
        self.icon = icon
        self.data = data

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<PluginResult title={self.title!r}>"


class SubprocessResult:
    """Output of :func:`run_subprocess` (like ``subprocess.CompletedProcess``)."""

    __slots__ = ("args", "returncode", "stderr", "stdout")

    def __init__(
        self,
        args: list[str],
        returncode: int,
        stdout: str = "",
        stderr: str = "",
    ):
        self.args = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<SubprocessResult args={self.args!r} returncode={self.returncode}>"


class SubprocessTimeoutError(TimeoutError):
    """Raised when a command run via :func:`run_subprocess` exceeds its timeout."""

    def __init__(self, args: list[str], timeout: float | None):
        super().__init__(f"command timed out after {timeout}s: {args!r}")


def _spawn_subprocess(
    args: list[str],
    *,
    input: str | None = None,
    env: dict | None = None,
) -> Gio.Subprocess:
    """Spawn *args* via :class:`Gio.Subprocess`, surfacing failures as OSError."""
    flags = Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
    if input is not None:
        flags |= Gio.SubprocessFlags.STDIN_PIPE
    try:
        if env:
            launcher = Gio.SubprocessLauncher.new(flags)
            for key, value in env.items():
                launcher.setenv(str(key), str(value), True)
            return launcher.spawnv(list(args))
        return Gio.Subprocess.new(list(args), flags)
    except GLib.Error as exc:
        raise OSError(f"failed to spawn {' '.join(args)}: {exc}") from exc


def _communicate_subprocess(
    proc: Gio.Subprocess,
    args: list[str],
    *,
    input: str | None = None,
    timeout: float | None = None,
) -> SubprocessResult:
    """Wait for *proc* to finish; raises SubprocessTimeoutError on timeout."""
    timed_out = threading.Event()

    def _on_timeout():
        timed_out.set()
        with suppress(Exception):
            proc.force_exit()

    timer = threading.Timer(timeout, _on_timeout) if timeout is not None else None
    if timer is not None:
        timer.start()
    try:
        _, stdout, stderr = proc.communicate_utf8(input, None)
    except GLib.Error as exc:
        raise OSError(f"failed to run {' '.join(args)}: {exc}") from exc
    finally:
        if timer is not None:
            timer.cancel()
    if timed_out.is_set():
        raise SubprocessTimeoutError(args, timeout)
    returncode = (
        -proc.get_term_sig() if proc.get_if_signaled() else proc.get_exit_status()
    )
    return SubprocessResult(args, returncode, stdout or "", stderr or "")


def run_subprocess(
    args: list[str],
    *,
    timeout: float | None = None,
    text: bool = True,
    input: str | None = None,
    env: dict | None = None,
    **kwargs: Any,
) -> SubprocessResult:
    """Gio-based ``subprocess.run`` for plugins; returns a :class:`SubprocessResult`."""
    kwargs.pop("capture_output", None)
    proc = _spawn_subprocess(args, input=input, env=env)
    return _communicate_subprocess(proc, args, input=input, timeout=timeout)


#: Maximum cached entries per plugin before the oldest are evicted.
_CACHE_MAX_ENTRIES = 256

#: Sentinel returned by :meth:`LauncherPlugin.cache_get` on a miss.
_CACHE_MISS = CACHE_MISS


def cached_handle(ttl: float | None = None):
    """Decorator: cache a plugin's ``handle(args)`` results keyed by args.

    On a hit the cached result list is returned without running ``handle``
    again, so repeated lookups (e.g. the same /translate text, /search query
    or /define word) skip the network call. The effective TTL is *ttl* if
    given, else the plugin's ``cache_ttl_seconds`` class attribute;
    ``None`` or ``0`` disables caching.

    A superseded query's empty result is never cached, so a cancelled
    ``handle()`` can't shadow a real result for the same args.
    """

    def decorate(handle):
        @functools.wraps(handle)
        def wrapper(self, args):
            effective_ttl = ttl if ttl is not None else self.cache_ttl_seconds
            if effective_ttl is None or effective_ttl <= 0:
                return handle(self, args)
            value = self.cache_get(args)
            if value is not _CACHE_MISS:
                return value
            value = handle(self, args)
            if not self.is_cancelled():
                self.cache_put(args, value, ttl=effective_ttl)
            return value

        return wrapper

    return decorate


class LauncherPlugin:
    """Base class for slash-command plugins (set ``name`` + ``description``)."""

    name: str = ""
    description: str = ""
    #: GTK icon name (e.g. ``"accessories-calculator-symbolic"``) or a Nerd
    #: Font glyph string. Falls back to the launcher default when unset.
    icon: str | None = None
    #: Extra slash-command names that trigger this plugin.
    aliases: ClassVar[list[str]] = []
    #: Optional per-plugin debounce (ms) before ``handle()`` is dispatched
    #: while typing. ``None`` or ``0`` falls back to the launcher's default
    #: debounce. Set a larger value for expensive plugins (e.g. those that
    #: spawn a subprocess like /calc) to avoid one query per keystroke.
    debounce_ms: int | None = None
    #: Optional session-cache TTL (seconds) for ``handle()`` results, keyed
    #: by query args. ``None`` (or ``0``) disables caching; set it on
    #: network plugins to cache repeat lookups. Combine with the
    #: :func:`cached_handle` decorator, or use :meth:`cache_get` /
    #: :meth:`cache_put` / :meth:`cached` directly for finer control.
    cache_ttl_seconds: float | None = None
    #: When True, the launcher stays open after ``execute()`` (useful for
    #: converters that want to keep showing results). ``execute()`` may also
    #: return True to keep the launcher open.
    keep_open: bool = False

    def __init__(self) -> None:
        self._cancel_event = threading.Event()
        self._subprocess: Gio.Subprocess | None = None
        #: Session cache of ``handle()`` results, keyed by args.
        self._cache = TTLCache(maxsize=_CACHE_MAX_ENTRIES)

    def handle(self, args: str) -> list[PluginResult]:
        """Return result rows for the argument string (runs on a worker thread)."""
        return []

    def execute(self, result: PluginResult | None = None) -> bool:
        """Run when the user activates *result*; True keeps the launcher open."""
        return False

    # -- cancellation -------------------------------------------------

    def cancel(self) -> None:
        """Cancel in-flight ``handle()`` work (flag + force-exit subprocess)."""
        self._cancel_event.set()
        if self._subprocess is not None:
            with suppress(Exception):
                self._subprocess.force_exit()

    def _reset_cancel(self) -> None:
        """Clear the cancellation flag before dispatching a fresh query."""
        self._cancel_event.clear()
        self._subprocess = None

    def is_cancelled(self) -> bool:
        """True when :meth:`cancel` was called since the last dispatch."""
        return self._cancel_event.is_set()

    def run_subprocess(
        self,
        args: list[str],
        *,
        timeout: float | None = None,
        text: bool = True,
        input: str | None = None,
        env: dict | None = None,
        **kwargs: Any,
    ) -> SubprocessResult:
        """Like :func:`run_subprocess` but tracked so :meth:`cancel` can kill it."""
        kwargs.pop("capture_output", None)
        proc = _spawn_subprocess(args, input=input, env=env)
        self._subprocess = proc
        try:
            return _communicate_subprocess(proc, args, input=input, timeout=timeout)
        finally:
            if self._subprocess is proc:
                self._subprocess = None

    def run_http(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json: Any = None,
        headers: dict | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Like :func:`http_request` but aborts when this plugin is cancelled."""
        return http_request(
            self.is_cancelled,
            method,
            url,
            params=params,
            json=json,
            headers=headers,
            timeout=timeout,
        )

    # -- session result cache -------------------------------------------

    def cache_get(self, key: Any) -> Any:
        """Return the cached value for *key*, or ``_CACHE_MISS`` if absent/expired."""
        return self._cache.get(key, _CACHE_MISS)

    def cache_put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        """Store *value* for *key* under the given *ttl* (or ``cache_ttl_seconds``).

        Expired and oldest entries are evicted once the cache grows past
        ``_CACHE_MAX_ENTRIES``. ``None``/``0`` TTL is a no-op.
        """
        if ttl is None:
            ttl = self.cache_ttl_seconds
        self._cache.put(key, value, ttl=ttl)

    def cached(self, key: Any, producer, ttl: float | None = None) -> Any:
        """Return the cached value for *key*, producing and storing it on a miss."""
        if ttl is None:
            ttl = self.cache_ttl_seconds
        return self._cache.get_or_produce(key, producer, ttl=ttl)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<{type(self).__name__} name={self.name!r}>"


class PluginCancelledError(RuntimeError):
    """Raised when a superseded query aborts an in-flight plugin operation.

    ``handle()`` should catch it and return an empty list (no results to
    show) rather than surfacing it as an error row.
    """


def _materialize_response(response, content: bytes) -> Any:
    """Rebuild a fully-read ``httpx.Response`` from a streamed one."""
    import httpx

    return httpx.Response(
        status_code=response.status_code,
        headers=response.headers,
        content=content,
        request=response.request,
        extensions=response.extensions,
    )


def http_request(
    cancelled,
    method: str,
    url: str,
    *,
    params: dict | None = None,
    json: Any = None,
    headers: dict | None = None,
    timeout: float | None = None,
) -> Any:
    """Run an HTTP request that aborts as soon as *cancelled()* is true.

    The response body is streamed in chunks, so a superseded query stops
    downloading and parsing immediately instead of running to completion
    and being discarded. Returns a fully-read ``httpx.Response`` — ``.text``,
    ``.json()`` and ``.raise_for_status()`` behave as usual. Raises the
    normal httpx exceptions on failure and :class:`PluginCancelledError`
    when the query was superseded mid-flight.

    *cancelled* is a zero-arg callable returning a truthy value when the
    query has been superseded; pass ``None`` for fire-and-forget requests.
    """
    if cancelled is not None and cancelled():
        raise PluginCancelledError()
    client = get_http_client()
    with client.stream(
        method,
        url,
        params=params,
        json=json,
        headers=headers,
        timeout=timeout,
    ) as response:
        if cancelled is not None and cancelled():
            raise PluginCancelledError()
        chunks = []
        for chunk in response.iter_bytes():
            if cancelled is not None and cancelled():
                raise PluginCancelledError()
            chunks.append(chunk)
    return _materialize_response(response, b"".join(chunks))


# Re-exported for the plugin API: plugins (including out-of-tree ones) import
# the clipboard helper from here, but it is not plugin infrastructure - the
# implementation lives with the other shared helpers.
copy_to_clipboard = copy_to_clipboard_fn


class PluginManager:
    """Loads launcher plugins from a directory and registers their commands."""

    def __init__(
        self,
        plugins_dir: str,
        plugin_names: list[str] | None = None,
    ):
        self.plugins_dir = os.path.expanduser(plugins_dir)
        #: Allowlist of plugin names to load (case-insensitive, whitespace
        #: trimmed). ``None`` loads every discovered plugin; an empty list
        #: loads none.
        self._plugin_names = (
            {name.strip().casefold() for name in plugin_names if name and name.strip()}
            if plugin_names is not None
            else None
        )
        self._plugins: dict[str, LauncherPlugin] = {}
        self._instances: list[LauncherPlugin] = []

    # -- discovery ----------------------------------------------------

    def load(self) -> int:
        """Discover and load plugins; returns the number of registered commands."""
        self._plugins.clear()
        self._instances.clear()

        if not os.path.isdir(self.plugins_dir):
            logger.info(
                f"[LauncherPlugin] Plugins directory "
                f"'{self.plugins_dir}' not found, no slash commands loaded"
            )
            self._warn_unknown_allowlist_entries()
            return 0

        count = 0
        for path in sorted(os.listdir(self.plugins_dir)):
            full_path = os.path.join(self.plugins_dir, path)
            module_name: str | None = None
            try:
                if path.endswith(".py") and not path.startswith("_"):
                    module_name = self._import_file(full_path)
                elif os.path.isdir(full_path) and os.path.exists(
                    os.path.join(full_path, "__init__.py")
                ):
                    module_name = self._import_package(full_path, path)
                else:
                    continue
            except Exception as exc:
                logger.exception(
                    f"[LauncherPlugin] Failed to load plugin '{path}': {exc}"
                )
                continue

            if module_name:
                count += self._register_from_module(module_name, path)

        self._warn_unknown_allowlist_entries()
        logger.info(
            f"[LauncherPlugin] Loaded {count} slash command(s) from {self.plugins_dir}"
        )
        return count

    def _warn_unknown_allowlist_entries(self) -> None:
        """Warn about ``plugins`` names that matched no loaded plugin."""
        if self._plugin_names is None:
            return
        registered = {plugin.name.casefold() for plugin in self._instances}
        missing = sorted(self._plugin_names - registered)
        if missing:
            logger.warning(
                "[LauncherPlugin] plugins listed in launcher config were not "
                f"found: {', '.join(missing)}"
            )

    def _import_file(self, path: str) -> str | None:
        """Import a single-file plugin under a unique synthetic module name."""
        stem = os.path.splitext(os.path.basename(path))[0]
        module_name = f"{_PLUGIN_MODULE_PREFIX}{stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module_name

    def _import_package(self, path: str, dirname: str) -> str | None:
        """Import a package plugin (dir with __init__.py) with relative imports."""
        module_name = f"{_PLUGIN_MODULE_PREFIX}{dirname}"
        init_path = os.path.join(path, "__init__.py")
        spec = importlib.util.spec_from_file_location(module_name, init_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module_name

    # -- registration -------------------------------------------------

    def _register_from_module(self, module_name: str, source: str) -> int:
        """Register every LauncherPlugin subclass exposed by the module."""
        module = sys.modules.get(module_name)
        if module is None:
            return 0
        count = 0
        for attr in vars(module).values():
            if (
                inspect.isclass(attr)
                and issubclass(attr, LauncherPlugin)
                and attr is not LauncherPlugin
                and not inspect.isabstract(attr)
                and self._register(attr, source)
            ):
                count += 1
        return count

    def _register(self, plugin_cls: type, source: str) -> bool:
        """Instantiate a plugin and register it under its name + aliases."""
        if (
            self._plugin_names is not None
            and plugin_cls.name
            and plugin_cls.name.casefold() not in self._plugin_names
        ):
            logger.info(
                f"[LauncherPlugin] Plugin '{plugin_cls.name}' in {source} is not "
                f"in launcher config plugins allowlist — skipped"
            )
            return False

        try:
            instance = plugin_cls()
        except Exception as exc:
            logger.exception(
                f"[LauncherPlugin] Failed to instantiate "
                f"{plugin_cls.__name__} from {source}: {exc}"
            )
            return False

        if not instance.name:
            logger.warning(
                f"[LauncherPlugin] Plugin {plugin_cls.__name__} in {source} "
                f"has no name — skipped"
            )
            return False

        if (
            self._plugin_names is not None
            and instance.name.casefold() not in self._plugin_names
        ):
            logger.info(
                f"[LauncherPlugin] Plugin '{instance.name}' in {source} is not "
                f"in launcher config plugins allowlist — skipped"
            )
            return False

        keys = [instance.name.casefold()] + [
            alias.casefold() for alias in instance.aliases
        ]
        for key in keys:
            if key in self._plugins:
                logger.warning(
                    f"[LauncherPlugin] Duplicate slash command '/{key}' "
                    f"from {source} — keeping the first registration"
                )
                continue
            self._plugins[key] = instance
        self._instances.append(instance)
        return True

    # -- lookup -------------------------------------------------------

    def get(self, command: str) -> LauncherPlugin | None:
        """Return the plugin registered for *command* (case-insensitive)."""
        return self._plugins.get(command.casefold())

    def all(self) -> list[LauncherPlugin]:
        """Return all loaded plugins, sorted by command name."""
        return sorted(self._instances, key=lambda plugin: plugin.name)

    def match(self, prefix: str) -> list[LauncherPlugin]:
        """Return plugins whose command or alias starts with *prefix*."""
        prefix = prefix.casefold()
        matched: set[LauncherPlugin] = set()
        for key, plugin in self._plugins.items():
            if key.startswith(prefix):
                matched.add(plugin)
        return sorted(matched, key=lambda plugin: plugin.name)


_manager: PluginManager | None = None
_manager_dir: str = ""
_manager_names: frozenset[str] | None = None


def get_plugin_manager(
    plugins_dir: str,
    plugin_names: list[str] | None = None,
) -> PluginManager:
    """Return a cached :class:`PluginManager`, reloading when config changes."""
    global _manager, _manager_dir, _manager_names
    plugins_dir = os.path.expanduser(plugins_dir)
    names = (
        frozenset(
            name.strip().casefold() for name in plugin_names if name and name.strip()
        )
        if plugin_names is not None
        else None
    )
    if _manager is None or _manager_dir != plugins_dir or _manager_names != names:
        _manager = PluginManager(plugins_dir, plugin_names)
        _manager.load()
        _manager_dir = plugins_dir
        _manager_names = names
    return _manager
