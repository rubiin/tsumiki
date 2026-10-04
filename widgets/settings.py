"""Settings button widget to open the settings GUI."""

from modules.settings_gui import open_settings
from shared.widget_container import ButtonWidget
from utils.i18n import _
from utils.widget_utils import nerd_font_icon


class SettingsWidget(ButtonWidget):
    """A widget to open the settings panel."""

    def __init__(self, **kwargs):
        super().__init__(name="settings", **kwargs)

        self.add_panel_content(
            nerd_font_icon(
                icon=self.config.get("icon", "󰒓"),
                props={"style_classes": ["panel-font-icon"]},
            )
            if self.format_shows_icon()
            else None,
            _("widget.settings.label"),
        )

        self.set_tooltip_if_enabled(_("widget.settings.tooltip"), default=True)

        self.connect("clicked", lambda *_: open_settings())
