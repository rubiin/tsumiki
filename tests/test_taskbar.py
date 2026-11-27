"""Taskbar client filtering.

The taskbar used to skip every workspace with a non-positive id, so windows
on a special workspace (scratchpad) never appeared. It now follows the dock's
special-workspace logic, keyed on ``hide_special_workspace_apps``.
"""

import unittest
from unittest import mock

from utils.hyprland import hyprland_service
from widgets.taskbar import TaskBarWidget

NORMAL = {"address": "0x1000", "class": "firefox", "workspace": {"id": 2}}
SPECIAL = {"address": "0x2000", "class": "kitty", "workspace": {"id": -98}}
# Hyprland >= 0.57 drops the numeric id for special workspaces.
SPECIAL_MODERN = {
    "address": "0x4000",
    "class": "org.kde.ktorrent",
    "workspace": {
        "address": "special:special",
        "type": "special",
        "name": "special:special",
    },
}


def make_taskbar(config: dict, current_only: bool = False) -> TaskBarWidget:
    widget = TaskBarWidget.__new__(TaskBarWidget)
    widget.config = config
    widget._service = hyprland_service
    widget._hide_special_workspace_apps = config.get(
        "hide_special_workspace_apps", False
    )
    widget._show_current_workspace_only = current_only
    widget._current_workspace_id = None
    widget._active_address = None
    widget._clients_by_address = {}
    widget._client_buttons = {}
    widget._sync_in_progress = False
    widget._add_client_button = mock.Mock()
    widget._update_button_visuals = mock.Mock()
    widget._remove_button = mock.Mock()
    return widget


class SpecialWorkspaceTest(unittest.TestCase):
    """``_process_clients`` handles special-workspace clients like the dock."""

    def addresses(self, widget: TaskBarWidget) -> set:
        return set(widget._clients_by_address)

    def test_special_workspace_apps_show_by_default(self):
        widget = make_taskbar({"ignored": []})

        widget._process_clients([NORMAL, SPECIAL], None)

        self.assertEqual({"0x1000", "0x2000"}, self.addresses(widget))

    def test_special_workspace_apps_are_hidden_when_enabled(self):
        widget = make_taskbar({"ignored": [], "hide_special_workspace_apps": True})

        widget._process_clients([NORMAL, SPECIAL], None)

        self.assertEqual({"0x1000"}, self.addresses(widget))

    def test_special_workspace_without_id_shows_by_default(self):
        widget = make_taskbar({"ignored": []})

        widget._process_clients([NORMAL, SPECIAL_MODERN], None)

        self.assertEqual({"0x1000", "0x4000"}, self.addresses(widget))

    def test_special_workspace_without_id_is_hidden_when_enabled(self):
        widget = make_taskbar({"ignored": [], "hide_special_workspace_apps": True})

        widget._process_clients([NORMAL, SPECIAL_MODERN], None)

        self.assertEqual({"0x1000"}, self.addresses(widget))

    def test_client_without_workspace_info_is_skipped(self):
        widget = make_taskbar({"ignored": []})

        widget._process_clients([NORMAL, {"address": "0x3000", "class": "obs"}], None)

        self.assertEqual({"0x1000"}, self.addresses(widget))

    def test_current_workspace_only_filters_special_when_unfocused(self):
        widget = make_taskbar({"ignored": []}, current_only=True)
        widget._on_workspace_data({"id": 2}, lambda _: None)

        widget._process_clients([NORMAL, SPECIAL], None)

        self.assertEqual({"0x1000"}, self.addresses(widget))

    def test_a_failed_workspace_fetch_keeps_the_tracked_id(self):
        widget = make_taskbar({"ignored": []}, current_only=True)
        widget._current_workspace_id = 2
        seen = []

        widget._on_workspace_data(None, seen.append)
        widget._on_workspace_data({}, seen.append)

        self.assertEqual([2, 2], seen)
        self.assertEqual(2, widget._current_workspace_id)

    def test_current_special_workspace_is_tracked(self):
        widget = make_taskbar({"ignored": []}, current_only=True)
        widget._on_workspace_data({"id": -98}, lambda _: None)

        widget._process_clients([NORMAL, SPECIAL], None)

        self.assertEqual({"0x2000"}, self.addresses(widget))


if __name__ == "__main__":
    unittest.main()
