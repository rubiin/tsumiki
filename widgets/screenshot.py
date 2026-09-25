
from services.screen_record import ScreenRecorderService
from shared.widget_container import ButtonWidget
from utils.i18n import _


class ScreenShotWidget(ButtonWidget):
    """A widget to switch themes."""

    def __init__(self, **kwargs):
        super().__init__(name="screenshot", **kwargs)

        self.initialized = False

        self.recorder_service = None

        self.add_panel_content(
            self.config.get("icon"),
            _("widget.screenshot.label"),
            show_label=self.config.get("label", True),
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
