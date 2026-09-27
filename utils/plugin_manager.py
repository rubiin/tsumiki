"""Plugin system for the launcher slash commands; see the Plugin Development docs."""

from __future__ import annotations

import functools
import importlib.util
import inspect
import os
import signal
import subprocess
import sys
import threading
from contextlib import suppress
from typing import Any, ClassVar

from fabric.utils import logger

from utils.functions import copy_to_clipboard as copy_to_clipboard_fn
from utils.functions import get_http_client
from utils.ttl_cache import CACHE_MISS, TTLCache

# Prefix for imported plugin modules so a plugin file cannot shadow a stdlib one.
_PLUGIN_MODULE_PREFIX = "tsumiki_plugin_"

#: Grace period for reaping a killed process; the group is already gone, this
#: only bounds how long we wait for the direct child to be collected.
_REAP_TIMEOUT_SECONDS = 1.0


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
        stdout: str | bytes = "",
        stderr: str | bytes = "",
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


def _kill_process_group(proc: subprocess.Popen) -> None:
    """SIGKILL the group the child leads, grandchild processes included.

    Killing only the direct child leaves anything that inherited the output pipe
    holding it open, and the caller's read would block forever.
    """
    with suppress(OSError):
        os.killpg(proc.pid, signal.SIGKILL)


def _spawn_subprocess(
    args: list[str],
    *,
    input: str | None = None,
    env: dict | None = None,
) -> subprocess.Popen:
    """Spawn *args* as the leader of a new session, surfacing failures as OSError.

    The new session is what makes :func:`_kill_process_group` safe: without it
    the child shares this process's group and a timeout would kill the bar.
    """
    try:
        return subprocess.Popen(
            list(args),
            stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
    except OSError as exc:
        raise OSError(f"failed to spawn {' '.join(args)}: {exc}") from exc


def _communicate_subprocess(
    proc: subprocess.Popen,
    args: list[str],
    *,
    input: str | None = None,
    timeout: float | None = None,
    text: bool = True,
) -> SubprocessResult:
    """Wait for *proc* to finish; raises SubprocessTimeoutError on timeout."""
    stdout: bytes = b""
    stderr: bytes = b""
    timed_out = False
    try:
        stdout, stderr = proc.communicate(input, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_process_group(proc)
        # The group is gone, so this only collects the child; bound it anyway.
        with suppress(subprocess.TimeoutExpired, OSError, ValueError):
            stdout, stderr = proc.communicate(timeout=_REAP_TIMEOUT_SECONDS)
        with suppress(subprocess.TimeoutExpired, OSError):
            proc.wait(timeout=_REAP_TIMEOUT_SECONDS)
    if timed_out:
        raise SubprocessTimeoutError(args, timeout)
    if text:
        return SubprocessResult(
            args,
            proc.returncode,
            stdout.decode("utf-8", "replace"),
            stderr.decode("utf-8", "replace"),
        )
    return SubprocessResult(args, proc.returncode, stdout, stderr)


def run_subprocess(
    args: list[str],
    *,
    timeout: float | None = None,
    text: bool = True,
    input: str | None = None,
    env: dict | None = None,
    capture_output: bool = True,
) -> SubprocessResult:
    """``subprocess.run`` for plugins; returns a :class:`SubprocessResult`.

    ``capture_output`` and ``text`` are accepted for call compatibility with
    ``subprocess.run``: output is always captured, and ``text=False`` returns it
    as bytes. Any other keyword is a TypeError rather than a silent no-op.
    """
    del capture_output
    proc = _spawn_subprocess(args, input=input, env=env)
    return _communicate_subprocess(proc, args, input=input, timeout=timeout, text=text)


#: Maximum cached entries per plugin before the oldest are evicted.
_CACHE_MAX_ENTRIES = 256

#: Sentinel returned by :meth:`LauncherPlugin.cache_get` on a miss.
_CACHE_MISS = CACHE_MISS


def cached_handle(ttl: float | None = None):
    """Decorator: cache a plugin's ``handle(args)`` results keyed by args.

    TTL is *ttl*, else ``cache_ttl_seconds``; a cancelled result is never
    cached, so it cannot shadow a real one.
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
    #: GTK icon name (e.g. ``"accessories-calculator-symbolic"``) or a Nerd Font glyph.
    icon: str | None = None
    #: Extra slash-command names that trigger this plugin.
    aliases: ClassVar[list[str]] = []
    #: Debounce (ms) before ``handle()`` dispatches; ``None``/``0`` means default.
    debounce_ms: int | None = None
    #: Session-cache TTL (seconds) for ``handle()``; ``None``/``0`` disables it.
    cache_ttl_seconds: float | None = None
    #: Keep the launcher open after ``execute()``.
    keep_open: bool = False

    def __init__(self) -> None:
        self._cancel_event = threading.Event()
        self._subprocess: subprocess.Popen | None = None
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
        """Cancel in-flight ``handle()`` work (flag + kill the tracked process)."""
        self._cancel_event.set()
        if self._subprocess is not None:
            _kill_process_group(self._subprocess)

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
        capture_output: bool = True,
    ) -> SubprocessResult:
        """Like :func:`run_subprocess` but tracked so :meth:`cancel` can kill it."""
        del capture_output
        proc = _spawn_subprocess(args, input=input, env=env)
        self._subprocess = proc
        try:
            return _communicate_subprocess(
                proc, args, input=input, timeout=timeout, text=text
            )
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
        """Store *value* for *key* under *ttl* (or ``cache_ttl_seconds``)."""
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
    """A superseded query aborted the plugin; ``handle()`` should return []."""


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

    The body is streamed in chunks so a superseded query stops downloading at
    once. Pass ``None`` for *cancelled* when no cancellation is possible.
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


# Re-exported for plugins (including out-of-tree ones), but not plugin infrastructure.
copy_to_clipboard = copy_to_clipboard_fn


class PluginManager:
    """Loads launcher plugins from a directory and registers their commands."""

    def __init__(
        self,
        plugins_dir: str,
        plugin_names: list[str] | None = None,
    ):
        self.plugins_dir = os.path.expanduser(plugins_dir)
        #: Allowlist of plugin names (case-insensitive, trimmed); ``None`` loads all.
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
