from collections.abc import Callable

from fabric.bluetooth.service import BluetoothClient, BluetoothDevice
from fabric.utils import Gtk, bulk_connect
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow

from services import bluetooth_service
from shared.buttons import HoverButton, QSChevronButton, ScanButton
from shared.list import ListBox
from shared.submenu import QuickSubMenu
from utils.i18n import _
from utils.icons import get_text_icon
from utils.widget_utils import nerd_font_icon


class BluetoothDeviceBox(CenterBox):
    """A widget to display a Bluetooth device in a box."""

    def __init__(self, device: BluetoothDevice, **kwargs):
        super().__init__(
            spacing=2,
            style_classes="submenu-button",
            h_expand=True,
            name="bluetooth-device-box",
            **kwargs,
        )
        self.device: BluetoothDevice = device

        self.icon_to_text_icon = {
            "audio-headset": get_text_icon("ui.headset", "󰋎"),
            "phone": get_text_icon("ui.phone", "󰏲"),
            "audio-headphones": get_text_icon("ui.headphones", "󰋋"),
            "keyboard": get_text_icon("ui.keyboard", ""),
            "mouse": get_text_icon("ui.mouse", ""),
            "audio-speakers": get_text_icon("ui.speakers", "󰓃"),
            "camera": get_text_icon("ui.camera", ""),
            "printer": get_text_icon("ui.printer", "󰐪"),
            "tv": get_text_icon("ui.tv", ""),
            "watch": get_text_icon("ui.watch", ""),
            "bluetooth": get_text_icon("bluetooth.enabled", "󰂱"),
        }

        self.connect_button = HoverButton(style_classes="submenu-button")
        self.connect_button.connect(
            "clicked",
            lambda _: self.device.set_property("connecting", not self.device.connected),
        )

        self._device_handler_ids = bulk_connect(
            self.device,
            {
                "notify::connecting": self.on_device_connecting,
                "notify::connected": self.on_device_connect,
            },
        )
        self.connect("destroy", self._on_destroy)

        device_name = device.name or _("widget.bluetooth.unknown_device")

        self.add_start(
            nerd_font_icon(
                icon=self.icon_to_text_icon.get(
                    device.icon_name, get_text_icon("bluetooth.enabled", "󰂱")
                ),
                props={"style_classes": ["panel-font-icon"]},
            ),
        )

        self.add_start(
            Label(
                label=device_name,
                style_classes="submenu-item-label",
                ellipsization="end",
            )
        )

        self.add_end(self.connect_button)

        self.on_device_connect()

    def _on_destroy(self, *_):
        for handler_id in self._device_handler_ids:
            self.device.disconnect(handler_id)

    def on_device_connecting(self, *_args):
        if self.device.connecting:
            self.connect_button.set_label(_("widget.bluetooth.connecting"))
        elif self.device.connected is False:
            self.connect_button.set_label(_("widget.bluetooth.connect_failed"))

    def on_device_connect(self, *_args):
        if self.device.connected:
            self.connect_button.set_label(
                _("widget.bluetooth.disconnect"),
            )
        else:
            self.connect_button.set_label(
                _("widget.bluetooth.connect"),
            )


