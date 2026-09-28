from typing import ClassVar

from fabric.utils import GObject, cooldown

from services.brightness import BrightnessService
from utils.widget_utils import (
    get_brightness_icon_name,
)

from ..osd import GenericOSDContainer


class BrightnessOSDContainer(GenericOSDContainer):
    """A widget to display the OSD for brightness."""

    __gsignals__: ClassVar = {
        "brightness-changed": (GObject.SignalFlags.RUN_FIRST, None, (int,))
    }

    def __init__(self, config: dict, **kwargs):
        super().__init__(
            config=config,
            **kwargs,
        )
        self.brightness_service = BrightnessService()
        self.config = config

        self.update_brightness()
        self._watch_brightness()

    def _watch_brightness(self) -> None:
        """Tracked so a rebuilt bar drops the handler with the widget."""
        self._register_handlers(
            self.brightness_service,
            {"brightness_changed": self.on_brightness_changed},
        )

    @cooldown(0.1)
    def update_brightness(self):
        brightness_percent = self.brightness_service.screen_brightness_percentage
        self.update_values(brightness_percent)
        self.update_icon(int(brightness_percent))

    def update_icon(self, current_brightness: int):
        icon_name = get_brightness_icon_name(current_brightness)["icon"]
        self.icon.set_from_icon_name(icon_name, self.icon_size)

    def on_brightness_changed(self, *_):
        self.update_brightness()
        self.emit("brightness-changed", 0)
