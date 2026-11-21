"""Tests for the quick settings display picker helpers."""

import unittest

from widgets.quick_settings.submenu.displays import monitor_summary


class MonitorSummaryTest(unittest.TestCase):
    """The picker's detail line must stay readable and crash-free."""

    def test_resolution_and_refresh(self):
        monitor = {"width": 2560, "height": 1440, "refreshRate": 143.99, "scale": 1}
        self.assertEqual(monitor_summary(monitor), "2560x1440 @ 144 Hz")

    def test_fractional_scale_is_shown(self):
        monitor = {"width": 1920, "height": 1080, "refreshRate": 60.0, "scale": 1.5}
        self.assertEqual(monitor_summary(monitor), "1920x1080 @ 60 Hz · 1.5x")

    def test_missing_fields_do_not_raise(self):
        self.assertEqual(monitor_summary({}), "0x0 @ 0 Hz")


if __name__ == "__main__":
    unittest.main()
