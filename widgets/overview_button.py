from shared.widget_container import ButtonWidget
from utils.i18n import _


class OverviewButtonWidget(ButtonWidget):
    """A widget to show the overview of all workspaces and windows."""

    def __init__(self, **kwargs):
        super().__init__(name="overview_button", **kwargs)

        self.set_tooltip_if_enabled(_("widget.overview_button.tooltip"))

        self.label_format = self.config.get("label_format", "{icon} overview")
        self.add_formatted_label(self.label_format, self.config.get("icon", ""))

        # Lazy-init overview popup
        self._overview_popup = None
        self.connect("clicked", self.on_click)

    def on_click(self, *_):
        from modules.overview import OverViewOverlay
        from utils.config import tsumiki_config

        if self._overview_popup is None:
            self._overview_popup = OverViewOverlay(tsumiki_config)
        self._overview_popup.toggle_popup()
