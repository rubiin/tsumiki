from fabric.bluetooth import BluetoothClient

from shared.widget_container import ButtonWidget
from utils.i18n import _
from utils.icons import get_text_icon


class BlueToothWidget(ButtonWidget):
    """A widget to display the Bluetooth status."""

    def __init__(self, **kwargs):
        super().__init__(name="bluetooth", **kwargs)

        self.icons = get_text_icon("bluetooth", "")

        self.label_format = self.config.get("label_format", "")
        self.add_formatted_label(self.label_format, self.icons["enabled"])

        self.bluetooth_client = BluetoothClient()
        self._register_handlers(
            self.bluetooth_client,
            {"changed": self.update_bluetooth_status},
        )

        self.update_bluetooth_status()

    def update_bluetooth_status(self, *_args):
        bt_status = "on" if self.bluetooth_client.enabled else "off"

        icon = self.icons["enabled"] if bt_status == "on" else self.icons["disabled"]

        self.refresh_formatted_label(icon)

        self.set_tooltip_if_enabled(_("widget.bluetooth.tooltip"))
