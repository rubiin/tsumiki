"""Watch config files and restart Tsumiki when they change."""

import hashlib
import threading

from fabric.utils import (
    Gio,
    GLib,
    get_relative_path,
    logger,
    os,
)

from utils.colors import Colors
from utils.config import tsumiki_config
from utils.constants import APPLICATION_NAME
from utils.functions import spawn_detached

# Debounce first, then enforce a minimum gap between restart attempts.
_DEFAULT_RESTART_DELAY = 1500
_RESTART_COOLDOWN_MS = 3000
_CONFIG_FILES = frozenset(["config.toml"])


class ConfigWatcher:
    """Simple file watcher that monitors config files and restarts Tsumiki."""

    __slots__ = (
        "_cooldown_timer_id",
        "_file_hashes",
        "_initialized",
        "_last_restart_at_us",
        "_restart_delay",
        "_restart_pending",
        "_restart_timer_id",
        "init_script",
        "monitors",
        "root_dir",
        "watched_names",
    )

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.monitors: list[Gio.FileMonitor] = []
        self._file_hashes: dict[str, str | None] = {}
        self._restart_pending = False
        self._last_restart_at_us = 0
        self._restart_delay = self._get_restart_delay()
        self._restart_timer_id = None
        self._cooldown_timer_id = None
        self.root_dir = get_relative_path("..")
        self.init_script = f"{self.root_dir}/tsumiki.sh"
        self.watched_names = {os.path.basename(p) for p in _CONFIG_FILES}

        self._monitor_directory()

        self._initialized = True

    def _monitor_directory(self):
        """Monitor the config directory, reacting only to watched files.

        Watching the directory survives an editor's atomic save-by-rename,
        which would drop a per-file inotify watch.
        """
        try:
            directory = Gio.File.new_for_path(self.root_dir)
            monitor = directory.monitor_directory(Gio.FileMonitorFlags.NONE, None)
            monitor.connect("changed", self._on_file_changed)
            self.monitors.append(monitor)
            logger.info(
                f"{Colors.INFO}[ConfigWatcher] Monitoring "
                f"{', '.join(sorted(self.watched_names))} in {self.root_dir}"
            )
        except Exception as e:
            logger.exception(
                f"{Colors.ERROR}[ConfigWatcher] Failed to monitor {self.root_dir}: {e}"
            )

        for filename in _CONFIG_FILES:
            config_path = f"{self.root_dir}/{filename}"
            if os.path.exists(config_path):
                self._file_hashes[config_path] = self._read_file_hash(config_path)

    def _get_restart_delay(self) -> int:
        """Read restart debounce delay from config with a safe fallback."""
        delay_ms = (
            tsumiki_config.get("general", {}).get(
                "restart_delay", _DEFAULT_RESTART_DELAY
            )
            or _DEFAULT_RESTART_DELAY
        )

        try:
            return max(1, int(delay_ms))
        except (TypeError, ValueError):
            logger.warning(
                f"{Colors.WARNING}[ConfigWatcher] Invalid restart_delay "
                f"({delay_ms}), using {_DEFAULT_RESTART_DELAY}"
            )
            return _DEFAULT_RESTART_DELAY

    def _read_file_hash(self, file_path: str) -> str | None:
        """Return a stable hash for file content, or None when unreadable."""
        try:
            with open(file_path, "rb") as config_file:
                return hashlib.sha256(config_file.read()).hexdigest()
        except OSError:
            return None

    def _is_relevant_event(self, event_type) -> bool:
        """Whether an inotify event may have changed a watched file.

        An atomic save reports several event types (and a fresh file may only
        ever report CREATED), so the content hash — not the event — decides
        whether this is a real change.
        """
        events = Gio.FileMonitorEvent
        return event_type in (
            events.CHANGED,
            events.CHANGES_DONE_HINT,
            events.CREATED,
            events.RENAMED,
            events.MOVED_IN,
        )

    def _on_file_changed(self, monitor, file, other_file, event_type):
        """Handle file change events."""
        if not self._is_relevant_event(event_type):
            return

        file_path = file.get_path()
        if not file_path or os.path.basename(file_path) not in self.watched_names:
            return

        current_hash = self._read_file_hash(file_path)
        previous_hash = self._file_hashes.get(file_path)
        if current_hash is None or current_hash == previous_hash:
            return

        self._file_hashes[file_path] = current_hash
        if self._restart_pending:
            return

        self._restart_pending = True
        logger.info(
            f"{Colors.INFO}[ConfigWatcher] Config changed: {file.get_basename()}"
        )
        if self._restart_timer_id is not None:
            GLib.source_remove(self._restart_timer_id)
        # Delay restart slightly to batch rapid config writes.
        self._restart_timer_id = GLib.timeout_add(
            self._restart_delay, self._restart_if_allowed
        )

    def _restart_if_allowed(self) -> bool:
        """Restart after debounce while respecting cooldown between restarts."""
        self._restart_timer_id = None
        now_us = GLib.get_monotonic_time()
        if self._last_restart_at_us:
            elapsed_ms = (now_us - self._last_restart_at_us) // 1000
            if elapsed_ms < _RESTART_COOLDOWN_MS:
                wait_ms = max(1, _RESTART_COOLDOWN_MS - elapsed_ms)
                if self._cooldown_timer_id is not None:
                    GLib.source_remove(self._cooldown_timer_id)
                self._cooldown_timer_id = GLib.timeout_add(
                    wait_ms, self._restart_if_allowed
                )
                return False

        self._restart_pending = False
        self._last_restart_at_us = now_us

        logger.info(f"{Colors.INFO}[ConfigWatcher] Restarting after config changes")
        return self._restart_tsumiki()

    def _restart_tsumiki(self) -> bool:
        """Restart Tsumiki using the init script."""
        try:
            logger.info(
                f"{Colors.INFO}[ConfigWatcher] Restarting {APPLICATION_NAME.title()}..."
            )
            # Detached so the restart outlives the bar it is about to kill.
            spawn_detached(
                [self.init_script, "-restart"],
                cwd=os.path.dirname(self.init_script),
            )
        except Exception as e:
            logger.exception(f"{Colors.ERROR}[ConfigWatcher] Failed to restart: {e}")

        return False  # Don't repeat

    def stop(self):
        """Stop monitoring files and cancel pending timers."""
        for monitor in self.monitors:
            monitor.cancel()
        self.monitors.clear()
        self._file_hashes.clear()
        if self._restart_timer_id is not None:
            GLib.source_remove(self._restart_timer_id)
            self._restart_timer_id = None
        if self._cooldown_timer_id is not None:
            GLib.source_remove(self._cooldown_timer_id)
            self._cooldown_timer_id = None


_watcher: ConfigWatcher | None = None
_watcher_lock = threading.Lock()


def start_config_watching():
    """Start watching config files for changes (thread-safe)."""
    global _watcher
    with _watcher_lock:
        if _watcher is None:
            _watcher = ConfigWatcher()


def stop_config_watching():
    """Stop watching config files (thread-safe)."""
    global _watcher
    with _watcher_lock:
        if _watcher is not None:
            _watcher.stop()
            _watcher = None
