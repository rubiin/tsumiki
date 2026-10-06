"""Tests for the live-value fields each widget's ``label_format`` exposes.

A widget feeds its own state or reading into the template through a named field.
The field name has to line up across the format-string registry, the schema and
the widget code, so each one is exercised at the layer that renders it.
"""

import unittest
from unittest import mock

from utils.i18n import _
from utils.validation import _VALID_LABEL_FORMATS
from widgets.battery import BatteryWidget
from widgets.bluetooth import BlueToothWidget
from widgets.cloudflare_warp import CloudflareWarpWidget
from widgets.dns_switcher import DnsSwitcherWidget
from widgets.ocr import OCRWidget
from widgets.weather import WeatherWidget

_EXPECTED_FIELDS = {
    "battery": {
        "percent",
        "time_remaining",
        "capacity",
        "temperature",
        "state",
    },
    "weather": {
        "location",
        "temperature",
        "condition",
        "humidity",
        "wind_speed",
        "sunrise",
        "sunset",
    },
    "bluetooth": {"state"},
    "microphone": {"state"},
    "cloudflare_warp": {"state"},
    "dns_switcher": {"current_dns"},
    "ocr": {"lang"},
}


class FormatRegistryTest(unittest.TestCase):
    """The registry must advertise exactly the fields the widgets render."""

    def test_declared_fields_match_the_widgets(self):
        for name, fields in _EXPECTED_FIELDS.items():
            with self.subTest(widget=name):
                self.assertEqual(fields, _VALID_LABEL_FORMATS[name]["label_format"])


class BatteryStateTest(unittest.TestCase):
    """``{state}`` and the health readings ride in the battery label."""

    def _probe(self, full_battery_level=100) -> BatteryWidget:
        widget = BatteryWidget.__new__(BatteryWidget)
        widget.full_battery_level = full_battery_level
        return widget

    def test_state_words_follow_the_upower_code(self):
        probe = self._probe()
        self.assertEqual("full", probe._state_name(4, 100, False))
        self.assertEqual("charging", probe._state_name(1, 50, True))
        self.assertEqual("discharging", probe._state_name(2, 50, False))
        self.assertEqual("unknown", probe._state_name(0, 50, False))

    def test_full_battery_level_is_honoured(self):
        probe = self._probe(full_battery_level=90)
        self.assertEqual("full", probe._state_name(2, 95, False))

    def test_render_label_exposes_the_new_fields(self):
        widget = self._probe()
        widget.hide_percent_when_full = False
        widget.label_format = "{state} {capacity} {temperature}"
        widget._hovered = False
        widget._hover_color = "#000"
        widget._battery_color = "#fff"
        widget._map_glyphs = lambda *_: "G"
        widget.battery_icon = mock.Mock()
        widget._last_state = {
            "percent": 80,
            "charging": False,
            "time_remaining": "2h",
            "capacity": 80,
            "temperature": 30,
            "state": "discharging",
        }

        widget._render_label()

        widget.battery_icon.set_markup.assert_called_once_with(
            '<span foreground="#fff">G</span> discharging 80% 30°C'
        )


class BluetoothStateTest(unittest.TestCase):
    """``{state}`` flips with the client's enabled flag."""

    def _probe(self, enabled: bool) -> BlueToothWidget:
        widget = BlueToothWidget.__new__(BlueToothWidget)
        widget.icons = {"enabled": "on-icon", "disabled": "off-icon"}
        widget.bluetooth_client = mock.Mock(enabled=enabled)
        widget.refresh_formatted_label = mock.Mock()
        widget.set_tooltip_if_enabled = mock.Mock()
        return widget

    def test_enabled_renders_state_on(self):
        widget = self._probe(enabled=True)
        widget.update_bluetooth_status()
        widget.refresh_formatted_label.assert_called_once_with(
            "on-icon", state="on"
        )

    def test_disabled_renders_state_off(self):
        widget = self._probe(enabled=False)
        widget.update_bluetooth_status()
        widget.refresh_formatted_label.assert_called_once_with(
            "off-icon", state="off"
        )


class CloudflareWarpStateTest(unittest.TestCase):
    """``{state}`` tracks the WARP connection."""

    def _probe(self, connected: bool) -> CloudflareWarpWidget:
        widget = CloudflareWarpWidget.__new__(CloudflareWarpWidget)
        widget._available = True
        widget._connected_icon = "up-icon"
        widget._disconnected_icon = "down-icon"
        widget._service = mock.Mock(connected=connected)
        widget.refresh_formatted_label = mock.Mock()
        widget.set_tooltip_text = mock.Mock()
        return widget

    def test_connected_renders_state_connected(self):
        widget = self._probe(connected=True)
        widget._on_status_changed()
        widget.refresh_formatted_label.assert_called_once_with(
            "up-icon", state="connected"
        )

    def test_disconnected_renders_state_disconnected(self):
        widget = self._probe(connected=False)
        widget._on_status_changed()
        widget.refresh_formatted_label.assert_called_once_with(
            "down-icon", state="disconnected"
        )


class DnsCurrentTextTest(unittest.TestCase):
    """``{current_dns}`` names the active provider, or the default label."""

    def _probe(self, current: str) -> DnsSwitcherWidget:
        widget = DnsSwitcherWidget.__new__(DnsSwitcherWidget)
        widget._service = mock.Mock(current=current)
        return widget

    def test_active_provider_is_returned(self):
        self.assertEqual("Cloudflare", self._probe("Cloudflare")._current_dns_text())

    def test_default_falls_back_to_the_i18n_label(self):
        widget = self._probe("Default")
        self.assertEqual(_("widget.dns_switcher.default"), widget._current_dns_text())

    def test_a_cleared_service_falls_back_to_the_label(self):
        self.assertNotEqual("", self._probe("")._current_dns_text())


class OcrLangFieldTest(unittest.TestCase):
    """``{lang}`` follows the picked tesseract language."""

    def test_selecting_a_language_refreshes_the_label(self):
        widget = OCRWidget.__new__(OCRWidget)
        widget.current_lang = "eng"
        widget.refresh_formatted_label = mock.Mock()
        widget.set_tooltip_if_enabled = mock.Mock()

        widget.on_language_selected(None, "deu")

        self.assertEqual("deu", widget.current_lang)
        widget.refresh_formatted_label.assert_called_once_with(lang="deu")


class WeatherLabelFieldsTest(unittest.TestCase):
    """``label_format`` can reference the readings the widget collects."""

    def _probe(self, label_format: str) -> WeatherWidget:
        widget = WeatherWidget.__new__(WeatherWidget)
        widget.config = {"label_format": label_format}
        widget.data = {"location": "Kathmandu"}
        widget.current_weather = {
            "weatherDesc": [{"value": "Clear"}],
            "humidity": "40",
            "windspeedKmph": "12",
            "windspeedMiles": "7",
            "temp_C": "25",
            "temp_F": "77",
        }
        widget.sunrise_time = "6:00 AM"
        widget.sunset_time = "6:00 PM"
        return widget

    def test_sunrise_and_sunset_are_available(self):
        widget = self._probe("{sunrise} - {sunset}")
        self.assertEqual("6:00 AM - 6:00 PM", widget.get_label_text())

    def test_location_humidity_and_wind_are_available(self):
        widget = self._probe("{location} {humidity} {wind_speed}")
        self.assertEqual("Kathmandu 40% 12 Km/h", widget.get_label_text())


if __name__ == "__main__":
    unittest.main()
