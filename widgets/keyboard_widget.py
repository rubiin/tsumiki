from services import keyboard_service
from shared.widget_container import ButtonWidget
from utils.constants import get_kblayout_map


def layout_display_name(layout: str, name_map: dict[str, str] | None = None) -> str:
    """Resolve a layout to its label, letting user names win over the built-in map."""
    if name_map and layout in name_map:
        return name_map[layout]
    return get_kblayout_map().get(layout, layout)


class KeyboardWidget(ButtonWidget):
    """A widget to display the current keyboard layout and lock keys."""

    def __init__(self, **kwargs):
        super().__init__(name="keyboard", **kwargs)

        self.label_format = self.config.get("label_format", "{layout}")
        self.name_map = self.config.get("language_name_map", {})
        self._service = keyboard_service

        self.add_formatted_label(self.label_format)
        self._render()
        self._update_tooltip()

        self._register_handlers(
            self._service,
            {
                "notify::layout-name": self._on_layout_changed,
                "notify::caps-lock": self._on_lock_changed,
                "notify::num-lock": self._on_lock_changed,
            },
        )

    def _on_layout_changed(self, *_):
        self._render()
        self._update_tooltip()

    def _on_lock_changed(self, *_):
        self._render()
        self._update_tooltip()

    def _render(self) -> None:
        """Re-render the panel label from the service's live state."""
        layout = self._service.layout_name
        display = layout_display_name(layout, self.name_map) if layout else "Unknown"
        self.refresh_formatted_label(
            layout=display,
            caps_state="on" if self._service.caps_lock else "off",
            num_state="on" if self._service.num_lock else "off",
        )

    def _update_tooltip(self) -> None:
        caps = "On" if self._service.caps_lock else "Off"
        num = "On" if self._service.num_lock else "Off"
        self.set_tooltip_if_enabled(
            f"Layout: {self._service.layout_name} | "
            f"Caps Lock 󰪛: {caps} | Num Lock : {num}"
        )
