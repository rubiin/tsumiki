"""Hyprland 0.57 gives special workspaces no numeric id.

Fabric reads the initial workspace list with ``workspace["id"]`` and parses
the id slot of create/destroy events with ``int()``; both raise for a
scratchpad, and the first one took the bar down at startup.
"""

import json
import unittest
from unittest import mock

from fabric.hyprland.service import HyprlandEvent
from fabric.hyprland.widgets import HyprlandWorkspaces

from widgets.workspaces import _HyprlandWorkspaces

SPECIAL = {
    "address": "special:special",
    "type": "special",
    "name": "special:special",
}


def _event(*data: str) -> HyprlandEvent:
    return HyprlandEvent(name="createworkspacev2", data=list(data), raw_data=b"")


class _Probe(_HyprlandWorkspaces):
    """The workspace handlers, driven without GTK or a Hyprland socket."""

    def __init__(self, workspaces: list[dict], active: dict):
        replies = {
            "j/workspaces": json.dumps(workspaces),
            "j/activeworkspace": json.dumps(active),
        }
        self.connection = mock.Mock()
        self.connection.send_command.side_effect = lambda cmd: mock.Mock(
            reply=replies[cmd].encode()
        )
        self.created: list[int] = []
        self.activated: list[int] = []
        self.destroyed: list[int] = []

    def workspace_created(self, workspace_id):
        self.created.append(workspace_id)

    def workspace_activated(self, workspace_id):
        self.activated.append(workspace_id)

    def workspace_destroyed(self, workspace_id):
        self.destroyed.append(workspace_id)


class InitialWorkspaceListTest(unittest.TestCase):
    """``on_ready`` must survive a workspace list holding a scratchpad."""

    def test_a_scratchpad_in_the_list_does_not_break_startup(self):
        probe = _Probe([{"id": 1, "name": "1"}, SPECIAL], {"id": 1, "name": "1"})

        probe.on_ready()

        self.assertEqual([1], probe.created)
        self.assertEqual([1], probe.activated)

    def test_an_idless_active_workspace_does_not_break_startup(self):
        probe = _Probe([{"id": 1, "name": "1"}, SPECIAL], SPECIAL)

        probe.on_ready()

        self.assertEqual([1], probe.created)
        self.assertEqual([], probe.activated)


class WorkspaceEventTest(unittest.TestCase):
    """Scratchpads emit their address in the id slot of v2 events."""

    def test_creating_a_scratchpad_is_ignored(self):
        probe = _Probe([], {})

        probe.on_create_workspace(None, _event("special:zzz", "special:zzz"))

        self.assertEqual([], probe.created)

    def test_creating_a_numbered_workspace_still_bakes_a_button(self):
        probe = _Probe([], {})

        probe.on_create_workspace(None, _event("3", "3"))

        self.assertEqual([3], probe.created)

    def test_destroying_a_scratchpad_is_ignored(self):
        probe = _Probe([], {})

        probe.on_destroy_workspace(None, _event("special:zzz", "special:zzz"))

        self.assertEqual([], probe.destroyed)

    def test_destroying_a_numbered_workspace_still_removes_it(self):
        probe = _Probe([], {})

        probe.on_destroy_workspace(None, _event("3", "3"))

        self.assertEqual([3], probe.destroyed)


class UrgentSignalTest(unittest.TestCase):
    """``show_urgent`` only gates Fabric's urgent signal, not the event."""

    def test_fabric_handles_urgent_events(self):
        self.assertIs(_HyprlandWorkspaces.on_urgent, HyprlandWorkspaces.on_urgent)

    def test_the_urgent_signal_reaches_fabric_when_enabled(self):
        probe = _HyprlandWorkspaces.__new__(_HyprlandWorkspaces)
        probe._show_urgent = True

        with mock.patch.object(HyprlandWorkspaces, "urgent") as base:
            probe.urgent(3)

        base.assert_called_once_with(3)

    def test_the_urgent_signal_is_dropped_when_disabled(self):
        probe = _HyprlandWorkspaces.__new__(_HyprlandWorkspaces)
        probe._show_urgent = False

        with mock.patch.object(HyprlandWorkspaces, "urgent") as base:
            probe.urgent(3)

        base.assert_not_called()


if __name__ == "__main__":
    unittest.main()
