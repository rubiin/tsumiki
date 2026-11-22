"""Shared base for circular-progress widgets that respond to scroll."""

from shared.widget_container import EventBoxWidget
from utils.icons import get_text_icon
from utils.widget_utils import create_progress, nerd_font_icon


class ScrollableProgressWidget(EventBoxWidget):
    """Provide the icon + progress layout; subclasses handle scroll and reading."""

    def __init__(
        self,
        name: str,
        icon_name: str,
        icon_style_classes: list[str],
        events: list[str] | None = None,
        **kwargs,
    ):
        super().__init__(
            name=name,
            events=events or ["scroll", "smooth-scroll"],
            **kwargs,
        )

        self.icon = nerd_font_icon(
            icon=get_text_icon(icon_name, ""),
            props={"style_classes": icon_style_classes},
        )

        self.progress_bar = create_progress(
            child=self.icon,
            value=kwargs.pop("initial_progress", 0.0),
        )

        self.container_box.add(self.progress_bar)

    def update_progress(self, normalized_value: float, icon_text: str):
        """Update the circular progress bar and icon text."""
        self.progress_bar.set_value(normalized_value)
        self.progress_bar.animate_value(normalized_value)
        self.icon.set_text(icon_text)
