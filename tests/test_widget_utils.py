"""Tests for utils/widget_utils.py — widget utility functions."""

import unittest
from unittest import mock

import utils.widget_utils as wu


class GetBarGraphTest(unittest.TestCase):
    """Test the bar graph unicode string generator."""

    def test_zero(self):
        self.assertEqual(wu.get_bar_graph(0), "\u2581")

    def test_boundary_10(self):
        self.assertEqual(wu.get_bar_graph(10), "\u2581")

    def test_20(self):
        self.assertEqual(wu.get_bar_graph(20), "\u2582")

    def test_boundary_30(self):
        self.assertEqual(wu.get_bar_graph(30), "\u2582")

    def test_40(self):
        self.assertEqual(wu.get_bar_graph(40), "\u2583")

    def test_50(self):
        self.assertEqual(wu.get_bar_graph(50), "\u2584")

    def test_60(self):
        self.assertEqual(wu.get_bar_graph(60), "\u2585")

    def test_70(self):
        self.assertEqual(wu.get_bar_graph(70), "\u2586")

    def test_80(self):
        self.assertEqual(wu.get_bar_graph(80), "\u2587")

    def test_100(self):
        self.assertEqual(wu.get_bar_graph(100), "\u2588")

    def test_string_input(self):
        self.assertEqual(wu.get_bar_graph("45"), "\u2584")

    def test_string_invalid_raises(self):
        with self.assertRaises(ValueError):
            wu.get_bar_graph("abc")


class GetBrightnessIconNameTest(unittest.TestCase):
    """Test brightness icon selection based on level thresholds."""

    def test_off(self):
        result = wu.get_brightness_icon_name(0)
        self.assertIn("icon_text", result)
        self.assertIn("icon", result)

    def test_negative(self):
        result = wu.get_brightness_icon_name(-5)
        self.assertIn("icon_text", result)

    def test_low(self):
        result = wu.get_brightness_icon_name(20)
        self.assertIn("icon_text", result)

    def test_boundary_low(self):
        result = wu.get_brightness_icon_name(32)
        self.assertIn("icon_text", result)

    def test_medium(self):
        result = wu.get_brightness_icon_name(50)
        self.assertIn("icon_text", result)

    def test_boundary_medium(self):
        result = wu.get_brightness_icon_name(66)
        self.assertIn("icon_text", result)

    def test_high(self):
        result = wu.get_brightness_icon_name(80)
        self.assertIn("icon_text", result)

    def test_all_keys_present(self):
        for level in [0, 10, 40, 70, 100]:
            result = wu.get_brightness_icon_name(level)
            self.assertIsInstance(result["icon_text"], str)
            self.assertIsInstance(result["icon"], str)
            self.assertTrue(len(result["icon_text"]) > 0)
            self.assertTrue(len(result["icon"]) > 0)


class GetAudioIconNameTest(unittest.TestCase):
    """Test audio icon selection based on volume and mute state."""

    def test_muted(self):
        result = wu.get_audio_icon_name(50, True)
        self.assertIn("icon_text", result)
        self.assertIn("icon", result)

    def test_zero_volume(self):
        result = wu.get_audio_icon_name(0, False)
        self.assertIn("icon_text", result)

    def test_low(self):
        result = wu.get_audio_icon_name(20, False)
        self.assertIn("icon_text", result)

    def test_medium(self):
        result = wu.get_audio_icon_name(50, False)
        self.assertIn("icon_text", result)

    def test_high(self):
        result = wu.get_audio_icon_name(80, False)
        self.assertIn("icon_text", result)

    def test_overamplified(self):
        result = wu.get_audio_icon_name(150, False)
        self.assertIn("icon_text", result)

    def test_all_keys_present(self):
        cases = [
            (0, False),
            (20, False),
            (50, False),
            (80, False),
            (120, False),
            (50, True),
        ]
        for vol, muted in cases:
            result = wu.get_audio_icon_name(vol, muted)
            self.assertIsInstance(result["icon_text"], str)
            self.assertIsInstance(result["icon"], str)
            self.assertTrue(len(result["icon_text"]) > 0)


class UptimeTest(unittest.TestCase):
    """Test the uptime formatter returns HH:MM format."""

    def test_returns_hhmm_format(self):
        result = wu.uptime()
        self.assertRegex(result, r"^\d{2}:\d{2}$")


class FabricatorLifecycleTest(unittest.TestCase):
    """Test util fabricator subscribe/unsubscribe lifecycle."""

    def setUp(self):
        wu._util_fabricator = None
        wu._util_polling_enabled = False
        wu._util_subscribers = 0
        wu._util_changed_handler_ids.clear()

    def tearDown(self):
        wu._util_fabricator = None
        wu._util_polling_enabled = False
        wu._util_subscribers = 0
        wu._util_changed_handler_ids.clear()

    def test_connect_increments_subscribers(self):
        mock_fab = mock.Mock()
        mock_fab.connect.return_value = 42
        wu._util_fabricator = mock_fab

        handler_id = wu.connect_util_fabricator_changed(mock.Mock())
        self.assertEqual(wu._util_subscribers, 1)
        self.assertEqual(handler_id, 42)
        self.assertIn(42, wu._util_changed_handler_ids)

    def test_disconnect_none_is_noop(self):
        wu.disconnect_util_fabricator_changed(None)
        self.assertEqual(wu._util_subscribers, 0)

    def test_disconnect_decrements_subscribers(self):
        mock_fab = mock.Mock()
        mock_fab.connect.return_value = 42
        wu._util_fabricator = mock_fab
        wu._util_subscribers = 1
        wu._util_changed_handler_ids.add(42)

        wu.disconnect_util_fabricator_changed(42)
        self.assertEqual(wu._util_subscribers, 0)
        self.assertEqual(len(wu._util_changed_handler_ids), 0)

    def test_disconnect_stops_fabricator_when_zero(self):
        mock_fab = mock.Mock()
        mock_fab.connect.return_value = 1
        wu._util_fabricator = mock_fab
        wu._util_subscribers = 1
        wu._util_changed_handler_ids.add(1)

        wu.disconnect_util_fabricator_changed(1)
        self.assertIsNone(wu._util_fabricator)
        self.assertFalse(wu._util_polling_enabled)

    def test_disconnect_unknown_id_does_not_decrement(self):
        wu._util_subscribers = 1
        wu.disconnect_util_fabricator_changed(999)
        self.assertEqual(wu._util_subscribers, 1)


if __name__ == "__main__":
    unittest.main()
