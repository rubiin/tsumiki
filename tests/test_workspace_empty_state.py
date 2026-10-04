"""Tests for the empty-workspace rendering of the bar's workspace widgets.

With no windows on the active workspace, both widgets kept a stale look: the
workspace button stayed on the bar as a bubble, and the window title kept the
tooltip of the window it used to show.
"""

import unittest

from fabric.hyprland.widgets import HyprlandActiveWindow

from shared.widget_container import BaseWidget
from widgets.window_title import WindowTitleWidget
from widgets.workspaces import WorkSpacesWidget


def _workspaces(hide_unoccupied: bool = True, ignored: set[int] | None = None):
    """A ``WorkSpacesWidget`` shell with only the fields button setup reads."""
    widget = WorkSpacesWidget.__new__(WorkSpacesWidget)
    widget.icon_map = {}
    widget.label_format = "{id}"
    widget.style = "numbered"
    widget.ignored_ws = ignored or set()
    widget.show_special = False
    widget.hide_unoccupied = hide_unoccupied
    return widget


class _TitleProbe:
    """``_get_title`` and friends, driven without a Hyprland connection."""

    _get_title = WindowTitleWidget._get_title
    _get_compiled_pattern = WindowTitleWidget._get_compiled_pattern
    _set_tooltip = WindowTitleWidget._set_tooltip
    _sync_occupancy = WindowTitleWidget._sync_occupancy
    set_tooltip_if_enabled = BaseWidget.set_tooltip_if_enabled

    def __init__(self, **config):
        self.config = config
        self.tooltips_enabled = True
        self.tooltip_text: str | None = "unset"
        self.visible = True
        self.label = ""

    def get_label(self) -> str:
        return self.label

    def set_tooltip_text(self, text):
        self.tooltip_text = text

    def set_visible(self, visible):
        self.visible = visible


class WorkspaceButtonOccupancyTest(unittest.TestCase):
    """``hide_unoccupied`` must hide the button, not just the label."""

    def test_a_freshly_baked_button_is_hidden(self):
        """The regression: focusing an empty workspace baked a visible bubble.

        Fabric never clears ``empty`` on that path, so the button stayed.
        """
        button = _workspaces()._setup_button(6)

        self.assertFalse(button.get_visible())

    def test_an_occupied_workspace_is_shown(self):
        button = _workspaces()._setup_button(6)

        button.empty = False

        self.assertTrue(button.get_visible())

    def test_the_button_is_hidden_again_when_the_workspace_empties(self):
        button = _workspaces()._setup_button(6)
        button.empty = False

        button.empty = True

        self.assertFalse(button.get_visible())

    def test_hiding_stays_opt_out(self):
        button = _workspaces(hide_unoccupied=False)._setup_button(6)

        self.assertTrue(button.get_visible())

    def test_an_ignored_workspace_stays_hidden_once_occupied(self):
        widget = _workspaces(ignored={6})

        button = widget._setup_button(6)
        button.empty = False

        self.assertFalse(button.get_visible())


class WindowTitleEmptyStateTest(unittest.TestCase):
    """The title widget must forget the window it is no longer showing."""

    def test_the_tooltip_is_dropped_when_no_window_is_focused(self):
        """The regression: the stale title tooltip outlived its window."""
        probe = _TitleProbe()

        probe._get_title("config.toml - tsumiki", "code-insiders")
        probe._get_title("", "unknown")

        self.assertIsNone(probe.tooltip_text)

    def test_the_tooltip_is_cleared_even_with_tooltips_switched_off(self):
        probe = _TitleProbe()
        probe.tooltips_enabled = False
        probe.tooltip_text = "config.toml - tsumiki"

        probe._get_title("", "unknown")

        self.assertIsNone(probe.tooltip_text)

    def test_a_focused_window_still_gets_its_tooltip(self):
        probe = _TitleProbe()

        probe._get_title("config.toml - tsumiki", "code-insiders")

        self.assertEqual("config.toml - tsumiki", probe.tooltip_text)

    def test_mappings_off_no_longer_skips_the_tooltip(self):
        probe = _TitleProbe(mappings=False)

        probe._get_title("config.toml - tsumiki", "code-insiders")

        self.assertEqual("config.toml - tsumiki", probe.tooltip_text)

    def test_the_widget_is_the_button_that_tracks_the_window(self):
        """The title widget is the active-window button, not a wrapper."""
        self.assertTrue(issubclass(WindowTitleWidget, HyprlandActiveWindow))

    def test_an_empty_label_collapses_the_button(self):
        probe = _TitleProbe()

        probe.label = ""
        probe._sync_occupancy()
        self.assertFalse(probe.visible)

        probe.label = "Code - Insiders"
        probe._sync_occupancy()
        self.assertTrue(probe.visible)


if __name__ == "__main__":
    unittest.main()
