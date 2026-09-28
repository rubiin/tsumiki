import re

from fabric.hyprland.widgets import get_hyprland_connection
from fabric.utils import logger

from utils.functions import normalize_address, parse_hyprland_reply
from utils.singleton import SingletonMixin

# /dispatch is Lua in 0.55+: a bare window address matches nothing, so use a selector.
_ADDRESS_RE = re.compile(r"\A0x[0-9a-fA-F]+\Z")


def _window_selector(address: str) -> str | None:
    """Return *address* as a Lua window selector, or None if it is unusable.

    The value lands in a Lua string literal, so non-hex input is rejected
    rather than escaped.
    """
    if not address or not _ADDRESS_RE.match(address):
        logger.error(f"[HyprlandService] Refusing to dispatch bad address {address!r}")
        return None
    return f'"address:{address}"'


class HyprlandService(SingletonMixin):
    """Singleton for all Hyprland IPC, so widgets never touch the connection."""

    def __init__(self):
        if not self._init_once():
            return
        self._connection = get_hyprland_connection()

    # ── Connection access (for event subscription etc.) ────────────

    @property
    def connection(self):
        """The raw connection — only for ``bulk_connect`` or direct signals."""
        return self._connection

    @property
    def ready(self) -> bool:
        return self._connection.ready

    def connect(self, signal: str, callback) -> int:
        """Subscribe to a Hyprland event; returns the id for ``disconnect``."""
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
        """Call *callback* once the socket is ready (immediately if it is)."""
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
        """Fetch the current submap and pass the string to *callback*.

        ``hyprctl submap`` returns a plain string, not JSON, so it needs its
        own reply handler.
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

    def _dispatch(self, lua: str) -> None:
        """Run a ``hl.dsp.*`` expression, logging anything but a clean ack.

        Hyprland answers a bad dispatch with an error string, and dropping it
        is how a wholesale API break stayed invisible.
        """
        self._connection.send_command_async(f"dispatch {lua}", self._on_dispatch_reply)

    @staticmethod
    def _on_dispatch_reply(reply) -> None:
        if reply.reply != b"ok":
            logger.error(
                f"[HyprlandService] dispatch rejected: "
                f"{reply.command} -> {reply.reply.decode(errors='replace')}"
            )

    def _dispatch_to_window(self, template: str, address: str) -> None:
        """Send *template* with ``WINDOW`` replaced by *address*'s selector."""
        selector = _window_selector(address)
        if selector is not None:
            self._dispatch(template.replace("WINDOW", selector))

    def focus_window(self, address: str):
        self._dispatch_to_window("hl.dsp.focus({window=WINDOW})", address)

    def close_window(self, address: str):
        self._dispatch_to_window("hl.dsp.window.close({window=WINDOW})", address)

    def close_windows_by_class(self, window_class: str) -> None:
        """Close every window whose class regex matches *window_class*."""
        if not window_class:
            return
        self._dispatch(f'hl.dsp.window.close({{window="class:{window_class}"}})')

    def move_window_to_workspace(
        self, address: str, workspace: int, silent: bool = False
    ):
        # follow=false is movetoworkspacesilent: the window moves, focus stays.
        follow = "false" if silent else "true"
        self._dispatch_to_window(
            f"hl.dsp.window.move({{workspace={workspace}, follow={follow}, "
            "window=WINDOW})",
            address,
        )

    def toggle_floating(self, address: str):
        self._dispatch_to_window(
            'hl.dsp.window.float({action="toggle", window=WINDOW})', address
        )

    def set_fullscreen(self, active: bool):
        action = "set" if active else "unset"
        self._dispatch(
            f'hl.dsp.window.fullscreen({{mode="fullscreen", action="{action}"}})'
        )


# Module-level singleton for convenient imports
hyprland_service = HyprlandService()


class HyprlandClient:
    """Window adapter over one ``j/clients`` entry, delegating IPC to the singleton."""

    __slots__ = ("_active", "_data")

    def __init__(self, data: dict, active_address: str | None = None):
        self._data = data
        self._active = normalize_address(data.get("address")) == active_address

    @property
    def raw_data(self) -> dict:
        """The raw client dict, for spatial fields absent from the typed API."""
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
