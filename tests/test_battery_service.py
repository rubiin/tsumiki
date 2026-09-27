"""Tests for the UPower PropertiesChanged filter in ``services/battery.py``.

The D-Bus signal is unfiltered and undebounced, so an uninteresting key still
cost the consumer a D-Bus read storm plus a full markup rebuild.
"""

import unittest
from unittest import mock

from gi.repository import GLib

from services.battery import BatteryService


def _properties_changed(changed: dict[str, object]) -> GLib.Variant:
    """Build the ``(sa{sv}as)`` payload a PropertiesChanged signal carries.

    The leading interface name is what makes this shape easy to get wrong: the
    changed keys are element 1, so indexing element 0 filters on characters.
    """
    return GLib.Variant(
        "(sa{sv}as)",
        (
            "org.freedesktop.UPower.Device",
            {name: GLib.Variant("s", str(value)) for name, value in changed.items()},
            (),
        ),
    )


class HandlePropertyChangeTest(unittest.TestCase):
    """Only a rendered property may wake the widget."""

    def setUp(self):
        # Bypass __init__: it opens a system bus connection to UPower.
        self.service = BatteryService.__new__(BatteryService)
        self.service.emit = mock.Mock()

    def _signal(self, changed: dict[str, object]):
        self.service.handle_property_change(
            mock.Mock(),  # connection
            ":1.2",  # sender
            "/org/freedesktop/UPower/devices/DisplayDevice",  # object path
            "org.freedesktop.DBus.Properties",  # interface
            "PropertiesChanged",  # signal name
            _properties_changed(changed),
        )

    def test_a_rendered_property_re_emits(self):
        for name in ("Percentage", "State", "IsPresent", "TimeToEmpty"):
            with self.subTest(name=name):
                self.service.emit.reset_mock()

                self._signal({name: 1})

                self.service.emit.assert_called_once_with("changed")

    def test_the_real_signal_signature_re_emits(self):
        """Element 0 is the interface name, not the changed-properties dict."""
        self._signal({"Percentage": 42})

        self.service.emit.assert_called_once_with("changed")

    def test_only_uninteresting_keys_do_not_re_emit(self):
        self._signal({"Vendor": "Acme", "Technology": "lipo", "PowerSupply": "BAT0"})

        self.service.emit.assert_not_called()

    def test_a_mixed_payload_still_re_emits(self):
        self._signal({"Vendor": "Acme", "Percentage": 55})

        self.service.emit.assert_called_once_with("changed")

    def test_an_unreadable_payload_stays_permissive(self):
        """Better a redundant rebuild than a bar frozen on a stale value."""
        self.service.handle_property_change(
            mock.Mock(), ":1.2", "/path", "iface", "PropertiesChanged", None
        )

        self.service.emit.assert_called_once_with("changed")

    def test_the_callback_takes_no_positional_arguments(self):
        """A truncated call must not raise from the filter itself."""
        self.service.handle_property_change()

        self.service.emit.assert_called_once_with("changed")


if __name__ == "__main__":
    unittest.main()
