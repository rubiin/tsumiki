import unittest
from types import SimpleNamespace
from unittest.mock import patch

from widgets.quick_settings.submenu.bluetooth import BluetoothToggle


class ConnectedLabelTest(unittest.TestCase):
    """The toggle status line names the connected device and its battery."""

    def _label(self, connected):
        toggle = BluetoothToggle.__new__(BluetoothToggle)
        toggle.client = SimpleNamespace(connected_devices=connected, enabled=True)
        # Keep the test independent of the loaded language file.
        with patch(
            "widgets.quick_settings.submenu.bluetooth._",
            side_effect=lambda key, **_: key,
        ):
            return toggle._connected_label()

    def test_includes_battery_percentage(self):
        device = SimpleNamespace(name="WH-1000XM4", battery_percentage=40.4)
        self.assertEqual(self._label([device]), "WH-1000XM4 · 40%")

    def test_omits_unavailable_battery(self):
        device = SimpleNamespace(name="Keyboard", battery_percentage=0)
        self.assertEqual(self._label([device]), "Keyboard")

    def test_reports_on_when_nothing_connected(self):
        self.assertEqual(self._label([]), "common.on")


if __name__ == "__main__":
    unittest.main()
