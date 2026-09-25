import warnings

from fabric.hyprland import Hyprland
from fabric.utils import Gdk, bulk_connect, logger

from utils.decorators import cancel_timeout, replace_timeout
from utils.hyprland import hyprland_service
from utils.singleton import SingletonMixin

from .constants import MONITOR_HOTPLUG_DELAY_MS
from .functions import parse_hyprland_reply

warnings.filterwarnings("ignore", category=DeprecationWarning)


class HyprlandWithMonitors(SingletonMixin, Hyprland):
    """A Hyprland class with additional monitor common."""


    def __init__(self, commands_only: bool = False, **kwargs):
        super().__init__(commands_only, **kwargs)
        self.display: Gdk.Display = Gdk.Display.get_default()

    def get_all_monitors(self, callback):
        """Fetch all monitors asynchronously.

        Calls callback(dict | None) with {monitor_id: monitor_name} mapping.
        """
        self.send_command_async(
            "j/monitors",
            lambda reply: self._handle_all_monitors_reply(reply, callback),
        )

    def _handle_all_monitors_reply(self, reply, callback):
        try:
            monitors_data = parse_hyprland_reply(reply)
            callback({monitor["id"]: monitor["name"] for monitor in monitors_data})
        except Exception as e:
            logger.exception(f"[Monitors] Error parsing monitors reply: {e}")
            callback(None)

    def get_gdk_monitor_id_from_name(self, plug_name: str) -> int | None:
        for i in range(self.display.get_n_monitors()):
            if self.display.get_default_screen().get_monitor_plug_name(i) == plug_name:
                return i
        return None

    def get_gdk_monitor_id(self, hyprland_id: int, callback):
        """Get GDK monitor ID asynchronously."""
        self.get_all_monitors(
            lambda monitors: callback(
                self.get_gdk_monitor_id_from_name(monitors[hyprland_id])
                if monitors and hyprland_id in monitors
                else None
            )
        )

    def get_current_gdk_monitor_id(self, callback):
        """Get current GDK monitor ID asynchronously."""
        self.send_command_async(
            "j/activeworkspace",
            lambda reply: self._handle_current_monitor_reply(reply, callback),
        )

    def _handle_current_monitor_reply(self, reply, callback):
        try:
            active_workspace = parse_hyprland_reply(reply)
            monitor_name = active_workspace.get("monitor")
            if monitor_name:
                callback(self.get_gdk_monitor_id_from_name(monitor_name))
            else:
                callback(None)
        except Exception as e:
            logger.exception(f"[Monitors] Error parsing active workspace reply: {e}")
            callback(None)

    def get_monitor_names(self, callback):
        """Get list of all connected monitor names asynchronously."""
        self.send_command_async(
            "j/monitors",
            lambda reply: self._handle_monitor_names_reply(reply, callback),
        )

    def _handle_monitor_names_reply(self, reply, callback):
        try:
            monitors_data = parse_hyprland_reply(reply)
            callback([monitor["name"] for monitor in monitors_data])
        except Exception as e:
            logger.exception(f"[Monitors] Error parsing monitor names: {e}")
            callback([])


class MonitorWatcher:
    """Watches for monitor add/remove events and notifies registered callbacks."""

    def __init__(self):
        self.callbacks = []
        self._hyprland_connection = None
        self._pending_timer_id = None

    def add_callback(self, callback):
        if callback not in self.callbacks:
            self.callbacks.append(callback)

    def start_watching(self):
        if self._hyprland_connection:
            return

        self._hyprland_connection = hyprland_service.connection
        bulk_connect(
            self._hyprland_connection,
            {
                "event::monitoradded": self.on_monitor_changed,
                "event::monitorremoved": self.on_monitor_changed,
            },
        )

    def stop(self):
        """Cancel any pending timer and stop watching."""
        cancel_timeout(self, "_pending_timer_id")
        self.callbacks.clear()

    def on_monitor_changed(self, *_):
        replace_timeout(
            self, "_pending_timer_id", MONITOR_HOTPLUG_DELAY_MS, self._notify_callbacks
        )

    def _notify_callbacks(self):
        self._pending_timer_id = None
        for callback in tuple(self.callbacks):
            try:
                callback()
            except Exception as e:
                logger.exception(f"Monitor callback error: {e}")
        return False
