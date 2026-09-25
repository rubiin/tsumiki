import atexit
import contextlib
import ctypes
import html
import importlib
import json
import re
import shutil
import subprocess
import tempfile
import threading
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from functools import lru_cache
from io import BytesIO
from typing import Any, Callable, Iterable, List, Literal, Optional, TypeVar

import gi
from fabric.hyprland import HyprlandReply
from fabric.utils import (
    Gdk,
    GdkPixbuf,
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
    WHITE,
)
from .decorators import run_in_thread, thread
from .exceptions import ExecutableNotFoundError
from .icons import get_text_icon

gi.require_version("Pango", "1.0")
from gi.repository import Pango  # noqa: E402

# Formatting tags re-enabled by ``parse_markup`` after escaping (SwayNC-inspired).
_ALLOWED_MARKUP_TAGS_RE = re.compile(r"&lt;(/?(?:b|i|u))&gt;")
# Double-escaped entities some apps send (e.g. Discord escapes "<" itself).
_DOUBLE_ESCAPED_ENTITIES_RE = re.compile(
    r"&amp;(lt;|gt;|amp;|apos;|quot;|#60;|#x3C;|#x3c;|#62;|#x3E;|#x3e;|#39;|#34;)"
)
# One-time codes (2FA / OTP) in notification bodies, e.g. "123-456" or "482913",
# delimited by whitespace/string boundaries and optional trailing punctuation.
# The optional literal "G-" prefix covers Google's "G-123456" sender format.
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

T = TypeVar("T")
U = TypeVar("U")


def batch_process(
    items: Iterable[T], batch_size: int, func: Callable[[List[T]], List[U]]
) -> List[U]:
    """Process items in batches for efficiency."""
    result = []
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) == batch_size:
            result.extend(func(batch))
            batch = []
    if batch:
        result.extend(func(batch))
    return result


def get_window_manager_backend() -> Literal["hyprland", "sway", "i3"]:
    """Detect the current compositor/window-manager backend from session env vars."""

    desktop_markers = " ".join(
        filter(
            None,
            [
                os.environ.get("XDG_CURRENT_DESKTOP", ""),
                os.environ.get("XDG_SESSION_DESKTOP", ""),
                os.environ.get("DESKTOP_SESSION", ""),
            ],
        )
    ).lower()

    if os.environ.get("SWAYSOCK") or "sway" in desktop_markers:
        return "sway"
    if os.environ.get("I3SOCK") or "i3" in desktop_markers:
        return "i3"
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") or "hyprland" in desktop_markers:
        return "hyprland"

    # Keep existing behavior as default.
    return "hyprland"


# Function to convert RGB to hex format
def rgb_to_hex(rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


# Function to set the process name
def set_process_name(name: str):
    libc = ctypes.CDLL("libc.so.6")
    libc.prctl(15, name.encode("utf-8"), 0, 0, 0)  # 15 = PR_SET_NAME


# Function to convert RGB to CSS rgb format
def rgb_to_css(rgb) -> str:
    return f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]})"


# Function to mix two RGB colors, with a ratio of 0.5 by default.
def mix_colors(color1, color2, ratio=0.5) -> tuple[int, int, int]:
    r = int(color1[0] * (1 - ratio) + color2[0] * ratio)
    g = int(color1[1] * (1 - ratio) + color2[1] * ratio)
    b = int(color1[2] * (1 - ratio) + color2[2] * ratio)
    return (r, g, b)


# Function to tint a color by mixing it with white
def tint_color(color, tint_factor=1) -> tuple[int, int, int]:
    # tint_factor: 0 means original color, 1 means full white
    return mix_colors(color, WHITE, tint_factor)


