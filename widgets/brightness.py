from fabric.utils import cooldown

import utils.functions as helpers
from services.brightness import BrightnessService
from shared.scrollable_progress import ScrollableProgressWidget
from utils.widget_utils import get_brightness_icon_name


class BrightnessWidget(ScrollableProgressWidget):
    """A widget that displays and controls the brightness."""

    def __init__(self, **kwargs):
        self._brightness_service = BrightnessService()

        normalized_brightness = helpers.convert_to_percent(
            self._brightness_service.screen_brightness,
            self._brightness_service.max_screen,
        )

        super().__init__(
            name="brightness",
            icon_name="brightness.medium",
            icon_style_classes=["panel-font-icon", "progress-bar-icon"],
            initial_progress=normalized_brightness / 100,
            **kwargs,
        )

        # Connect the brightness service to update the progress bar
        self._register_handlers(
            self._brightness_service,
            {"brightness_changed": self.on_brightness_changed},
        )

        # Connect the event box to handle scroll events
        self.connect("scroll-event", self.on_scroll)

    @cooldown(1)
    def on_scroll(self, _, event):
        # Adjust the brightness based on the scroll direction
        val_y = event.delta_y
        step_pct = self.config.get("step_size", 5)
        max_screen = self._brightness_service.max_screen
        raw_step = int((step_pct / 100) * max_screen) if max_screen > 0 else 0

        if val_y > 0:
            self._brightness_service.screen_brightness += raw_step
        else:
            self._brightness_service.screen_brightness -= raw_step

    def on_brightness_changed(self, *_):
        brightness = helpers.convert_to_percent(
            self._brightness_service.screen_brightness,
            self._brightness_service.max_screen,
        )

        self.update_progress(
            brightness / 100,
            get_brightness_icon_name(brightness)["icon_text"],
        )

        self.set_tooltip_if_enabled(f"{brightness}%")
