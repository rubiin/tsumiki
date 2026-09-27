from fabric.utils import Gio, GLib

# Cache shared D-Bus connections by bus type to avoid redundant connections
_bus_cache = {}

# GLib's -1 means "wait forever", which wedges the GTK main loop if the service
# stops responding. 5 s is long enough for a cold UPower start.
_DEFAULT_CALL_TIMEOUT_MS = 5000


def _get_shared_bus(bus_type):
    """Get or create a shared D-Bus connection for the given bus type."""
    if bus_type not in _bus_cache:
        _bus_cache[bus_type] = Gio.bus_get_sync(bus_type, None)
    return _bus_cache[bus_type]


class GioDBusHelper:
    """A helper class for interacting with D-Bus using the Gio library."""

    def __init__(
        self,
        bus_name,
        object_path,
        interface_name,
        bus_type=Gio.BusType.SYSTEM,
    ):
        self.bus = _get_shared_bus(bus_type)

        self.bus_name = bus_name
        self.object_path = object_path
        # DO_NOT_AUTO_START stops the proxy from *launching* the service, which
        # is the slow part when UPower is not already up. Properties must still
        # load, because consumers read them via get_cached_property.
        self.proxy = Gio.DBusProxy.new_sync(
            self.bus,
            Gio.DBusProxyFlags.DO_NOT_AUTO_START,
            None,
            bus_name,
            object_path,
            interface_name,
            None,
        )

    def call_method(
        self,
        bus_name,
        object_path,
        interface_name,
        method_name,
        parameters=None,
        timeout=_DEFAULT_CALL_TIMEOUT_MS,
    ):
        if parameters is None:
            parameters = GLib.Variant("()", ())
        result = self.bus.call_sync(
            bus_name,
            object_path,
            interface_name,
            method_name,
            parameters,
            None,
            Gio.DBusCallFlags.NONE,
            timeout,
            None,
        )
        return result.unpack()

    def listen_signal(
        self, member, callback, interface_name="org.freedesktop.DBus.Properties"
    ):
        """Register a signal listener (conn, sender, path, iface, signal, parameters)"""
        self.bus.signal_subscribe(
            self.bus_name,
            interface_name,
            member,
            self.object_path,
            arg0=None,
            flags=Gio.DBusSignalFlags.NONE,
            callback=callback,
        )

    def set_property(self, interface_name, property_name, value_variant):
        """Sets a D-Bus property using the standard D-Bus Properties interface."""
        return self.call_method(
            bus_name=self.bus_name,
            object_path=self.object_path,
            interface_name="org.freedesktop.DBus.Properties",
            method_name="Set",
            parameters=GLib.Variant(
                "(ssv)", (interface_name, property_name, value_variant)
            ),
        )