def delayed_call(
    delay_ms: int,
    callback: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> int:
    """Schedule a function to be called after a delay.

    Similar to JavaScript's setTimeout. The callback runs on the main GTK thread.
    """

    def _wrapper() -> bool:
        callback(*args, **kwargs)
        return False  # Don't repeat

    return GLib.timeout_add(delay_ms, _wrapper)


def delayed_call_seconds(
    delay_seconds: float,
    callback: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> int:
    """Schedule a function to be called after a delay in seconds.

    Convenience wrapper around delayed_call for second-based delays.
    """
    return delayed_call(int(delay_seconds * 1000), callback, *args, **kwargs)


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


# Function to get a simple color palette from an image using threading
def get_simple_palette_threaded(
    image_path: str,
    callback: Callable[[Optional[list[tuple[int, int, int]]]], None],
    color_count: int = 4,
    resize: int = 64,
):
    thread(_pillow_worker, image_path, callback, color_count, resize)


# Function to escape the markup
def parse_markup(text: str) -> str:
    """Escape *text* for Pango markup, re-enabling a small whitelist of
    formatting tags (b/i/u) so apps can send basic formatting without being
    able to inject arbitrary markup (inspired by SwayNotificationCenter).

    Falls back to fully-escaped output when the re-enabled markup does not
    parse (e.g. unclosed tags), so malformed bodies can never break rendering.
    """
    escaped = html.escape(text.replace("\n", " "))
    # Re-enable whitelisted tags first (real ``<b>`` tags survive escaping as
    # ``&lt;b&gt;``), then fix double-escaped entities: apps like Discord send
    # pre-escaped text, so a literal "<" arrives as "&lt;" and would render as
    # "&lt;" without unescaping "&amp;" back to "&" first (SwayNC behavior).
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
    """Return the first one-time (2FA) code found in *text*, else ``None``.

    Matches 4-8 digit codes and ``123-456`` / ``123 456`` pairs delimited by
    whitespace or string boundaries, plus Google's ``G-123456`` format
    (SwayNC-inspired). Returns digits only, ready for pasting into OTP fields.
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
    """Strip ``<img src=...>`` tags from *text* and return a tuple of the
    cleaned text and the first image source, or ``None`` (SwayNC-inspired).

    The returned source is not resolved to a path; use ``expand_env`` and
    ``os.path.exists`` at the call site.
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
    """Format a unix timestamp as a compact relative label, e.g. "Now",
    "5m ago", "2h ago", "3d ago". Accepts seconds or milliseconds; returns an
    empty string for missing/invalid input."""
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
    """Copy *text* to the system clipboard (wl-copy, falling back to xclip).

    Synchronous by default, which reports whether the copy completed. With
    *asynchronous* the text is handed to the tool and the call returns
    immediately so the GTK thread is never blocked while it starts; the real
    outcome then arrives on the completion callback, so the return value only
    says the copy was dispatched.

    A missing tool or a spawn failure is logged, never raised.
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
    """Write via a temp file beside *path*, then rename it into place.

    A crash or a failed dump leaves the previous file intact instead of a
    truncated one, so ``config.toml`` and the caches cannot be corrupted. The
    temp file is removed if the dump raises.
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


# support for multiple monitors
def for_monitors(widget: Gtk.Widget) -> list[Gtk.Widget]:
    n = Gdk.Display.get_default().get_n_monitors() if Gdk.Display.get_default() else 1
    return [widget(i) for i in range(n)]


# Function to ttl lru cache
def ttl_lru_cache(seconds_to_live: int, maxsize: int = 128):
    def wrapper(func):
        @lru_cache(maxsize)
        def inner(__ttl, *args, **kwargs):
            return func(*args, **kwargs)

        return lambda *args, **kwargs: inner(
            time.time() // seconds_to_live, *args, **kwargs
        )

    return wrapper


# Function to parse hyprland reply
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


# Lock to serialize read-modify-write cycles on config.toml.
# Without this, concurrent calls (e.g. set_mode triggering both
# theme and mode updates) race on the same file: the second read
# can observe stale pre-first-write content, silently reverting
# the first update on next restart.
_config_write_lock = threading.Lock()


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
            node[key_path[-1]] = value

            write_toml_file(config_file, config, sync=True)
        except (IOError, OSError, ValueError, KeyError, TypeError) as e:
            logger.exception(
                f"{Colors.ERROR}[Config] Error updating {'.'.join(key_path)}: {e}"
            )


# Function to update the theme configuration
def update_theme_config(theme_name: str):
    """Update the config.toml file with the new theme name."""
    _update_config_key(["styling", "theme_name"], theme_name)
    logger.info(f"{Colors.INFO}[Theme] Updated theme config to {theme_name}")


# Function to update the styling mode (dark/light)
def update_styling_mode(mode: str):
    """Update the config.toml file with the new styling mode."""
    _update_config_key(["styling", "mode"], mode)
    logger.info(f"{Colors.INFO}[Theme] Updated styling mode to {mode}")


# Function to convert celsius to fahrenheit
def celsius_to_fahrenheit(celsius: float) -> float:
    return (celsius * 9 / 5) + 32


# Merge the parsed data with the default configuration
def deep_merge(data: dict, target: dict) -> dict:
    """
    Recursively update a nested dictionary with values from another dictionary.
    """
    merged = target.copy()
    for key, user_value in data.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(user_value, dict)
        ):
            merged[key] = deep_merge(user_value, merged[key])
        else:
            merged[key] = user_value
    return merged


# Function to flatten a dictionary
def flatten_dict(d: dict, parent_key: str = "", sep: str = "-") -> dict:
    """Flatten a nested dictionary into a single level."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):  # If the value is a dictionary, recurse
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


# Function to exclude keys from a dictionary
def exclude_keys(d: dict, keys_to_exclude: list[str]) -> dict:
    return {k: v for k, v in d.items() if k not in keys_to_exclude}


# Function to format time in hours and minutes
def format_seconds_to_hours_minutes(secs: int) -> str:
    mm, _ = divmod(secs, 60)
    hh, mm = divmod(mm, 60)
    return "%d h %02d min" % (hh, mm)


# Function to convert bytes to kilobytes, megabytes, or gigabytes
def convert_bytes(
    bytes: int, to: Literal["kb", "mb", "gb", "tb"], format_spec=".1f"
) -> str:
    factor = BYTES_FACTORS.get(to, 1)
    return f"{format(bytes / (1024**factor), format_spec)}{to.upper()}"


# Function to check if the current time is between sunrise and sunset
def check_if_day(
    sunrise_time,
    sunset_time,
    current_time: str | None = None,
    time_format: str = "%I:%M %p",
) -> str:
    if current_time is None:
        current_time = datetime.now().strftime(time_format)

    current_time_obj = datetime.strptime(current_time, time_format)
    sunrise_time_obj = datetime.strptime(sunrise_time, time_format)
    sunset_time_obj = datetime.strptime(sunset_time, time_format)

    # Compare current time with sunrise and sunset
    if sunrise_time_obj <= sunset_time_obj:
        return sunrise_time_obj <= current_time_obj < sunset_time_obj

    return current_time_obj >= sunrise_time_obj or current_time_obj < sunset_time_obj


# wttr.in time are in 300,400...2100 format, we need to convert it to 4:00...21:00
# Accepts both "HHMM" (e.g. "1200") and "HH:MM" (e.g. "14:30") input.
def convert_to_12hr_format(time: str) -> str:
    if not time:
        return time or ""

    # Handle "HH:MM" format (e.g. from Open-Meteo sunrise/sunset)
    if ":" in str(time):
        try:
            hour, minute = map(int, str(time).split(":"))
        except (ValueError, IndexError):
            return str(time)
    else:
        # Handle "HHMM" format (e.g. from wttr.in hourly forecast)
        time_int = int(time)
        hour = time_int // 100
        minute = time_int % 100

    # Convert to 12-hour format
    period = "AM" if hour < 12 else "PM"

    # Adjust hour for 12-hour format
    if hour == 0:
        hour = 12
    elif hour > 12:
        hour -= 12

    # Format the time as a string
    return f"{hour}:{minute:02d} {period}"


# Function to unique list
def unique_list(lst: list[Any]) -> list[Any]:
    """Return a list with unique elements."""
    return list(set(lst))


# Function to get the relative time
def get_relative_time(mins: int) -> str:
    # Seconds
    if mins == 0:
        return "now"

    # Minutes
    if mins < 60:
        return f"{mins} minute{'s' if mins > 1 else ''} ago"

    # Hours
    if mins < 1440:
        hours = mins // 60
        return f"{hours} hour{'s' if hours > 1 else ''} ago"

    # Days
    days = mins // 1440
    return f"{days} day{'s' if days > 1 else ''} ago"


# Function to get the percentage of a value
def convert_to_percent(
    current: int | float, max: int | float, is_int=True
) -> int | float:
    if max == 0:
        return 0
    if is_int:
        return int((current / max) * 100)
    else:
        return (current / max) * 100


# Function to check if a color is valid
def is_valid_gjs_color(color: str) -> bool:
    color_lower = color.strip().lower()

    if color_lower in NAMED_COLORS:
        return True

    if HEX_COLOR_RE.match(color):
        return True

    return bool(RGB_RE.match(color_lower) or RGBA_RE.match(color_lower))


# Function to convert seconds to milliseconds
def convert_seconds_to_milliseconds(seconds: int) -> int:
    return seconds * 1000


# Set the scale's adjustment
def set_scale_adjustment(
    scale, min_value: float = 0, max_value: float = 100, steps: float = 1
):
    adj = scale.get_adjustment()
    if adj.get_upper() == adj.get_lower():
        scale.set_adjustment(
            Gtk.Adjustment(
                lower=min_value,
                upper=max_value,
                step_increment=steps,
                page_increment=0,
                page_size=0,
            )
        )


# Function to toggle a shell command
def toggle_command(command: str, full_command: str):
    full_command = full_command.strip(" ")
    if is_app_running(command):
        kill_process(command)
    else:
        # Use subprocess directly so the launched app survives bar restart.
        subprocess.Popen(
            full_command,
            shell=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


def char_limit_to_px(label_widget, char_limit: int) -> int:
    n = max(1, int(char_limit))
    sample = "M" * n  # conservative (wide) mapping
    layout = label_widget.create_pango_layout(sample)
    style = label_widget.get_style_context()
    layout.set_font_description(style.get_font(Gtk.StateFlags.NORMAL))
    px, _ = layout.get_pixel_size()
    return px


## Function to execute a shell command asynchronously
def kill_process(process_name: str):
    exec_shell_command_async(f"pkill {process_name}", lambda *_: None)


def lazy_load_class(module_name: str, class_name: str):
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


# Function to generate a QR code image
@ttl_lru_cache(3600, 10)
def make_qrcode(text: str, size: int = 200) -> GdkPixbuf.Pixbuf:
    import qrcode

    # Generate QR Code image
    qr = qrcode.make(text)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    buffer.seek(0)

    # Load into GTK Pixbuf
    loader = GdkPixbuf.PixbufLoader.new_with_type("png")
    loader.write(buffer.read())
    loader.close()
    pixbuf = loader.get_pixbuf()

    # Scale Pixbuf to the desired size
    scaled_pixbuf = pixbuf.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)

    return scaled_pixbuf


# Function to play sound
@cooldown(1)
def play_sound(file: str):
    exec_shell_command_async(f"pw-play {file}", lambda *_: None)


# Function to get the distro icon
@ttl_lru_cache(600, 10)
def get_distro_icon() -> str:
    distro_id = GLib.get_os_info("ID")

    # Search for the icon in the list
    return get_text_icon(f"distro.{distro_id}", "") or ""


# Function to check if an executable exists
@ttl_lru_cache(600, 10)
def check_executable_exists(executable_name):
    executable_path = GLib.find_program_in_path(executable_name)
    if not executable_path:
        raise ExecutableNotFoundError(
            executable_name
        )  # Raise an error if the executable is not found and exit the application


# Function to locate an executable on PATH
@ttl_lru_cache(600, 64)
def find_executable(executable_name: str) -> str | None:
    """Return the absolute path of *executable_name*, or None if not found.

    TTL-cached (10 min) so repeated lookups — e.g. plugins probing for a
    required tool on every query — don't re-scan PATH each time.
    """
    return GLib.find_program_in_path(executable_name)


# Function to send a notification
@cooldown(1)
def send_notification(
    title: str,
    body: str,
    urgency: Literal["low", "normal", "critical"] = "normal",
    icon: Optional[str] = None,
    app_name: str = "Application",
):
    # Create a notification with the title
    notification = Gio.Notification.new(title)
    notification.set_body(body)

    # Set the urgency level if provided
    if urgency in URGENCY_LEVELS:
        notification.set_urgent(urgency == "critical")

    # Set the icon if provided
    if icon:
        notification.set_icon(Gio.ThemedIcon.new(icon))

    # Optionally, set the application name
    notification.set_title(app_name)

    application = Gio.Application.get_default()

    # Send the notification to the application
    application.send_notification(None, notification)
    return True


def write_json_file(path: str, data: dict | list, *, sync: bool = False):
    """Write JSON off-thread by default, or inline when *sync* is true.

    Write failures are logged, never raised, so a caller on a worker thread
    cannot be wedged by an unwritable path.
    """
    if not sync:
        return thread(write_json_file, path, data, sync=True)

    try:
        _atomic_write(
            path, lambda handle: json.dump(data, handle, indent=4, ensure_ascii=False)
        )
    except (IOError, OSError, TypeError) as e:
        logger.exception(f"Failed to write json: {e}")


# Function to ensure the file exists
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


# Function to ensure the directory exists
@run_in_thread
def ensure_directory(path: str):
    if not GLib.file_test(path, GLib.FileTest.EXISTS):
        try:
            Gio.File.new_for_path(path).make_directory_with_parents(None)
        except GLib.Error as e:
            logger.exception(f"Failed to create directory {path}: {e.message}")


def run_command(cmd: str | Sequence[str]) -> str | None:
    """Run a command and return its stdout, or ``None`` when it failed.

    Fabric's ``exec_shell_command`` returns the *error text* on a non-zero
    exit, so its result cannot be used to tell success from failure - callers
    testing it for ``False`` never see an error. This wrapper keys off the
    exit status instead, which is the only reliable signal.

    A list argument runs without a shell, which is the safe form for any value
    that came from config, a notification or the filesystem. A string runs via
    the shell, for commands that genuinely need it.
    """
    try:
        result = subprocess.run(
            cmd,
            shell=isinstance(cmd, str),
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.exception(f"Failed to run {cmd}: {e}")
        return None

    if result.returncode != 0:
        detail = result.stderr.strip()
        logger.warning(
            f"Command failed (status {result.returncode}): {cmd}"
            + (f": {detail}" if detail else "")
        )
        return None
    return result.stdout


# Function to check if an app is running
@ttl_lru_cache(seconds_to_live=2, maxsize=32)
def is_app_running(app_name: str) -> bool:
    # pidof exits non-zero when nothing matches, so the status is the answer.
    return run_command(["pidof", app_name]) is not None


# Function to take a memory snapshot
def take_snapshot():
    import tracemalloc

    tracemalloc.start()
    # Later in code
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics("lineno")

    print("stats", tracemalloc.get_traced_memory())

    print("[Top 10 Memory Lines]")
    for stat in top_stats[:10]:
        print(stat)

    return True  # Keep the timeout active


# ── Shared HTTP client ───────────────────────────────────────

_shared_http_client = None
_shared_http_client_lock = threading.Lock()


def get_http_client():
    """Return a shared ``httpx.Client`` with connection pooling (thread-safe).

    Services that make HTTP requests (weather, quotes, etc.) should use
    this instead of creating throwaway ``httpx.Client`` or ``urlopen``
    instances per call.  The shared session reuses TCP connections,
    caches DNS, and applies consistent timeout / User-Agent defaults.

    The underlying ``httpx`` module is imported lazily, so there is no
    import cost for configurations that never make HTTP requests.
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

_path_exists_cache: dict[str, tuple[bool, float]] = {}
_PATH_EXISTS_CACHE_MAX = 500
_path_exists_cache_lock = threading.Lock()


def path_exists_ttl(path: str, ttl: int = 300) -> bool:
    """Check if a filesystem path exists, with TTL and bounded caching (thread-safe).

    Caches ``os.path.exists`` results to avoid redundant syscalls on
    hot paths (system tray icon checks, device scans, etc.).  The
    cache is a simple module-level dict capped at ``_PATH_EXISTS_CACHE_MAX``
    entries; entries live at most *ttl* seconds before a fresh stat
    is issued.  When the cache exceeds the cap the oldest entry is
    evicted.
    """
    with _path_exists_cache_lock:
        now = time.time()
        cached = _path_exists_cache.get(path)
        if cached is not None and now - cached[1] < ttl:
            return cached[0]

    result = os.path.exists(path)

    with _path_exists_cache_lock:
        if len(_path_exists_cache) >= _PATH_EXISTS_CACHE_MAX:
            # Evict oldest entry
            try:
                oldest = next(iter(_path_exists_cache))
                del _path_exists_cache[oldest]
            except StopIteration:
                pass
        _path_exists_cache[path] = (result, now)
    return result


# Pre-defined log domains tuple (immutable)
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


# Function to set a debug logger for GLib
def set_debug_logger():
    import traceback

    # Build level map once
    level_map = {
        GLib.LogLevelFlags.LEVEL_ERROR: "ERROR",
        GLib.LogLevelFlags.LEVEL_CRITICAL: "CRITICAL",
        GLib.LogLevelFlags.LEVEL_WARNING: "WARNING",
        GLib.LogLevelFlags.LEVEL_MESSAGE: "MESSAGE",
        GLib.LogLevelFlags.LEVEL_INFO: "INFO",
        GLib.LogLevelFlags.LEVEL_DEBUG: "DEBUG",
    }

    # Pre-compute mask
    mask = ~(GLib.LogLevelFlags.FLAG_FATAL | GLib.LogLevelFlags.FLAG_RECURSION)

    def log_handler(domain, level, message):
        masked_level = GLib.LogLevelFlags(level & mask)
        level_name = level_map.get(masked_level, f"UNKNOWN({level})")
        print(f"\n[{domain or 'Default'}] {level_name}: {message}")
        traceback.print_stack()

    # Set log levels
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
    """Safely disconnect a signal handler without raising exceptions.

    Args:
        signal_source: The object (e.g., GObject) with the signal
        handler_id: The handler ID returned by connect(). Can be None.
    """
    if handler_id is not None:
        with contextlib.suppress(Exception):
            signal_source.disconnect(handler_id)


def load_cover_pixbuf(path: str, width: int, height: int):
    # Decode at roughly the target size to avoid full-resolution decode.
    # GdkPixbuf.new_from_file_at_size uses optimized JPEG decode that only
    # decompresses the needed resolution when possible.
    target_size = max(width, height)
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(path, target_size, target_size)

    src_w = pixbuf.get_width()
    src_h = pixbuf.get_height()

    scale = max(width / src_w, height / src_h)

    scaled_w = int(src_w * scale)
    scaled_h = int(src_h * scale)

    scaled = pixbuf.scale_simple(
        scaled_w,
        scaled_h,
        GdkPixbuf.InterpType.BILINEAR,
    )

    x = (scaled_w - width) // 2
    y = (scaled_h - height) // 2

    return scaled.new_subpixbuf(x, y, width, height)
