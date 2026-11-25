"""Wallpaper state shared by the picker.

Saved as ``{"path": <default for all monitors>, "monitors": {<name>: <path>}}``:
a per-monitor entry overrides the default for that monitor. Older files only
having ``path`` still load.
"""

import json
import mimetypes
import os
import re
from collections.abc import Callable, Sequence

from fabric.utils import Gio, GLib, logger

from utils.constants import APP_DATA_DIRECTORY, WALLPAPER_DIR
from utils.functions import ensure_directory, write_json_file

WALLPAPER_STATE_FILE = f"{APP_DATA_DIRECTORY}/wallpaper_picker.json"

BACKENDS = ("hyprpaper", "awww")
DEFAULT_BACKEND = "hyprpaper"
SORTS = ("date", "name")
DEFAULT_SORT = "date"
_AWWW_IMAGE_MARKER = "currently displaying: image: "
_AWWW_MONITOR_RE = re.compile(r"([^:\s][^:]*): \d+x\d+,")

THUMB_SIZE = (512, 288)  # 16:9, so a tile only scales down


def _read_state() -> dict:
    try:
        with open(WALLPAPER_STATE_FILE) as f:
            state = json.load(f)
    except (OSError, ValueError):
        return {"path": None, "monitors": {}}
    if not isinstance(state, dict):
        return {"path": None, "monitors": {}}
    state.setdefault("path", None)
    if not isinstance(state.get("monitors"), dict):
        state["monitors"] = {}
    return state


def _module_config() -> dict:
    """The ``[modules.wallpaper]`` table (empty when unset)."""
    from utils.config import tsumiki_config

    config = tsumiki_config.get("modules", {}).get("wallpaper", {})
    return config if isinstance(config, dict) else {}


def wallpaper_backend() -> str:
    """Configured wallpaper daemon, falling back to hyprpaper."""
    backend = _module_config().get("backend")
    return backend if backend in BACKENDS else DEFAULT_BACKEND


def wallpaper_directory() -> str:
    """Configured wallpaper folder with ``~`` and env vars expanded."""
    directory = _module_config().get("directory") or WALLPAPER_DIR
    if not isinstance(directory, str):
        directory = WALLPAPER_DIR
    return os.path.expandvars(os.path.expanduser(directory))


def wallpaper_thumbs_directory() -> str:
    """Thumbnail cache, kept inside the wallpaper folder so it moves with it."""
    return os.path.join(wallpaper_directory(), ".thumbs")


def wallpaper_sort() -> str:
    """Configured grid order: ``date`` (newest first) or ``name``."""
    sort = _module_config().get("sort")
    return sort if sort in SORTS else DEFAULT_SORT


def _existing(path: str | None) -> str | None:
    return path if path and os.path.exists(path) else None


def get_last_wallpaper() -> str | None:
    """The wallpaper last set for all monitors, if it still exists."""
    return _existing(_read_state()["path"])


def wallpaper_for_monitor(monitor_name: str) -> str | None:
    """The saved wallpaper for one monitor, falling back to the default."""
    state = _read_state()
    return _existing(state["monitors"].get(monitor_name)) or _existing(state["path"])


def save_wallpaper(path: str, monitor_names: list[str] | None = None):
    """Remember *path* for the given monitors, or for all when None."""
    if monitor_names is None:
        state = {"path": path, "monitors": {}}
    else:
        state = _read_state()
        for name in monitor_names:
            state["monitors"][name] = path
    ensure_directory(os.path.dirname(WALLPAPER_STATE_FILE), sync=True)
    write_json_file(WALLPAPER_STATE_FILE, state, sync=True)


def list_wallpapers() -> list[str]:
    """Image file names in the wallpaper folder, ordered by config."""
    entries = []
    try:
        with os.scandir(wallpaper_directory()) as it:
            for entry in it:
                file_type = mimetypes.guess_type(entry.name)[0]
                if not (file_type and file_type.startswith("image/")):
                    continue
                try:
                    mtime = entry.stat().st_mtime
                except OSError:
                    continue
                entries.append((mtime, entry.name))
    except OSError:
        return []
    if wallpaper_sort() == "name":
        entries.sort(key=lambda e: e[1].lower())
    else:
        entries.sort(key=lambda e: (-e[0], e[1].lower()))
    return [name for _, name in entries]


