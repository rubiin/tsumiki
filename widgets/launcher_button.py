from shared.widget_container import ButtonWidget
from utils.i18n import _


class LauncherButton(ButtonWidget):
    """Button widget to launch the application launcher."""

    def __init__(self, **kwargs):
        super().__init__(name="launcher_button", **kwargs)

        self.launcher = None

        self.label_format = self.config.get("label_format", "\uf003b")
        self.add_formatted_label(self.label_format)

        self.set_tooltip_if_enabled(_("widget.launcher_button.tooltip"), default=True)

        self.connect("clicked", self.on_click)

    def _get_or_create_launcher(self):
        """Get or create the app launcher instance."""
        from modules.launcher import Launcher
        from utils.config import tsumiki_config

        if self.launcher is None:
            self.launcher = Launcher(tsumiki_config)

        return self.launcher

    def on_click(self, *_):
        """Toggle the app launcher visibility."""
        launcher = self._get_or_create_launcher()
        if launcher:
            launcher.toggle()
