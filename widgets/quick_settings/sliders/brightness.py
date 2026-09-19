from fabric.utils import cooldown

from services.brightness import BrightnessService
from shared.setting_scale import SettingSlider
from utils.icons import get_text_icon
from utils.widget_utils import get_brightness_icon_name


class BrightnessSlider(SettingSlider):
    """A widget to display a scale for brightness settings."""

    def __init__(
        self,
    ):
        self.client = BrightnessService()
        super().__init__(
            pixel_size=20,
            icon_name=get_text_icon("brightness.medium", "󰃟"),
            start_value=self.client.screen_brightness_percentage,
        )

        if self.client.screen_brightness == -1:
            self.destroy()
            return

        self._destroyed = False
        self._brightness_handler_id = None
        if self.scale:
            self.scale.connect("change-value", self.on_scale_move)
            self._brightness_handler_id = self.client.connect(
                "brightness_changed", self.on_brightness_change
            )

        self.icon_button.connect("clicked", self.reset)
        self.connect("destroy", self._on_destroy)

    def _on_destroy(self, *_):
        self._destroyed = True
        if self._brightness_handler_id is not None:
            self.client.disconnect(self._brightness_handler_id)
            self._brightness_handler_id = None

    def reset(self, *_):
        """Reset the brightness to the default value."""
        self.client.screen_brightness = 0

    @cooldown(0.1)
    def on_scale_move(self, _, __, moved_pos: float):
        # Convert percentage (0-100) to raw brightness value (0-max_screen)
        raw_value = int((moved_pos / 100) * self.client.max_screen)
        self.client.screen_brightness = raw_value

    def on_brightness_change(self, service: BrightnessService, _):
        if self._destroyed:
            return
        brightness_percent = service.screen_brightness_percentage

        # Avoid unnecessary updates if the value hasn't changed
        if brightness_percent == round(self.scale.get_value()):
            return

        self.scale.set_value(brightness_percent)
        self.scale.set_tooltip_text(f"{brightness_percent}%")

        self.update_icon(int(brightness_percent))

    def update_icon(self, current_brightness: int):
        icon_name = get_brightness_icon_name(current_brightness)["icon_text"]
        self.icon.set_label(icon_name)
