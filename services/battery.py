from typing import Literal

from fabric import Signal
from fabric.utils import Gio, logger

from utils.dbus_helper import GioDBusHelper

from .base import SingletonService

DeviceState = {
    0: "UNKNOWN",
    1: "CHARGING",
    2: "DISCHARGING",
    3: "EMPTY",
    4: "FULLY_CHARGED",
    5: "PENDING_CHARGE",
    6: "PENDING_DISCHARGE",
}

# UPower republishes every property it knows; only these are read back, and a
# change to any other one only costs the consumer a rebuild of identical markup.
_RENDERED_PROPERTIES = frozenset(
    {
        "Percentage",
        "State",
        "IsPresent",
        "Temperature",
        "Energy",
        "TimeToEmpty",
        "TimeToFull",
        "IconName",
    }
)


def _has_rendered_property(parameters) -> bool:
    """Whether a ``PropertiesChanged`` payload touches a rendered property.

    Stays permissive when the payload cannot be read: an unrecognised shape must
    refresh the bar rather than freeze it.
    """
    if not parameters:
        return True
    try:
        changed = parameters[0]
    except (TypeError, IndexError, KeyError):
        return True
    if not changed:
        return True
    return bool(set(changed) & _RENDERED_PROPERTIES)


class BatteryService(SingletonService):
    """Service to interact with UPower via GIO D-Bus"""

    @Signal
    def changed(self) -> None:
        """Signal emitted when battery changes."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.bus_name = "org.freedesktop.UPower"
        self.object_path = "/org/freedesktop/UPower/devices/DisplayDevice"
        self.interface_name = "org.freedesktop.UPower.Device"

        self.dbus_helper = GioDBusHelper(
            bus_type=Gio.BusType.SYSTEM,
            bus_name=self.bus_name,
            object_path=self.object_path,
            interface_name=self.interface_name,
        )

        self.proxy = self.dbus_helper.proxy

        # Listen for PropertiesChanged signals
        self.dbus_helper.listen_signal(
            member="PropertiesChanged",
            callback=self.handle_property_change,
        )

    def get_property(
        self,
        property: Literal[
            "Percentage",
            "Temperature",
            "TimeToEmpty",
            "TimeToFull",
            "IconName",
            "State",
            "Capacity",
            "IsPresent",
            "Vendor",
        ],
    ):
        try:
            result = self.proxy.get_cached_property(property)
            return result.unpack() if result is not None else None
        except Exception as e:
            logger.exception(f"[Battery] Error retrieving '{property}': {e}")

    def handle_property_change(
        self,
        _connection=None,
        _sender=None,
        _object_path=None,
        _interface=None,
        _signal_name=None,
        parameters=None,
    ):
        """Re-emit only when a property the bar renders actually changed.

        The signal is unfiltered and undebounced, so an ignored key still used
        to cost a D-Bus read storm plus a full markup rebuild in the widget.
        """
        if not _has_rendered_property(parameters):
            return

        self.emit("changed")
