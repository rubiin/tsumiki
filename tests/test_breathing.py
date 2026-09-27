"""Tests for ``BreathingMenu`` display updates.

The 1 Hz tick must not call ``show_all()``: that would recursively re-show the
exercise and duration frames the very same call hides.
"""

import unittest
from unittest import mock

try:
    from widgets.breathing import BreathingMenu

    HAS_BREATHING_MENU = True
except (ImportError, ValueError):  # GTK / fabric widgets unavailable
    HAS_BREATHING_MENU = False


def make_menu(*, running: bool) -> "BreathingMenu":
    """Build a BreathingMenu with mocked children, so no display is needed."""
    menu = BreathingMenu.__new__(BreathingMenu)
    menu._current_index = 0
    menu._is_running = running
    menu._is_paused = False
    menu._phase = "inhale" if running else ""
    menu._phase_remaining = 3000
    menu._phase_total = 4000
    menu._total_remaining = 60_000
    menu._current_cycle = 1
    menu._total_cycles = 6
    menu._timer_id = None
    menu._schedule_tick = mock.Mock()

    menu._phase_label = mock.Mock()
    menu._countdown_label = mock.Mock()
    menu._total_label = mock.Mock()
    menu._cycle_label = mock.Mock()
    menu._subtitle_lbl = mock.Mock()
    menu._circle = mock.Mock()
    menu._grid_frame = mock.Mock()
    menu._duration_frame = mock.Mock()
    menu._start_btn = mock.Mock()
    menu._stop_btn = mock.Mock()
    menu.show_all = mock.Mock()
    return menu


@unittest.skipUnless(HAS_BREATHING_MENU, "breathing menu unavailable")
class BreathingDisplayTest(unittest.TestCase):
    """show_all() belongs to __init__ only, never to the per-second update."""

    def test_tick_does_not_reveal_everything(self):
        menu = make_menu(running=True)

        menu._tick()

        menu.show_all.assert_not_called()

    def test_frames_stay_hidden_while_running(self):
        menu = make_menu(running=True)

        for _ in range(5):
            menu._tick()

        menu._grid_frame.set_visible.assert_called_with(False)
        menu._duration_frame.set_visible.assert_called_with(False)
        self.assertEqual(menu._grid_frame.set_visible.call_count, 5)

    def test_paused_state_also_skips_show_all(self):
        menu = make_menu(running=True)
        menu._is_paused = True

        menu._update_display()

        menu.show_all.assert_not_called()
        menu._grid_frame.set_visible.assert_called_with(False)

    def test_idle_state_shows_frames_without_show_all(self):
        menu = make_menu(running=False)

        menu._update_display()

        menu.show_all.assert_not_called()
        menu._grid_frame.set_visible.assert_called_with(True)
        menu._duration_frame.set_visible.assert_called_with(True)

    def test_dead_duration_button_handler_is_gone(self):
        # The duration presets became a SpinButton; _dur_buttons never existed.
        self.assertFalse(hasattr(BreathingMenu, "_on_duration_clicked"))


if __name__ == "__main__":
    unittest.main()
