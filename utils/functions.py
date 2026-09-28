import atexit
import contextlib
import copy
import ctypes
import html
import importlib
import json
import re
import shlex
import shutil
import tempfile
import threading
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from functools import lru_cache
from typing import Any, Callable, Literal, Optional

import gi
from fabric.hyprland import HyprlandReply
from fabric.utils import (
    Gio,
    GLib,
    Gtk,
    cooldown,
    exec_shell_command_async,
    get_relative_path,
    idle_add,
    logger,
    os,
    time,
)

from .colors import Colors
from .constants import (
    BYTES_FACTORS,
    HEX_COLOR_RE,
    NAMED_COLORS,
    RGB_RE,
    RGBA_RE,
    TEMP_PATHS,
    URGENCY_LEVELS,
)
from .decorators import run_in_thread, thread
from .exceptions import ExecutableNotFoundError
from .icons import get_text_icon
from .ttl_cache import TTLCache

gi.require_version("Pango", "1.0")
from gi.repository import Pango  # noqa: E402

# Formatting tags re-enabled by ``parse_markup`` after escaping (SwayNC-inspired).
_ALLOWED_MARKUP_TAGS_RE = re.compile(r"&lt;(/?(?:b|i|u))&gt;")
# Double-escaped entities some apps send (e.g. Discord escapes "<" itself).
_DOUBLE_ESCAPED_ENTITIES_RE = re.compile(
    r"&amp;(lt;|gt;|amp;|apos;|quot;|#60;|#x3C;|#x3c;|#62;|#x3E;|#x3e;|#39;|#34;)"
)
# One-time codes (2FA / OTP) in notification bodies, with Google's "G-" prefix allowed.
_ONE_TIME_CODE_RE = re.compile(
    r"(?:^|(?<=\s))(?:G-)?(\d{3}[- ]\d{3}|\d{4,8})(?=$|[\s.,])"
)
# ``<img src="...">`` tags embedded in notification bodies.
_BODY_IMAGE_TAG_RE = re.compile(r"<img[^>]*\ssrc=(\"([^\"]*)\"|'([^']*)')[^>]*>")
# Residual markup tags (e.g. <b>) stripped before one-time code extraction.
_MARKUP_TAG_RE = re.compile(r"<[^>]+>")


def register_temp_resource(path: str):
    TEMP_PATHS.add(path)


def expand_env(value: str | None) -> str:
    if not value:
        return ""
    return os.path.expanduser(os.path.expandvars(value))


def normalize_address(address: str | None) -> str | None:
    if not address:
        return None
    return address if address.startswith("0x") else f"0x{address}"


def cleanup_temp_resources():
    """Remove all registered temp files/directories."""
    for path in list(TEMP_PATHS):
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            elif os.path.isfile(path):
                os.remove(path)
            TEMP_PATHS.remove(path)
        except Exception as e:
            logger.warning(f"Failed to cleanup temp resource {path}: {e}")


atexit.register(cleanup_temp_resources)

# dlopen'd once: the library handle is stable for the process lifetime.
_LIBC = ctypes.CDLL("libc.so.6")
_PR_SET_NAME = 15


def set_process_name(name: str):
    _LIBC.prctl(_PR_SET_NAME, name.encode("utf-8"), 0, 0, 0)


def _pillow_worker(image_path, callback, color_count, resize):
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            img = img.convert("RGB")
            img.thumbnail((resize, resize), Image.LANCZOS)  # Fast, in-place resize
            pixels = img.getdata()

            most_common = Counter(pixels).most_common(color_count)
            palette = [color for color, _ in most_common]

            idle_add(callback, palette)
    except (ImportError, OSError, ValueError, TypeError) as e:
        logger.exception(f"Error generating color palette: {e}")
        idle_add(callback, None)


def get_simple_palette_threaded(
    image_path: str,
    callback: Callable[[Optional[list[tuple[int, int, int]]]], None],
    color_count: int = 4,
    resize: int = 64,
):
    thread(_pillow_worker, image_path, callback, color_count, resize)


