from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label

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
        name = kwargs.pop("name", "setting-slider")
        super().__init__(
            name=name,
            **kwargs,
        )
        # Box.__init__ skips BoxWidget's, so the config-derived flags are set here.
        self._init_widget_settings(name)
        self.pixel_size = pixel_size
        self.icon = nerd_font_icon(
            icon=icon_name,
            props={
                "style_classes": ["panel-font-icon", "shortcut-icon"],
                "style": f"font-size: {self.pixel_size}px;",
            },
        )

        self.icon_button = HoverButton(image=self.icon, name="setting-slider-button")

        # Non-expanding scale: CSS min-width is the single source of truth for
        # track length, so every row's track is identical regardless of extras.
        self.scale = create_scale(
            name="setting-slider-scale",
            duration=0.8,
            curve=(0.34, 1.56, 0.64, 1.0),
            value=start_value,
            increments=(1, 1),
            min_value=min,
            max_value=max,
            h_expand=False,
            h_align="start",
        )
        self.value_label = Label(
            name="setting-slider-value",
            label=f"{round(start_value)}%",
            v_align="center",
        )
        self.center_box = CenterBox(
            start_children=self.icon_button,
            center_children=Box(children=(self.scale, self.value_label)),
        )
        self.children = (self.center_box,)

    def set_value_label(self, value: float) -> None:
        """Show *value* as a percentage after the scale."""
        self.value_label.set_label(f"{round(value)}%")

    def set_scale_tooltip(self, text: str) -> None:
        """Set the scale's value tooltip, honouring the global tooltip switch.

        The scale is a plain Gtk widget, so it cannot use the BaseWidget helper
        that puts the tooltip on ``self``.
        """
        if self.tooltips_enabled:
            self.scale.set_tooltip_text(text)
