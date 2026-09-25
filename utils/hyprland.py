from fabric.hyprland.widgets import get_hyprland_connection
from fabric.utils import logger

from utils.functions import normalize_address, parse_hyprland_reply
from utils.singleton import SingletonMixin


class HyprlandService(SingletonMixin):
    """Singleton service for all Hyprland IPC interactions.

    Centralises connection management, query methods, and dispatch helpers
    so widgets no longer call ``get_hyprland_connection()`` directly.
    """


    def __init__(self):
        if not self._init_once():
            return
        self._connection = get_hyprland_connection()

    # ── Connection access (for event subscription etc.) ────────────

    @property
    def connection(self):
        """The raw Fabric Hyprland connection — only for consumers that
        need ``bulk_connect`` or direct signal subscription."""
        return self._connection

    @property
    def ready(self) -> bool:
        return self._connection.ready

    def connect(self, signal: str, callback) -> int:
        """Subscribe to a Hyprland event signal.

        Returns the handler id (pass to ``disconnect`` later).
        """
        return self._connection.connect(signal, callback)

    def disconnect(self, handler_id: int):
        self._connection.disconnect(handler_id)

    @staticmethod
    def _send_noop(*_):
        pass

    def send_command_async(self, command: str, callback=None):
        """Send a raw hyprctl command asynchronously."""
        self._connection.send_command_async(command, callback or self._send_noop)

    def on_ready(self, callback):
        """Invoke *callback* when the Hyprland socket is ready.

        If already ready, calls immediately; otherwise subscribes to
        the ``event::ready`` signal.
        """
        if self._connection.ready:
            callback()
        else:
            self._connection.connect("event::ready", lambda *_: callback())

    # ── Query helpers ─────────────────────────────────────────────

    def _parse_and_callback(self, reply, callback):
        try:
            data = parse_hyprland_reply(reply)
            callback(data)
        except Exception as e:
            logger.exception(f"[HyprlandService] Parse error: {e}")
            callback(None)

    def get_clients_async(self, callback):
        """Fetch ``j/clients`` and pass the parsed list to *callback*."""
        self._connection.send_command_async(
            "j/clients",
            lambda reply: self._parse_and_callback(reply, callback),
        )

    def get_monitors_async(self, callback):
        """Fetch ``j/monitors`` and pass the parsed list to *callback*."""
        self._connection.send_command_async(
            "j/monitors",
            lambda reply: self._parse_and_callback(reply, callback),
        )

    def get_active_workspace_async(self, callback):
        """Fetch ``j/activeworkspace`` and pass the parsed dict to *callback*."""
        self._connection.send_command_async(
            "j/activeworkspace",
            lambda reply: self._parse_and_callback(reply, callback),
        )

    def get_active_window_async(self, callback):
        """Fetch ``j/activewindow`` and pass the parsed dict to *callback*."""
        self._connection.send_command_async(
            "j/activewindow",
            lambda reply: self._parse_and_callback(reply, callback),
        )

    def get_devices_async(self, callback):
        """Fetch ``j/devices`` and pass the parsed dict to *callback*."""
        self._connection.send_command_async(
            "j/devices",
            lambda reply: self._parse_and_callback(reply, callback),
        )

    def get_submap_async(self, callback):
        """Fetch current submap and pass the string to *callback*.

        ``hyprctl submap`` returns a plain string, not JSON, so this
        uses its own reply handler instead of ``_parse_and_callback``.
        """
        self._connection.send_command_async(
            "submap",
            lambda reply: self._on_submap_reply(reply, callback),
        )

    def _on_submap_reply(self, reply, callback):
        try:
            data = reply.reply.decode().strip("\n").strip('"')
            callback(data)
        except Exception as e:
            logger.exception(f"[HyprlandService] Failed to parse submap reply: {e}")
            callback(None)

    # ── Dispatch helpers ──────────────────────────────────────────

    def focus_window(self, address: str):
        self._connection.send_command_async(
            f"dispatch focuswindow address:{address}",
            lambda *_: None,
        )

    def close_window(self, address: str):
        self._connection.send_command_async(
            f"dispatch closewindow address:{address}",
            lambda *_: None,
        )

    def move_window_to_workspace(self, address: str, workspace: int):
        self._connection.send_command_async(
            f"dispatch movetoworkspace {workspace},address:{address}",
            lambda *_: None,
        )

    def toggle_floating(self, address: str):
        self._connection.send_command_async(
            f"dispatch togglefloating address:{address}",
            lambda *_: None,
        )

    def set_fullscreen(self, active: bool):
        val = "1" if active else "0"
        self._connection.send_command_async(
            f"dispatch fullscreen {val}",
            lambda *_: None,
        )


# Module-level singleton for convenient imports
hyprland_service = HyprlandService()


class HyprlandClient:
    """Lightweight Hyprland client (window) adapter.

    Wraps a single window's data dict from Hyprland's ``j/clients``
    and delegates IPC commands to the shared ``HyprlandService``
    singleton — callers no longer need to pass a connection.
    """

    __slots__ = ("_active", "_data")

    def __init__(self, data: dict, active_address: str | None = None):
        self._data = data
        self._active = normalize_address(data.get("address")) == active_address

    @property
    def raw_data(self) -> dict:
        """Return the underlying Hyprland client data dict.

        Exposed for code that needs spatial fields (``size``, ``at``,
        ``workspace``, ``monitor``) not available via the typed API.
        """
        return self._data

    def get_app_id(self) -> str:
        return self._data.get("initialClass") or self._data.get("class") or ""

    def get_title(self) -> str:
        return self._data.get("title") or self.get_app_id()

    def get_address_str(self) -> str | None:
        return normalize_address(self._data.get("address"))

    def get_fullscreen(self) -> bool:
        return bool(self._data.get("fullscreen", False))

    def get_activated(self) -> bool:
        return self._active

    def set_activated(self, active: bool):
        self._active = active

    # ── Window actions ────────────────────────────────────────────

    def activate(self):
        addr = self.get_address_str()
        if addr:
            hyprland_service.focus_window(addr)

    def close(self):
        addr = self.get_address_str()
        if addr:
            hyprland_service.close_window(addr)

    def fullscreen(self):
        self.activate()
        hyprland_service.set_fullscreen(True)

    def unfullscreen(self):
        self.activate()
        hyprland_service.set_fullscreen(False)