def wallpaper_path(name: str) -> str:
    return os.path.join(wallpaper_directory(), name)


def thumbnail_path(name: str) -> str:
    return os.path.join(
        wallpaper_thumbs_directory(), f"{THUMB_SIZE[0]}x{THUMB_SIZE[1]}_{name}"
    )


def parse_listactive(text: str) -> dict[str, str]:
    """Parse ``hyprctl hyprpaper listactive`` output into monitor -> path."""
    active: dict[str, str] = {}
    for line in text.splitlines():
        name, sep, path = line.partition(":")
        if sep and path.strip():
            active[name.strip()] = path.strip()
    return active


def parse_awww_query(text: str) -> dict[str, str]:
    """Parse ``awww query`` output into monitor -> path.

    Each line looks like
    ``: DP-1: 1920x1080, scale: 1, currently displaying: image: /path``
    (an optional daemon namespace can precede the monitor name).
    """
    active: dict[str, str] = {}
    for line in text.splitlines():
        head, sep, path = line.partition(_AWWW_IMAGE_MARKER)
        if not sep or not path.strip():
            continue
        match = _AWWW_MONITOR_RE.search(head)
        if match:
            active[match.group(1).strip()] = path.strip()
    return active


def _run_async(argv: Sequence[str], callback: Callable[[bool, str, str], None]):
    """Run *argv* and report (ok, stdout, stderr) on the main loop."""
    try:
        proc = Gio.Subprocess.new(
            list(argv),
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
        )
    except GLib.Error as e:
        logger.error(f"[Wallpaper] Failed to run {argv[0]}: {e.message}")
        callback(False, "", e.message)
        return

    def _done(process: Gio.Subprocess, task: Gio.AsyncResult):
        try:
            _ok, stdout, stderr = process.communicate_utf8_finish(task)
        except GLib.Error as e:
            logger.error(f"[Wallpaper] {argv[0]} failed: {e.message}")
            callback(False, "", e.message)
            return
        callback(process.get_successful(), stdout or "", stderr or "")

    proc.communicate_utf8_async(None, None, _done)


def list_monitors_async(callback: Callable[[list[dict]], None]):
    """Hyprland's monitor list (name, width, height, x, y, ...)."""
    # Imported lazily: tests import this module without a Hyprland socket.
    from utils.hyprland import hyprland_service

    hyprland_service.get_monitors_async(lambda monitors: callback(monitors or []))


def apply_wallpaper(
    path: str,
    monitor_names: list[str],
    on_done: Callable[[], None] | None = None,
):
    """Show *path* on the given monitors via the configured daemon."""
    if wallpaper_backend() == "awww":
        if not monitor_names:
            if on_done:
                on_done()
            return
        _run_async(
            ["awww", "img", "-o", ",".join(monitor_names), path],
            lambda *_args: on_done and on_done(),
        )
        return

    remaining = len(monitor_names)
    if remaining == 0:
        if on_done:
            on_done()
        return

    def done(_ok: bool, _out: str, _err: str):
        nonlocal remaining
        remaining -= 1
        if remaining == 0 and on_done:
            on_done()

    for name in monitor_names:
        _run_async(
            ["hyprctl", "hyprpaper", "wallpaper", f"{name},{path}"],
            done,
        )


def query_active_wallpapers(callback: Callable[[dict[str, str]], None]):
    """What each monitor is actually showing, per the configured daemon."""

    def on_done(ok: bool, out: str, _err: str):
        callback(parse_active(out) if ok else {})

    def parse_active(text: str) -> dict[str, str]:
        if wallpaper_backend() == "awww":
            return parse_awww_query(text)
        return parse_listactive(text)

    if wallpaper_backend() == "awww":
        _run_async(["awww", "query"], on_done)
    else:
        _run_async(["hyprctl", "hyprpaper", "listactive"], on_done)


def restore_wallpapers():
    """Re-apply the saved wallpaper to each connected monitor."""

    def on_monitors(monitors: list[dict]):
        for monitor in monitors:
            path = wallpaper_for_monitor(monitor["name"])
            if path:
                apply_wallpaper(path, [monitor["name"]])

    list_monitors_async(on_monitors)
