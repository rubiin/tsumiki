"""Tests for utils/dbus_helper.py — D-Bus helper utilities."""

import unittest
from unittest import mock

from utils.dbus_helper import (
    GioDBusHelper,
    _bus_cache,
    _get_shared_bus,
)


class GetSharedBusTest(unittest.TestCase):
    """Test the shared bus connection cache."""

    def setUp(self):
        _bus_cache.clear()

    def tearDown(self):
        _bus_cache.clear()

    @mock.patch("utils.dbus_helper.Gio.bus_get_sync")
    def test_creates_new_connection(self, mock_get):
        mock_get.return_value = mock.Mock()
        bus = _get_shared_bus("SESSION")
        mock_get.assert_called_once_with("SESSION", None)
        self.assertIs(bus, mock_get.return_value)

    @mock.patch("utils.dbus_helper.Gio.bus_get_sync")
    def test_caches_connection(self, mock_get):
        mock_get.return_value = mock.Mock()
        bus1 = _get_shared_bus("SESSION")
        bus2 = _get_shared_bus("SESSION")
        self.assertIs(bus1, bus2)
        self.assertEqual(mock_get.call_count, 1)

    @mock.patch("utils.dbus_helper.Gio.bus_get_sync")
    def test_different_bus_types_get_separate_connections(self, mock_get):
        mock_get.side_effect = [mock.Mock(), mock.Mock()]
        bus_sys = _get_shared_bus("SYSTEM")
        bus_sess = _get_shared_bus("SESSION")
        self.assertIsNot(bus_sys, bus_sess)
        self.assertEqual(mock_get.call_count, 2)


class GioDBusHelperTest(unittest.TestCase):
    """Test GioDBusHelper with mocked Gio objects."""

    def _make_helper(self):
        mock_bus = mock.Mock()
        mock_proxy = mock.Mock()
        with (
            mock.patch(
                "utils.dbus_helper._get_shared_bus",
                return_value=mock_bus,
            ),
            mock.patch(
                "utils.dbus_helper.Gio.DBusProxy.new_sync",
                return_value=mock_proxy,
            ),
        ):
            helper = GioDBusHelper(
                bus_name="org.example.Test",
                object_path="/org/example/Test",
                interface_name="org.example.Interface",
            )
            helper._mock_bus = mock_bus
            helper._mock_proxy = mock_proxy
            return helper

    def test_init_creates_proxy(self):
        helper = self._make_helper()
        self.assertEqual(helper.bus_name, "org.example.Test")
        self.assertEqual(helper.object_path, "/org/example/Test")

    def test_call_method(self):
        helper = self._make_helper()
        helper._mock_bus.call_sync.return_value = mock.Mock()
        unpacked = mock.Mock()
        unpacked.return_value = ("result",)
        helper._mock_bus.call_sync.return_value.unpack = unpacked

        result = helper.call_method(
            bus_name="org.example.Test",
            object_path="/org/example/Test",
            interface_name="org.example.Interface",
            method_name="GetValue",
        )
        self.assertEqual(result, ("result",))
        helper._mock_bus.call_sync.assert_called_once()

    def test_call_method_default_parameters(self):
        helper = self._make_helper()
        helper._mock_bus.call_sync.return_value = mock.Mock()
        helper._mock_bus.call_sync.return_value.unpack.return_value = None

        helper.call_method(
            bus_name="org.example.Test",
            object_path="/org/example/Test",
            interface_name="org.example.Interface",
            method_name="Ping",
        )
        helper._mock_bus.call_sync.assert_called_once()

    def test_listen_signal(self):
        helper = self._make_helper()
        callback = mock.Mock()

        helper.listen_signal("PropertiesChanged", callback)

        helper._mock_bus.signal_subscribe.assert_called_once()
        call_args = helper._mock_bus.signal_subscribe.call_args
        self.assertEqual(call_args[0][3], "/org/example/Test")

    def test_set_property(self):
        helper = self._make_helper()
        helper._mock_bus.call_sync.return_value = mock.Mock()
        helper._mock_bus.call_sync.return_value.unpack.return_value = None

        variant_factory = mock.Mock()
        with mock.patch(
            "utils.dbus_helper.GLib.Variant",
            side_effect=variant_factory,
        ):
            helper.set_property("org.example.Interface", "SomeProp", mock.Mock())
        helper._mock_bus.call_sync.assert_called_once()


if __name__ == "__main__":
    unittest.main()
