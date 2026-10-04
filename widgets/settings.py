"""Settings button widget to open the settings GUI."""

from modules.settings_gui import open_settings
from shared.widget_container import ButtonWidget
from utils.i18n import _


class SettingsWidget(ButtonWidget):
    """A widget to open the settings panel."""

    def __init__(self, **kwargs):
        super().__init__(name="settings", **kwargs)

        self.label_format = self.config.get("label_format", "{icon} Settings")
        self.add_formatted_label(self.label_format, self.config.get("icon", "󰒓"))

        self.set_tooltip_if_enabled(_("widget.settings.tooltip"), default=True)

        self.connect("clicked", lambda *_: open_settings())