class BluetoothSubMenu(QuickSubMenu):
    """A submenu to display the Bluetooth settings."""

    def __init__(self, **kwargs):
        self.client = bluetooth_service
        self.client.connect("device-added", self.populate_new_device)

        self.paired_devices_listbox = ListBox(
            visible=True, name="paired-devices-listbox"
        )
        self.paired_devices_container = Box(
            orientation="v",
            spacing=10,
            h_expand=True,
            children=[
                Label(
                    label=_("widget.quick_settings.bluetooth.paired"),
                    h_align="start",
                    style_classes="panel-text",
                ),
                self.paired_devices_listbox,
            ],
        )

        self.available_devices_listbox = ListBox(
            visible=True, name="available-devices-listbox"
        )
        self.available_devices_container = Box(
            orientation="v",
            spacing=4,
            h_expand=True,
            children=[
                Label(
                    label=_("widget.quick_settings.bluetooth.available"),
                    h_align="start",
                    name="available-devices-label",
                    style_classes="panel-text",
                ),
                self.available_devices_listbox,
            ],
        )

        self.scan_button = ScanButton()
        self.scan_button.connect("clicked", self.on_scan_toggle)

        self.child = ScrolledWindow(
            min_content_size=(-1, 120),
            max_content_size=(-1, 260),
            # propagate_width=False keeps long device names from widening the popup.
            propagate_width=False,
            propagate_height=True,
            child=Box(
                orientation="v",
                children=[
                    self.paired_devices_container,
                    self.available_devices_container,
                ],
            ),
        )

        super().__init__(
            title=_("widget.bluetooth.tooltip"),
            title_icon=get_text_icon("bluetooth.enabled", "󰂱"),
            scan_button=self.scan_button,
            child=self.child,
            **kwargs,
        )

        # Track device rows for easy update
        self.device_rows = {}
        self._paired_devices = set()

        # Populate initial devices
        for device in self.client.devices:
            self.add_device_row(device)
            self._connect_paired(device)

    def on_scan_toggle(self, btn: Button):
        self.client.toggle_scan()
        btn.add_style_class(
            ["active"]
        ) if self.client.scanning else btn.remove_style_class(["active"])
        self.scan_button.play_animation()

    def _connect_paired(self, device: BluetoothDevice):
        """Connect the paired handler once per device."""
        if device.address in self._paired_devices:
            return
        self._paired_devices.add(device.address)
        device.connect("notify::paired", self.on_device_paired_changed)

    def populate_new_device(self, client: BluetoothClient, address: str):
        device: BluetoothDevice = client.get_device(address)
        self.add_device_row(device)
        self._connect_paired(device)

    def add_device_row(self, device: BluetoothDevice):
        # Remove existing row if present
        if device.address in self.device_rows:
            row, listbox = self.device_rows[device.address]
            listbox.remove(row)
            row.destroy()
        bt_item = Gtk.ListBoxRow(visible=True, name="bluetooth-device-row")
        bt_item.add(BluetoothDeviceBox(device))
        if device.paired:
            self.paired_devices_listbox.add(bt_item)
            self.device_rows[device.address] = (bt_item, self.paired_devices_listbox)
        else:
            self.available_devices_listbox.add(bt_item)
            self.device_rows[device.address] = (bt_item, self.available_devices_listbox)

    def on_device_paired_changed(self, device, *_):
        # Move device row between listboxes when paired status changes
        self.add_device_row(device)


class BluetoothToggle(QSChevronButton):
    """A widget to display the Bluetooth status."""

    def __init__(
        self,
        submenu_factory: Callable[[], QuickSubMenu] | None = None,
        **kwargs,
    ):
        super().__init__(
            action_label=_("common.enabled"),
            action_icon=get_text_icon("bluetooth.enabled", "󰂱"),
            submenu_factory=submenu_factory,
            **kwargs,
        )

        # Client Signals
        self.client = bluetooth_service
        self._bound_devices = set()

        bulk_connect(
            self.client,
            {"device-added": self.new_device, "notify::enabled": self.toggle_bluetooth},
        )

        self.toggle_bluetooth(self.client)

        for device in self.client.devices:
            self.new_device(self.client, device.address)
        self.device_connected(
            self.client.connected_devices[0]
        ) if self.client.connected_devices else None

        # Button Signals
        self.connect("action-clicked", lambda *_: self.client.toggle_power())

    def toggle_bluetooth(self, client: BluetoothClient, *_args):
        if client.enabled:
            self.set_active_style(True)
            self.action_icon.set_label(get_text_icon("bluetooth.enabled", "󰂱"))
            self.action_label.set_label(_("common.enabled"))
        else:
            self.set_active_style(False)
            self.action_icon.set_label(get_text_icon("bluetooth.disabled", "󰂲"))
            self.action_label.set_label(_("common.disabled"))

    def new_device(self, client: BluetoothClient, address: str):
        device: BluetoothDevice = client.get_device(address)
        if address in self._bound_devices:
            return
        self._bound_devices.add(address)
        device.connect("changed", self.device_connected)

    def device_connected(self, device: BluetoothDevice):
        if device.connected:
            self.action_label.set_label(device.name)
        elif self.action_label.get_label() == device.name:
            self.action_label.set_label(
                self.client.connected_devices[0].name
                if self.client.connected_devices
                else _("common.enabled")
            )
