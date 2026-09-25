from fabric.bluetooth import BluetoothClient
from fabric.widgets.label import Label

from shared.widget_container import ButtonWidget
from utils.i18n import _
from utils.icons import get_text_icon
from utils.widget_utils import nerd_font_icon


class BlueToothWidget(ButtonWidget):
    """A widget to display the Bluetooth status."""

    def __init__(self, **kwargs):
        super().__init__(name="bluetooth", **kwargs)

        self.icons = get_text_icon("bluetooth", "")

        self.bluetooth_icon = nerd_font_icon(
            icon=self.icons["enabled"],
            props={"style_classes": ["panel-font-icon"]},
        )

        self.container_box.add(
            self.bluetooth_icon,
        )

        if self.config.get("label", True):
            self.bt_label = Label(label=_("common.on"), style_classes="panel-text")
            self.container_box.add(self.bt_label)

        self.bluetooth_client = BluetoothClient()
        self._register_handlers(
            self.bluetooth_client,
            {"changed": self.update_bluetooth_status},
        )

        self.update_bluetooth_status()

    def update_bluetooth_status(self, *_args):
        bt_status = "on" if self.bluetooth_client.enabled else "off"

        icon = self.icons["enabled"] if bt_status == "on" else self.icons["disabled"]

        self.bluetooth_icon.set_label(icon)

        if self.config.get("label", True):
            self.bt_label.set_text(bt_status.capitalize())

        self.set_tooltip_if_enabled(_("widget.bluetooth.tooltip"))
