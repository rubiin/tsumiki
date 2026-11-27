"""Tests for the monitor query callbacks in ``utils/monitors.py``.

Monitor queries used to parse Hyprland replies inside ``HyprlandWithMonitors``;
they now consume the data ``HyprlandService`` already parses. These tests pin
the shape each callback expected before, including failed fetches.
"""

import unittest
from unittest import mock

from utils.monitors import HyprlandWithMonitors


def make_monitor_util(plug_names: tuple = ("DP-1",)) -> HyprlandWithMonitors:
    """A monitor util with a stubbed GDK display instead of a real one."""
    monitor_util = HyprlandWithMonitors.__new__(HyprlandWithMonitors)
    monitor_util.display = mock.Mock()
    monitor_util.display.get_n_monitors.return_value = len(plug_names)
    screen = monitor_util.display.get_default_screen.return_value
    screen.get_monitor_plug_name.side_effect = lambda i: plug_names[i]
    return monitor_util


class AllMonitorsTest(unittest.TestCase):
    """``get_all_monitors`` still answers id -> connector name."""

    def test_monitors_are_keyed_by_id(self):
        seen = []
        monitor_util = make_monitor_util()

        monitor_util._on_monitors_data(
            [{"id": 0, "name": "DP-1"}, {"id": 1, "name": "HDMI-A-1"}], seen.append
        )

        self.assertEqual([{0: "DP-1", 1: "HDMI-A-1"}], seen)

    def test_a_failed_fetch_yields_an_empty_map(self):
        seen = []

        make_monitor_util()._on_monitors_data(None, seen.append)

        self.assertEqual([{}], seen)

    def test_entries_without_a_name_answer_none(self):
        seen = []

        make_monitor_util()._on_monitors_data([{"id": 0}], seen.append)

        self.assertEqual([None], seen)


class MonitorNamesTest(unittest.TestCase):
    """``get_monitor_names`` still answers a list of connector names."""

    def test_names_are_listed(self):
        seen = []

        make_monitor_util()._on_monitor_names_data(
            [{"id": 0, "name": "DP-1"}, {"id": 1, "name": "eDP-1"}], seen.append
        )

        self.assertEqual([["DP-1", "eDP-1"]], seen)

    def test_a_failed_fetch_yields_an_empty_list(self):
        seen = []

        make_monitor_util()._on_monitor_names_data(None, seen.append)

        self.assertEqual([[]], seen)

    def test_entries_without_a_name_yield_an_empty_list(self):
        seen = []

        make_monitor_util()._on_monitor_names_data([{"id": 0}], seen.append)

        self.assertEqual([[]], seen)


class CurrentGdkMonitorTest(unittest.TestCase):
    """The active workspace's monitor resolves to its GDK index."""

    def test_the_active_monitors_gdk_id_is_delivered(self):
        seen = []

        make_monitor_util(("DP-1", "HDMI-A-1"))._on_current_monitor_data(
            {"monitor": "HDMI-A-1"}, seen.append
        )

        self.assertEqual([1], seen)

    def test_an_unknown_monitor_yields_none(self):
        seen = []

        make_monitor_util(("DP-1",))._on_current_monitor_data(
            {"monitor": "HDMI-A-9"}, seen.append
        )

        self.assertEqual([None], seen)

    def test_a_failed_fetch_yields_none(self):
        seen = []

        make_monitor_util()._on_current_monitor_data(None, seen.append)

        self.assertEqual([None], seen)


if __name__ == "__main__":
    unittest.main()
