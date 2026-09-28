"""Tests for the 1 Hz ``CommandSwitcher`` tick.

Every apply on this widget invalidates style or re-renders a label, so an
unchanged tick has to be free.
"""

import unittest
from unittest import mock

from shared.button_toggle import CommandSwitcher
from utils.change_cache import ChangeCache


def _make_switcher(
    *, command_available: bool = True, label: bool = True
) -> CommandSwitcher:
    """Build a CommandSwitcher without touching GTK widget init."""
    widget = CommandSwitcher.__new__(CommandSwitcher)
    widget.command = "example-daemon"
    widget.command_available = command_available
    widget.label = label
    widget.tooltip = True
    widget.tooltips_enabled = True
    widget.enabled_icon = "on"
    widget.disabled_icon = "off"
    widget.icon = mock.Mock()
    widget.label_text = mock.Mock()
    widget.get_mapped = mock.Mock(return_value=True)
    widget.toggle_css_class = mock.Mock()
    widget.set_tooltip_text = mock.Mock()
    widget._changes = ChangeCache()
    return widget


class SwitcherPollTest(unittest.TestCase):
    """Repeated ticks with unchanged state must apply nothing."""

    def _tick(self, widget, running, times=1):
        with mock.patch(
            "utils.functions.is_app_running", return_value=running
        ) as is_up:
            for _ in range(times):
                widget._update_ui()
        return is_up

    def test_ten_unchanged_ticks_apply_once(self):
        widget = _make_switcher()

        self._tick(widget, running=True, times=10)

        widget.toggle_css_class.assert_called_once_with("active", True)
        widget.icon.set_label.assert_called_once_with("on")
        widget.label_text.set_label.assert_called_once()
        widget.set_tooltip_text.assert_called_once()

    def test_a_state_flip_reapplies(self):
        widget = _make_switcher()

        self._tick(widget, running=True, times=5)
        self._tick(widget, running=False)

        widget.toggle_css_class.assert_called_with("active", False)
        widget.icon.set_label.assert_called_with("off")
        self.assertEqual(2, widget.set_tooltip_text.call_count)

    def test_an_unmapped_widget_is_not_polled_at_all(self):
        widget = _make_switcher()
        widget.get_mapped = mock.Mock(return_value=False)

        is_up = self._tick(widget, running=True)

        is_up.assert_not_called()
        widget.toggle_css_class.assert_not_called()

    def test_a_missing_command_degrades_to_a_disabled_toggle(self):
        """A missing binary must not raise during layout, and must stay cheap."""
        widget = _make_switcher(command_available=False)

        is_up = self._tick(widget, running=True, times=5)

        is_up.assert_not_called()
        widget.toggle_css_class.assert_called_once_with("active", False)
        widget.icon.set_label.assert_called_once_with("off")
        tooltip = widget.set_tooltip_text.call_args.args[0]
        self.assertTrue(tooltip.startswith("example-daemon:"), tooltip)
        self.assertNotIn("enabled", tooltip)

    def test_a_widget_without_a_label_skips_the_label_apply(self):
        widget = _make_switcher(label=False)

        self._tick(widget, running=True, times=3)

        widget.label_text.set_label.assert_not_called()
        widget.icon.set_label.assert_called_once_with("on")


if __name__ == "__main__":
    unittest.main()