def parse_markup(text: str) -> str:
    """Escape *text* for Pango, re-enabling only the whitelisted b/i/u tags.

    Falls back to fully-escaped output when the result does not parse, so a
    malformed body can never break rendering.
    """
    escaped = html.escape(text.replace("\n", " "))
    # Whitelisted tags survive escaping as entities; undo double-escaping too (Discord).
    candidate = _ALLOWED_MARKUP_TAGS_RE.sub(r"<\1>", escaped)
    candidate = _DOUBLE_ESCAPED_ENTITIES_RE.sub(r"&\1", candidate)
    if candidate == escaped:
        return escaped
    try:
        Pango.parse_markup(candidate, -1, "\0")
    except GLib.Error:
        return escaped
    return candidate


def extract_one_time_code(text: str) -> str | None:
    """Return the first 2FA code in *text* (digits only), or ``None``.

    Matches 4-8 digit codes and ``123-456``/``123 456`` pairs plus Google's
    ``G-123456`` form, ready for pasting into OTP fields.
    """
    if not text:
        return None
    # Strip residual markup tags so codes wrapped in e.g. <b>...</b> are found.
    text = _MARKUP_TAG_RE.sub("", text)
    match = _ONE_TIME_CODE_RE.search(text)
    if not match:
        return None
    return "".join(c for c in match.group(1) if c.isdigit()) or None


def extract_body_image(text: str) -> tuple[str, str | None]:
    """Strip ``<img src=...>`` tags, returning (cleaned text, first src).

    The source is unresolved; expand and stat it at the call site.
    """
    if not text or "<img" not in text:
        return text, None
    match = _BODY_IMAGE_TAG_RE.search(text)
    cleaned = _BODY_IMAGE_TAG_RE.sub("", text)
    if not match:
        return cleaned, None
    src = (match.group(2) or match.group(3) or "").strip()
    return cleaned, src or None


def format_relative_timestamp(ts: float | None) -> str:
    """Format a timestamp as "Now"/"5m ago"/"2h ago"/"3d ago".

    Takes seconds or milliseconds; missing or invalid input yields "".
    """
    if ts is None:
        return ""
    try:
        ts_value = float(ts)
        if ts_value > 1e12:  # already in milliseconds
            ts_value /= 1000.0
        diff = time.time() - ts_value
        if diff < 60:
            return "Now"
        if diff < 3600:
            return f"{int(diff / 60)}m ago"
        if diff < 86400:
            return f"{int(diff / 3600)}h ago"
        return f"{int(diff / 86400)}d ago"
    except (TypeError, ValueError, OSError, OverflowError):
        logger.warning(f"Failed to format relative timestamp for {ts!r}")
        return ""


def _clipboard_argv() -> list[str] | None:
    """Return the argv of the first available clipboard tool, or None."""
    if find_executable("wl-copy"):
        return ["wl-copy", "--type", "text/plain"]
    if find_executable("xclip"):
        return ["xclip", "-selection", "clipboard"]
    return None


def copy_to_clipboard(text: str, *, asynchronous: bool = False) -> bool:
    """Copy *text* to the clipboard (wl-copy, else xclip).

    Synchronous by default reports the real outcome; *asynchronous* only says
    the copy was dispatched. Failures are logged, never raised.
    """
    argv = _clipboard_argv()
    if argv is None:
        logger.warning("[CLIPBOARD] No clipboard tool (wl-copy/xclip) found")
        return False

    try:
        launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.STDIN_PIPE)
        proc = launcher.spawnv(argv)
        if asynchronous:
            proc.communicate_utf8_async(text or "", None, _on_clipboard_copy_finished)
        else:
            proc.communicate_utf8(text or "", None)
        return True
    except Exception:
        logger.exception("[CLIPBOARD] Failed to copy to clipboard")
        return False


def _on_clipboard_copy_finished(proc: Gio.Subprocess, result: Gio.AsyncResult):
    try:
        proc.communicate_utf8_finish(result)
    except Exception as e:
        logger.warning(f"[CLIPBOARD] Copy failed: {e}")


def read_json_file(file_path: str) -> Optional[dict | list]:
    if not os.path.exists(file_path):
        logger.warning(f"JSON file {file_path} does not exist.")
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError) as e:
        logger.exception(f"Failed to read JSON file {file_path}: {e}")
        return None


