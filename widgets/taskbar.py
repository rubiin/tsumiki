from time import monotonic

from fabric.utils import GLib, logger
from fabric.widgets.button import Button
from fabric.widgets.image import Image

from shared.buttons import HoverButton
from shared.widget_container import BoxWidget
from utils.functions import normalize_address
from utils.hyprland import HyprlandClient, hyprland_service
from utils.icon_resolver import IconResolver

SYNC_DEBOUNCE_MS = 60
_FADE_FRAME_MS = 16
_FADE_MS = 150

_BUTTON_BASE_CLASSES = ["buttons-basic", "buttons-transition"]


class TaskBarWidget(BoxWidget):
    """A widget to display the taskbar items."""

    def __init__(self, **kwargs):
        super().__init__(
            name="taskbar",
            **kwargs,
        )
        self._service = hyprland_service
        self._hyprland_connection = self._service.connection
        self._show_current_workspace_only = self.config.get(
            "show_current_workspace_only", False
        )
        self._hide_special_workspace_apps = self.config.get(
            "hide_special_workspace_apps", False
        )

        self._clients_by_address: dict[str, HyprlandClient] = {}
        self._client_buttons: dict[str, dict] = {}  # address -> {button, image, client}
        self._active_address: str | None = None
        self._current_workspace_id: int | None = None
        self._sync_scheduled_id: int | None = None
        self._sync_in_progress = False
        self._fade_sources: dict[object, int] = {}
        self._icon_resolver = IconResolver()

        events = {
            "event::openwindow": self._on_window_event,
            "event::closewindow": self._on_window_event,
            "event::activewindowv2": self._on_active_window_event,
            "event::windowtitle": self._on_window_event,
        }
        if self._show_current_workspace_only:
            events["event::workspace"] = self._on_workspace_event

        self._register_handlers(self._hyprland_connection, events)

        self.connect("destroy", self._on_destroy)

        if self._hyprland_connection.ready:
            self._sync_clients()
        else:
            self._register_handlers(
                self._hyprland_connection,
                {"event::ready": lambda *_: self._schedule_sync(delay_ms=0)},
            )

    def _on_destroy(self, *_):
        if self._sync_scheduled_id is not None:
            GLib.source_remove(self._sync_scheduled_id)
            self._sync_scheduled_id = None
        for source_id in self._fade_sources.values():
            GLib.source_remove(source_id)
        self._fade_sources.clear()

    # ── Event handlers ────────────────────────────────────────────

    def _on_window_event(self, *_):
        self._schedule_sync()

    def _on_workspace_event(self, *_):
        self._fetch_current_workspace(lambda _: self._schedule_sync())

    def _fetch_current_workspace(self, callback):
        try:
            self._service.get_active_workspace_async(
                lambda data: self._on_workspace_data(data, callback)
            )
        except Exception as e:
            logger.warning(f"[Taskbar] Failed to request active workspace: {e}")
            callback(None)

    def _on_workspace_data(self, data, callback):
        """Track the active workspace id, ignoring id 0 and failed fetches."""
        if not data:
            logger.warning("[Taskbar] Failed to parse workspace reply")
        else:
            ws_id = data.get("id")
            if isinstance(ws_id, int) and ws_id != 0:
                self._current_workspace_id = ws_id
        callback(self._current_workspace_id)

    def _on_active_window_event(self, *_):
        if not self._clients_by_address:
            self._schedule_sync(delay_ms=0)
            return

        event = _[1] if len(_) > 1 else None
        data = getattr(event, "data", None)
        if data is None:
            return

        if isinstance(data, (list, tuple)):
            data = ",".join(str(x) for x in data if x is not None)
        if not isinstance(data, str):
            return

        for token in reversed(data.split(",")):
            addr = normalize_address(token.strip())
            if addr:
                self._apply_active_state(addr)
                return

    # ── Debounced sync ────────────────────────────────────────────

    def _schedule_sync(self, delay_ms: int = SYNC_DEBOUNCE_MS):
        if self._sync_scheduled_id is not None:
            return
        if delay_ms <= 0:
            self._sync_clients()
            return
        self._sync_scheduled_id = GLib.timeout_add(delay_ms, self._run_scheduled_sync)

    def _run_scheduled_sync(self):
        self._sync_scheduled_id = None
        self._sync_clients()
        return False

    def _sync_clients(self):
        if self._sync_in_progress:
            self._schedule_sync()
            return
        self._sync_in_progress = True
        self._fetch_clients_async()

    def _fetch_clients_async(self):
        try:
            self._service.get_clients_async(self._on_raw_clients_reply)
        except Exception as e:
            logger.exception(f"[Taskbar] Failed to request clients: {e}")
            self._sync_in_progress = False

    def _on_raw_clients_reply(self, raw_clients):
        if raw_clients is None:
            logger.error("[Taskbar] Failed to parse clients")
            self._sync_in_progress = False
            return

        if self._active_address is None:
            self._fetch_active_address(
                lambda addr: self._process_clients(raw_clients, addr)
            )
        else:
            self._process_clients(raw_clients, self._active_address)

    def _fetch_active_address(self, callback):
        try:
            self._service.get_active_window_address_async(callback)
        except Exception as e:
            logger.warning(f"[Taskbar] Failed to request active window address: {e}")
            callback(None)

    def _process_clients(self, raw_clients, active_address):
        self._active_address = active_address
        if self._show_current_workspace_only and self._current_workspace_id is None:
            self._fetch_current_workspace(
                lambda _: self._process_clients(raw_clients, active_address)
            )
            return

        try:
            clients = self._service.get_wm_clients(
                raw_clients,
                active_address,
                ignored=self.config.get("ignored", []),
                hide_special=self._hide_special_workspace_apps,
                workspace_id=(
                    self._current_workspace_id
                    if self._show_current_workspace_only
                    else None
                ),
            )
            self._clients_by_address = self._service.index_clients(clients)

            # Remove stale buttons
            for address in list(self._client_buttons):
                if address not in self._clients_by_address:
                    self._remove_button(self._client_buttons.pop(address))

            # Add/update buttons
            for address, client in self._clients_by_address.items():
                if address in self._client_buttons:
                    entry = self._client_buttons[address]
                    entry["client"] = client
                    self._update_button_visuals(entry, client)
                else:
                    self._add_client_button(address, client)
        finally:
            self._sync_in_progress = False

    # ── Button management ─────────────────────────────────────────

    @staticmethod
    def _set_button_active_state(button: Button, is_active: bool):
        button.set_style_classes(
            [*_BUTTON_BASE_CLASSES, "active"] if is_active else _BUTTON_BASE_CLASSES
        )

    def _client_tooltip(self, client: HyprlandClient) -> str | None:
        """Window title for a task button, or None when tooltips are off."""
        if not (self.config.get("tooltip", True) and self.tooltips_enabled):
            return None
        return client.get_title()

    def _update_button_visuals(self, entry: dict, client: HyprlandClient):
        entry["image"].set_from_pixbuf(
            self._icon_resolver.resolve_icon_pixbuf(
                client.get_app_id(), self.config.get("icon_size", 22)
            )
        )
        entry["button"].set_tooltip_text(self._client_tooltip(client))
        self._set_button_active_state(entry["button"], client.get_activated())

    def _add_client_button(self, address: str, client: HyprlandClient):
        client_image = Image()
        client_image.set_from_pixbuf(
            self._icon_resolver.resolve_icon_pixbuf(
                client.get_app_id(), self.config.get("icon_size", 22)
            )
        )

        client_button = HoverButton(
            style_classes=list(_BUTTON_BASE_CLASSES),
            image=client_image,
            on_button_press_event=lambda _, event, addr=address: self._activate_client(
                addr
            ),
        )
        client_button.set_tooltip_text(self._client_tooltip(client))

        self._set_button_active_state(client_button, client.get_activated())

        self._client_buttons[address] = {
            "button": client_button,
            "image": client_image,
            "client": client,
        }
        self.add(client_button)
        self._animate_opacity(client_button, 0.0, 1.0)

    def _remove_button(self, entry: dict):
        """Fade the entry out, then detach and destroy it."""
        self._animate_opacity(
            entry["button"], 1.0, 0.0, lambda: self._destroy_button(entry)
        )

    def _destroy_button(self, entry: dict):
        self.remove(entry["button"])
        entry["button"].destroy()
        entry["image"].destroy()

    def _animate_opacity(self, widget, start: float, end: float, on_done=None):
        self._cancel_fade(widget)
        started = monotonic()

        def step() -> bool:
            progress = min(1.0, (monotonic() - started) * 1000 / _FADE_MS)
            widget.set_opacity(start + (end - start) * progress)
            if progress < 1.0:
                return True
            self._fade_sources.pop(widget, None)
            if on_done is not None:
                on_done()
            return False

        self._fade_sources[widget] = GLib.timeout_add(_FADE_FRAME_MS, step)

    def _cancel_fade(self, widget) -> None:
        source_id = self._fade_sources.pop(widget, None)
        if source_id is not None:
            GLib.source_remove(source_id)

    def _activate_client(self, address: str):
        """Activate a client by address at click time (avoids stale closure)."""
        client = self._clients_by_address.get(address)
        if client:
            client.activate()

    def _apply_active_state(self, active_address: str | None):
        self._active_address = active_address

        for address, client in self._clients_by_address.items():
            client.set_activated(address == active_address)

        for address, entry in self._client_buttons.items():
            client = self._clients_by_address.get(address)
            if client:
                self._set_button_active_state(entry["button"], client.get_activated())
                entry["button"].set_tooltip_text(self._client_tooltip(client))
