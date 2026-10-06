from fabric.utils import logger

from shared.widget_container import ButtonWidget
from utils.constants import get_kblayout_map
from utils.hyprland import hyprland_service


class KeyboardLayoutWidget(ButtonWidget):
    """A widget to display the current keyboard layout."""

    def __init__(self, **kwargs):
        super().__init__(name="keyboard", **kwargs)

        self.label_format = self.config.get("label_format", "{layout}")
        self.add_formatted_label(self.label_format)

        # all aboard...
        hyprland_service.on_ready(lambda: self.on_ready(None))

    def on_ready(self, _):
        self._get_keyboard()
        logger.info("[Keyboard] Connected to the hyprland socket")

    def _refresh_layout(self, layout: str) -> None:
        """Re-render the one panel label with the layout name."""
        self.refresh_formatted_label(layout=layout)

    def _handle_devices_data(self, data, *_):
        if data is None:
            return
        try:
            keyboards = data.get("keyboards", [])
            if not keyboards:
                self._refresh_layout("Unknown")
                logger.warning("[Keyboard] No keyboards found in the data")
                return

            main_kb = next((kb for kb in keyboards if kb.get("main")), keyboards[-1])

            layout = main_kb["active_keymap"]

            label = get_kblayout_map().get(layout, layout)

            if self.config.get("tooltip", False) and self.tooltips_enabled:
                caps = "On" if main_kb["capsLock"] else "Off"
                num = "On" if main_kb["numLock"] else "Off"
                self.set_tooltip_if_enabled(
                    f"Layout: {layout} | Caps Lock 󰪛: {caps} | Num Lock : {num}"
                )

            self._refresh_layout(label)
        except Exception as e:
            logger.exception(f"[Keyboard] Failed to parse keyboard data: {e}")

    def _get_keyboard(self):
        hyprland_service.get_devices_async(self._handle_devices_data)
