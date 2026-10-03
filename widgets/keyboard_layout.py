from fabric.utils import logger
from fabric.widgets.label import Label

from shared.widget_container import ButtonWidget
from utils.constants import get_kblayout_map
from utils.hyprland import hyprland_service
from utils.i18n import _
from utils.widget_utils import nerd_font_icon


class KeyboardLayoutWidget(ButtonWidget):
    """A widget to display the current keyboard layout."""

    def __init__(self, **kwargs):
        super().__init__(name="keyboard", **kwargs)

        self.kb_label = Label(
            label=_("widget.keyboard.label"), style_classes="panel-text"
        )

        if self.format_shows_icon():
            # Create a TextIcon with the specified icon and size
            self.icon = nerd_font_icon(
                icon=self.config.get("icon"),
                props={"style_classes": ["panel-font-icon"]},
            )
            self.container_box.add(self.icon)

        self.container_box.add(self.kb_label)

        # all aboard...
        hyprland_service.on_ready(lambda: self.on_ready(None))

    def on_ready(self, _):
        self._get_keyboard()
        logger.info("[Keyboard] Connected to the hyprland socket")

    def _handle_devices_data(self, data, *_):
        if data is None:
            return
        try:
            keyboards = data.get("keyboards", [])
            if not keyboards:
                self.kb_label.set_label("Unknown")
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

            self.kb_label.set_label(label)
        except Exception as e:
            logger.exception(f"[Keyboard] Failed to parse keyboard data: {e}")

    def _get_keyboard(self):
        hyprland_service.get_devices_async(self._handle_devices_data)