def read_toml_file(file_path: str) -> Optional[dict]:
    import pytomlpp as toml

    if not os.path.exists(file_path):
        logger.warning(f"TOML file {file_path} does not exist.")
        return None

    logger.info(f"[Config] Reading TOML config from {file_path}")
    try:
        with open(file_path, "r") as file:
            return toml.load(file)
    except (IOError, OSError, ValueError, KeyError, TypeError) as e:
        logger.exception(f"Failed to read TOML file {file_path}: {e}")
        return None


def _atomic_write(path: str, dump: Callable[[Any], None]) -> None:
    """Dump via a temp file beside *path*, then rename it into place.

    Keeps the old file intact if the dump raises, so config and caches are
    never left truncated.
    """
    directory = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tsumiki-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            dump(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def write_toml_file(path: str, data: dict, *, sync: bool = False):
    """Write TOML off-thread by default, or inline when *sync* is true."""
    import pytomlpp as toml

    if not sync:
        return thread(write_toml_file, path, data, sync=True)

    try:
        _atomic_write(path, lambda handle: toml.dump(data, handle))
    except (IOError, OSError, ValueError, KeyError, TypeError) as e:
        logger.exception(f"Failed to write toml: {e}")
        return None


def ttl_lru_cache(seconds_to_live: int, maxsize: int = 128):
    def wrapper(func):
        @lru_cache(maxsize)
        def inner(__ttl, *args, **kwargs):
            return func(*args, **kwargs)

        return lambda *args, **kwargs: inner(
            time.time() // seconds_to_live, *args, **kwargs
        )

    return wrapper


def parse_hyprland_reply(reply: HyprlandReply) -> dict:
    try:
        return json.loads(reply.reply.decode().strip("\n"))
    except (
        json.JSONDecodeError,
        AttributeError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
    ) as e:
        logger.exception(f"Failed to parse hyprland reply: {e}")
        return {}


# Without this lock, a concurrent second update reverts the first one.
_config_write_lock = threading.Lock()


def _absorb_own_config_write(config_file: str) -> None:
    """Tell the config watcher that this write is ours, not an external edit.

    Imported lazily: config_watcher imports us, so a module-level import
    would be circular.
    """
    from utils.config_watcher import _watcher

    if _watcher is not None:
        _watcher.note_self_write(config_file)


def _update_config_key(key_path: list[str], value: Any) -> None:
    """Update a single key in config.toml under a lock, without truncating it."""
    config_file = get_relative_path("../config.toml")
    with _config_write_lock:
        try:
            config = read_toml_file(config_file)
            if config is None:
                return

            node = config
            for k in key_path[:-1]:
                node = node.setdefault(k, {})
            # Rewriting an identical value costs a read, an fsync and a
            # spurious config-change event for no change at all.
            if node.get(key_path[-1]) == value:
                return
            node[key_path[-1]] = value

            write_toml_file(config_file, config, sync=True)
            _absorb_own_config_write(config_file)
        except (IOError, OSError, ValueError, KeyError, TypeError) as e:
            logger.exception(
                f"{Colors.ERROR}[Config] Error updating {'.'.join(key_path)}: {e}"
            )


def update_theme_config(theme_name: str):
    """Update the config.toml file with the new theme name."""
    _update_config_key(["styling", "theme_name"], theme_name)
    logger.info(f"{Colors.INFO}[Theme] Updated theme config to {theme_name}")


def update_styling_mode(mode: str):
    """Update the config.toml file with the new styling mode."""
    _update_config_key(["styling", "mode"], mode)
    logger.info(f"{Colors.INFO}[Theme] Updated styling mode to {mode}")


def celsius_to_fahrenheit(celsius: float) -> float:
    return (celsius * 9 / 5) + 32


def deep_merge(data: dict, target: dict) -> dict:
    """Recursively merge *data* over *target*.

    Inherited values are deep-copied, so a widget that mutates a config list
    in place cannot rewrite the shared defaults for the rest of the process.
    """
    merged = {key: copy.deepcopy(value) for key, value in target.items()}
    for key, user_value in data.items():
        if (
            key in target
            and isinstance(target[key], dict)
            and isinstance(user_value, dict)
        ):
            merged[key] = deep_merge(user_value, target[key])
        else:
            merged[key] = user_value
    return merged


def flatten_dict(d: dict, parent_key: str = "", sep: str = "-") -> dict:
    """Flatten a nested dictionary into a single level."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def exclude_keys(d: dict, keys_to_exclude: list[str]) -> dict:
    return {k: v for k, v in d.items() if k not in keys_to_exclude}


def format_seconds_to_hours_minutes(secs: int) -> str:
    mm, _ = divmod(secs, 60)
    hh, mm = divmod(mm, 60)
    return "%d h %02d min" % (hh, mm)


def convert_bytes(
    bytes: int, to: Literal["kb", "mb", "gb", "tb"], format_spec=".1f"
) -> str:
    factor = BYTES_FACTORS.get(to, 1)
    return f"{format(bytes / (1024**factor), format_spec)}{to.upper()}"


def _parse_time(value: str | None, time_format: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, time_format)
    except ValueError:
        return None


def check_if_day(
    sunrise_time: str | None,
    sunset_time: str | None,
    current_time: str | None = None,
    time_format: str = "%I:%M %p",
) -> bool:
    """Whether *current_time* falls between sunrise and sunset.

    Providers omit the daily sunrise/sunset when they have no forecast for the
    site, and the empty string must not raise out of the weather signal handler.
    """
    sunrise_time_obj = _parse_time(sunrise_time, time_format)
    sunset_time_obj = _parse_time(sunset_time, time_format)
    if sunrise_time_obj is None or sunset_time_obj is None:
        return False

    if current_time is None:
        current_time_obj = datetime.now()
    else:
        current_time_obj = _parse_time(current_time, time_format)
        if current_time_obj is None:
            return False

    if sunrise_time_obj <= sunset_time_obj:
        return sunrise_time_obj <= current_time_obj < sunset_time_obj

    return current_time_obj >= sunrise_time_obj or current_time_obj < sunset_time_obj


# wttr.in reports times as "HHMM" (e.g. "1200"); accept "HH:MM" too (Open-Meteo).
def convert_to_12hr_format(time: str) -> str:
    if not time:
        return time or ""

    if ":" in str(time):
        try:
            hour, minute = map(int, str(time).split(":"))
        except (ValueError, IndexError):
            return str(time)
    else:
        time_int = int(time)
        hour = time_int // 100
        minute = time_int % 100

    period = "AM" if hour < 12 else "PM"

    if hour == 0:
        hour = 12
    elif hour > 12:
        hour -= 12

    return f"{hour}:{minute:02d} {period}"


def unique_list(lst: list[Any]) -> list[Any]:
    """Return a list with unique elements."""
    return list(set(lst))


def convert_to_percent(
    current: int | float, max: int | float, is_int=True
) -> int | float:
    if max == 0:
        return 0
    if is_int:
        return int((current / max) * 100)
    else:
        return (current / max) * 100


def is_valid_gjs_color(color: str) -> bool:
    color_lower = color.strip().lower()

    if color_lower in NAMED_COLORS:
        return True

    if HEX_COLOR_RE.match(color_lower):
        return True

    return bool(RGB_RE.match(color_lower) or RGBA_RE.match(color_lower))


def convert_seconds_to_milliseconds(seconds: int) -> int:
    return seconds * 1000


def spawn_detached(argv: Sequence[str], cwd: str | None = None) -> None:
    """Spawn *argv* fire-and-forget in its own session, output to /dev/null.

    The separate session matters: callers use this for work that must outlive
    this process, e.g. the restart the config watcher triggers.
    """
    argv = list(argv)
    # setsid gives the child its own session so this process exiting cannot signal it.
    if find_executable("setsid"):
        argv.insert(0, "setsid")
    launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.NONE)
    if cwd:
        launcher.set_cwd(cwd)
    for stream in ("stdin", "stdout", "stderr"):
        getattr(launcher, f"set_{stream}_file_path")("/dev/null")
    launcher.spawnv(argv)


def toggle_command(command: str, full_command: str):
    full_command = full_command.strip(" ")
    if is_app_running(command):
        kill_process(command)
    else:
        spawn_detached(shlex.split(full_command))
    # The button re-reads its state right after this, so the snapshot would
    # answer with the state from before the toggle.
    invalidate_process_names()


def char_limit_to_px(label_widget, char_limit: int) -> int:
    n = max(1, int(char_limit))
    sample = "M" * n  # conservative (wide) mapping
    layout = label_widget.create_pango_layout(sample)
    style = label_widget.get_style_context()
    layout.set_font_description(style.get_font(Gtk.StateFlags.NORMAL))
    px, _ = layout.get_pixel_size()
    return px


def kill_process(process_name: str):
    # argv, not a shell string, and "--" so a leading-dash name is not an option.
    exec_shell_command_async(["pkill", "--", process_name])


def lazy_load_class(module_name: str, class_name: str):
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


@cooldown(1)
def play_sound(file: str):
    # A list, not a shell string: the sound path is user-configured.
    exec_shell_command_async(["pw-play", file])


@ttl_lru_cache(600, 10)
def get_distro_icon() -> str:
    distro_id = GLib.get_os_info("ID")

    return get_text_icon(f"distro.{distro_id}", "") or ""


def check_executable_exists(executable_name):
    """Raise ``ExecutableNotFoundError`` if *executable_name* is not on PATH.

    The lookup goes through ``find_executable``, which is TTL-cached: lru_cache
    does not memoize exceptions, so raising directly from a cached function meant
    a missing binary re-scanned PATH on every single call.
    """
    if not find_executable(executable_name):
        raise ExecutableNotFoundError(executable_name)


@ttl_lru_cache(600, 64)
def find_executable(executable_name: str) -> str | None:
    """Return the absolute path of *executable_name*, or None if not found.

    TTL-cached so plugins probing for a required tool do not re-scan PATH.
    """
    return GLib.find_program_in_path(executable_name)


@cooldown(1)
def send_notification(
    title: str,
    body: str,
    urgency: Literal["low", "normal", "critical"] = "normal",
    icon: Optional[str] = None,
    app_name: str = "Application",
):
    notification = Gio.Notification.new(title)
    notification.set_body(body)

    if urgency in URGENCY_LEVELS:
        notification.set_urgent(urgency == "critical")

    if icon:
        notification.set_icon(Gio.ThemedIcon.new(icon))

    notification.set_title(app_name)

    application = Gio.Application.get_default()

    application.send_notification(None, notification)
    return True


def write_json_file(path: str, data: dict | list, *, sync: bool = False):
    """Write JSON off-thread by default, or inline when *sync* is true.

    Failures are logged, never raised, so a worker thread cannot be wedged by
    an unwritable path.
    """
    if not sync:
        return thread(write_json_file, path, data, sync=True)

    try:
        _atomic_write(
            path, lambda handle: json.dump(data, handle, indent=4, ensure_ascii=False)
        )
    except (IOError, OSError, TypeError) as e:
        logger.exception(f"Failed to write json: {e}")


@run_in_thread
def ensure_file(path: str):
    file = Gio.File.new_for_path(path)
    parent = file.get_parent()

    try:
        if parent and not parent.query_exists(None):
            parent.make_directory_with_parents(None)

        if not file.query_exists(None):
            file.create(Gio.FileCreateFlags.NONE, None)
    except GLib.Error as e:
        logger.exception(f"Failed to ensure file '{path}': {e.message}")


def ensure_directory(path: str, *, sync: bool = False):
    """Create *path* and its parents; off-thread unless *sync*.

    A caller about to write into the directory must pass ``sync=True`` or it
    can race the mkdir.
    """
    if not sync:
        return thread(ensure_directory, path, sync=True)

    if not GLib.file_test(path, GLib.FileTest.EXISTS):
        try:
            Gio.File.new_for_path(path).make_directory_with_parents(None)
        except GLib.Error as e:
            logger.exception(f"Failed to create directory {path}: {e.message}")


class CommandError(RuntimeError):
    """A command failed with ``check=True``; *kind* is missing/timeout/failed."""

    def __init__(
        self,
        cmd: str | Sequence[str],
        message: str,
        *,
        kind: str = "failed",
        returncode: int | None = None,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.cmd = cmd
        self.kind = kind
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _spawn_and_wait(
    cmd: str | Sequence[str], timeout: float | None
) -> tuple[int | None, str, str, str | None]:
    """Run *cmd* to completion, returning ``(returncode, stdout, stderr, kind)``.

    A *kind* of timeout/missing means there is no usable returncode.
    """
    argv = shlex.split(cmd) if isinstance(cmd, str) else list(cmd)
    try:
        process = Gio.Subprocess.new(
            argv,
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
        )
    except GLib.Error as e:
        return None, "", str(e), "missing"

    timed_out = False

    def kill() -> None:
        nonlocal timed_out
        timed_out = True
        with contextlib.suppress(GLib.Error):
            process.force_exit()

    # A GLib timeout cannot fire while this thread blocks, so the watchdog is a thread.
    watchdog = threading.Timer(timeout, kill) if timeout else None
    if watchdog is not None:
        watchdog.daemon = True
        watchdog.start()
    try:
        _, stdout, stderr = process.communicate_utf8(None, None)
    finally:
        if watchdog is not None:
            watchdog.cancel()

    if timed_out:
        return None, stdout, stderr, "timeout"
    return process.get_exit_status(), stdout, stderr, None


def run_command(
    cmd: str | Sequence[str],
    *,
    timeout: float | None = None,
    check: bool = False,
) -> str | None:
    """Run a command, returning stdout or ``None`` when it failed.

    Keys off the exit status, not Fabric's ``exec_shell_command``, which returns
    the error text and so cannot signal success. ``check=True`` raises.
    """
    returncode, stdout, stderr, kind = _spawn_and_wait(cmd, timeout)

    if kind == "timeout":
        message = f"Command timed out after {timeout}s: {cmd}"
        if check:
            raise CommandError(cmd, message, kind="timeout")
        logger.warning(message)
        return None

    if kind == "missing":
        message = f"Failed to run {cmd}: {stderr}"
        if check:
            raise CommandError(cmd, message, kind="missing")
        logger.warning(message)
        return None

    if returncode != 0:
        detail = stderr.strip()
        message = f"Command failed (status {returncode}): {cmd}" + (
            f": {detail}" if detail else ""
        )
        if check:
            raise CommandError(
                cmd,
                message,
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
            )
        logger.warning(message)
        return None
    return stdout


_PROC_ROOT = "/proc"
# The kernel caps comm at 15 chars, so a name that long may be truncated.
_COMM_MAX_LEN = 15
_PROCESS_NAMES_TTL = 1.0
_process_names_cache: tuple[float, frozenset[bytes]] | None = None


def _read_proc_file(path: str, limit: int = 256) -> bytes:
    """Read a small ``/proc`` file, or b"" when it cannot be read.

    Uses os.open/os.read rather than open(): building the io stack costs more
    than the syscall here, and this runs once per pid.
    """
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return b""
    try:
        return os.read(fd, limit)
    except OSError:
        return b""
    finally:
        os.close(fd)


def _process_name_bytes() -> frozenset[bytes]:
    """Every process name currently in procfs, as comm and exe basenames."""
    try:
        entries = os.listdir(_PROC_ROOT)
    except OSError:
        return frozenset()

    names = set()
    for entry in entries:
        if not entry.isdigit():
            continue
        process_dir = f"{_PROC_ROOT}/{entry}"
        comm = _read_proc_file(f"{process_dir}/comm", _COMM_MAX_LEN + 16).strip()
        if not comm:
            continue
        names.add(comm)
        if len(comm) >= _COMM_MAX_LEN:
            # Truncated: only the exe link still carries the full name.
            with contextlib.suppress(OSError):
                exe = os.readlink(f"{process_dir}/exe")
                names.add(os.path.basename(exe).encode())
    return frozenset(names)


def _all_process_names() -> frozenset[bytes]:
    """The process-name snapshot, rebuilt at most once per TTL.

    Walking every pid costs ~8 ms, so 1 Hz pollers would each pay it; the
    snapshot makes the steady-state cost a set lookup.
    """
    global _process_names_cache
    cached = _process_names_cache
    if cached is not None and time.monotonic() - cached[0] < _PROCESS_NAMES_TTL:
        return cached[1]

    names = _process_name_bytes()
    _process_names_cache = (time.monotonic(), names)
    return names


def invalidate_process_names() -> None:
    """Force the next lookup to re-read procfs, after starting or killing one."""
    global _process_names_cache
    _process_names_cache = None


def is_app_running(app_name: str) -> bool:
    """Whether a process named *app_name* exists, read from procfs.

    Replaces ``pidof``, whose fork+exec cost ~28 ms on the GTK main thread.
    Answered from a 1 s snapshot, so invalidate it after starting or killing.
    """
    return app_name.encode() in _all_process_names()


# ── Shared HTTP client ───────────────────────────────────────

_shared_http_client = None
_shared_http_client_lock = threading.Lock()


def get_http_client():
    """Return a shared, connection-pooling ``httpx.Client`` (thread-safe).

    Reuses TCP connections and DNS, and applies consistent timeout/UA defaults,
    so services must not build throwaway clients per call.
    """
    global _shared_http_client
    with _shared_http_client_lock:
        if _shared_http_client is None:
            import httpx

            _shared_http_client = httpx.Client(
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/58.0.3029.110 Safari/537.3"
                    )
                },
                timeout=httpx.Timeout(10.0),
                limits=httpx.Limits(
                    max_keepalive_connections=5,
                    max_connections=10,
                ),
            )
    return _shared_http_client


# ── TTL-cached path existence ─────────────────────────────────

_PATH_EXISTS_CACHE_MAX = 500
_path_exists_cache = TTLCache(maxsize=_PATH_EXISTS_CACHE_MAX)


def path_exists_ttl(path: str, ttl: int = 300) -> bool:
    """``os.path.exists`` with a TTL and a bounded cache (thread-safe).

    Eviction is least-recently-inserted, not LRU, which is fine for a stat
    cache: a hot path is re-stat'ed every *ttl* seconds anyway.
    """
    return _path_exists_cache.get_or_produce(
        path, lambda: os.path.exists(path), ttl=ttl
    )


_LOG_DOMAINS = (
    None,  # Default domain
    "Gtk",
    "Gdk",
    "GLib",
    "GLib-GObject",
    "Pango",
    "Atk",
    "GIO",
    "GStreamer",
    "Gst",
    "Soup",
    "GVfs",
    "GWeather",
    "WebKit",
    "Vte",
    "Cogl",
    "NM",
    "BlueZ",
    "ModemManager",
)


def set_debug_logger():
    import traceback

    level_map = {
        GLib.LogLevelFlags.LEVEL_ERROR: "ERROR",
        GLib.LogLevelFlags.LEVEL_CRITICAL: "CRITICAL",
        GLib.LogLevelFlags.LEVEL_WARNING: "WARNING",
        GLib.LogLevelFlags.LEVEL_MESSAGE: "MESSAGE",
        GLib.LogLevelFlags.LEVEL_INFO: "INFO",
        GLib.LogLevelFlags.LEVEL_DEBUG: "DEBUG",
    }

    mask = ~(GLib.LogLevelFlags.FLAG_FATAL | GLib.LogLevelFlags.FLAG_RECURSION)

    def log_handler(domain, level, message):
        masked_level = GLib.LogLevelFlags(level & mask)
        level_name = level_map.get(masked_level, f"UNKNOWN({level})")
        print(f"\n[{domain or 'Default'}] {level_name}: {message}")
        traceback.print_stack()

    log_levels = (
        GLib.LogLevelFlags.LEVEL_ERROR
        | GLib.LogLevelFlags.LEVEL_CRITICAL
        | GLib.LogLevelFlags.LEVEL_WARNING
        | GLib.LogLevelFlags.LEVEL_MESSAGE
        | GLib.LogLevelFlags.LEVEL_INFO
        | GLib.LogLevelFlags.LEVEL_DEBUG
    )

    for domain in _LOG_DOMAINS:
        GLib.log_set_handler(domain, log_levels, log_handler)


def safe_disconnect(signal_source, handler_id: int | None) -> None:
    """Disconnect *handler_id*, ignoring a stale or already-gone id."""
    if handler_id is not None:
        with contextlib.suppress(Exception):
            signal_source.disconnect(handler_id)
