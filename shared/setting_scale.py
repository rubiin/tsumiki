from fabric.widgets.box import Box

from utils.icons import get_text_icon
from utils.widget_utils import create_scale, nerd_font_icon

from .buttons import HoverButton
from .widget_container import BaseWidget


class SettingSlider(Box, BaseWidget):
    """A widget to display a scale for quick settings."""

    def __init__(
        self,
        min: float = 0,
        max: float = 100,
        start_value: float = 50,
        icon_name: str = get_text_icon("fallback", ""),
        pixel_size: int = 18,
        **kwargs,
    ):
        super().__init__(
            name="setting-slider",
            **kwargs,
        )
        self.pixel_size = pixel_size
        self.icon = nerd_font_icon(
            icon=icon_name,
            props={
                "style_classes": ["panel-font-icon", "shortcut-icon"],
                "style": f"font-size: {self.pixel_size}px;",
            },
        )

        self.icon_button = HoverButton(image=self.icon, name="setting-slider-button")

        self.scale = create_scale(
            name="setting-slider-scale",
            duration=0.8,
            curve=(0.34, 1.56, 0.64, 1.0),
            value=start_value,
            increments=(1, 1),
            tooltip_text=str(start_value),
            min_value=min,
            max_value=max,
        )
        self.children = (self.icon_button, self.scale)
