from services.screen_record import ScreenRecorderService
from shared.widget_container import ButtonWidget
from utils.i18n import _
from utils.widget_utils import nerd_font_icon


class ScreenShotWidget(ButtonWidget):
    """A widget to switch themes."""

    def __init__(self, **kwargs):
        super().__init__(name="screenshot", **kwargs)

        self.initialized = False

        self.recorder_service = None

        self.add_panel_content(
            nerd_font_icon(
                icon=self.config.get("icon"),
                props={"style_classes": ["panel-font-icon"]},
            )
            if self.format_shows_icon()
            else None,
            _("widget.screenshot.label"),
        )

        self.set_tooltip_if_enabled(_("widget.screenshot.tooltip"))

        self.connect("clicked", self.on_click)

    def lazy_init(self, *_):
        if not self.initialized:
            self.recorder_service = ScreenRecorderService()
            self.initialized = True

    def on_click(self, *_):
        """Start recording the screen."""
        self.lazy_init()

        if not self.initialized:
            return  # Early exit if script not available

        self.recorder_service.screenshot(
            config=self.config,
        )
