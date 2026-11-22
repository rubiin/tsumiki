from fabric.bluetooth import BluetoothClient

from shared.widget_container import ButtonWidget
from utils.i18n import _
from utils.icons import get_icon


class BlueToothWidget(ButtonWidget):
    """A widget to display the Bluetooth status."""

    def __init__(self, **kwargs):
        super().__init__(name="bluetooth", **kwargs)

        self._resolve_icons()

        self.label_format = self.config.get("label_format", "")
        self.add_formatted_label(self.label_format, self.icons["enabled"], state="on")

        self.bluetooth_client = BluetoothClient()
        self._register_handlers(
            self.bluetooth_client,
            {"changed": self.update_bluetooth_status},
        )

        self.update_bluetooth_status()

    def _resolve_icons(self):
        """Resolve the on/off glyphs, preferring configured overrides."""
        self.icons = {
            "enabled": self.config.get("enabled_icon")
            or get_icon("bluetooth.enabled", "󰂱"),
            "disabled": self.config.get("disabled_icon")
            or get_icon("bluetooth.disabled", "󰂲"),
        }

    def update_bluetooth_status(self, *_args):
        bt_status = "on" if self.bluetooth_client.enabled else "off"

        icon = self.icons["enabled"] if bt_status == "on" else self.icons["disabled"]

        self.refresh_formatted_label(icon, state=bt_status)

        self.set_tooltip_if_enabled(_("widget.bluetooth.tooltip"))
