from fabric.utils import logger

from services import style_service
from shared.widget_container import ButtonWidget
from utils.colors import Colors
from utils.functions import send_notification
from utils.i18n import _


class ThemeSwitcherWidget(ButtonWidget):
    """A widget to cycle through available themes."""

    def __init__(self, **kwargs):
        super().__init__(name="theme_switcher", **kwargs)

        self._style_service = style_service

        # Get current theme from service
        self._current_theme = self._style_service.current_theme

        self.label_format = self.config.get("label_format", "\ue22b")
        self.add_formatted_label(self.label_format)

        self.set_tooltip_text(self._current_theme)
        self.connect("clicked", self.on_click)

        # Keep tooltip in sync with theme changes
        self._style_service.connect("theme_changed", self._on_theme_changed)

    def _on_theme_changed(self, _service, theme_name: str):
        """Keep the tooltip and the panel label in sync with the theme."""
        self._current_theme = theme_name
        self.set_tooltip_text(theme_name)
        self.refresh_formatted_label(theme=theme_name)

    def on_click(self, *_args):
        """Cycle to the next theme via StyleService."""
        if not self._style_service.available_themes:
            logger.warning(f"{Colors.WARNING}[ThemeSwitcher] No themes available")
            return

        new_theme = self._style_service.next_theme()

        if self.config.get("notify", True):
            send_notification("Tsumiki", _("widget.theme.switched", theme=new_theme))

        self.set_tooltip_text(new_theme)
