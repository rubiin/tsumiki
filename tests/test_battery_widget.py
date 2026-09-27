"""Tests for the properties the battery bar widget reads off UPower.

``Energy`` is not a property of the DisplayDevice, so reading it returned
``None`` -> 0 forever and the tooltip always said "Energy : 0.0 Wh".
"""

import unittest
from unittest import mock

from widgets.battery import BatteryWidget

# What UPower actually publishes on /org/freedesktop/UPower/devices/DisplayDevice.
DISPLAY_DEVICE_PROPERTIES = {
    "IsPresent": 1,
    "Percentage": 80,
    "State": 2,
    "Temperature": 305,
    "Capacity": 96,
    "TimeToEmpty": 7200,
    "TimeToFull": 0,
    "IconName": "battery-good-symbolic",
}


def make_widget() -> BatteryWidget:
    """A BatteryWidget with a stubbed client and no GTK window."""
    widget = BatteryWidget.__new__(BatteryWidget)
    widget.config = {"tooltip": True, "hide_when_missing": True, "label": True}
    widget.full_battery_level = 100
    widget.hide_percent_when_full = True
    widget.label_format = "{icon} {percent}"
    widget.battery_icons = [f"icon{i}" for i in range(11)]
    widget.charging_icons = [f"charge{i}" for i in range(11)]
    widget.tooltips_enabled = True
    widget.battery_icon = mock.Mock()
    widget.initialized = False
    widget.last_percentage = None
    widget.last_charging_state = None
    widget.low_battery_notified = False
    widget.full_battery_notified = False
    widget.charging_notified = False
    widget.discharging_notified = False

    client = mock.Mock()
    client.get_property.side_effect = (
        lambda name: DISPLAY_DEVICE_PROPERTIES.get(name)
    )
    widget.client = client
    widget.set_tooltip_text = mock.Mock()
    widget.set_tooltip_if_enabled = mock.Mock()
    return widget


class BatteryPropertyReadTest(unittest.TestCase):
    """Only properties UPower really publishes may be read."""

    def setUp(self):
        self.widget = make_widget()
        with mock.patch("widgets.battery.send_notification"):
            self.widget._update_ui()

    def _requested(self) -> set[str]:
        return {call.args[0] for call in self.widget.client.get_property.call_args_list}

    def test_the_energy_property_is_never_read(self):
        """The regression: "Energy" is absent, so the read silently gave 0."""
        self.assertNotIn("Energy", self._requested())

    def test_the_read_properties_all_exist_on_the_display_device(self):
        self.assertLessEqual(self._requested(), set(DISPLAY_DEVICE_PROPERTIES))

    def test_the_tooltip_reports_the_read_capacity(self):
        tooltip = self.widget.set_tooltip_if_enabled.call_args[0][0]

        self.assertIn("96", tooltip)
        self.assertNotIn("Wh", tooltip)


if __name__ == "__main__":
    unittest.main()
