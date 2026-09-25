"""Settings button widget to open the settings GUI."""


from modules.settings_gui import open_settings
from shared.widget_container import ButtonWidget
from utils.i18n import _


class SettingsWidget(ButtonWidget):
    """A widget to open the settings panel."""

    def __init__(self, **kwargs):
        super().__init__(name="settings", **kwargs)

        self.add_panel_content(
            self.config.get("icon", "󰒓"),
            _("widget.settings.label"),
            show_label=self.config.get("label", False),
        )

        self.set_tooltip_if_enabled(_("widget.settings.tooltip"), default=True)

        self.connect("clicked", lambda *_: open_settings())
