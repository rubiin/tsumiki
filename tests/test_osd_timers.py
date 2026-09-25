"""Tests for the OSD's two-key hide cycle.

``show_box`` arms a hide timer; the hide callback swaps it for a finalize timer
keyed separately, so showing a second OSD mid-animation has to cancel both.
The window is built via ``__new__`` with stubs: real construction needs a
display.
"""

import unittest
from unittest import mock

from modules.osd import OSDContainer
from shared import widget_container as container


def make_osd() -> OSDContainer:
    osd = OSDContainer.__new__(OSDContainer)
    osd._repeaters = []
    osd._handlers = []
    osd._timeouts = {}
    osd.timeout = 2000
    osd.set_visible = mock.Mock()
    osd.revealer = mock.Mock()
    osd.revealer.get_transition_duration.return_value = 250
    osd.audio_container = mock.Mock()
    osd.brightness_container = mock.Mock()
    osd.microphone_container = mock.Mock()
    osd.lockkeys_container = mock.Mock()
    osd.revealer.get_child.return_value = osd.audio_container
    return osd


class OSDTimerTest(unittest.TestCase):
    """show_box -> hide -> finalize-hide, and what interrupts each step."""

    def setUp(self):
        self.armed: list[tuple[int, object]] = []
        self.removed: list[int] = []
        self.next_id = 500
        for target, side_effect in (
            ("timeout_add", self._add),
            ("source_remove", self.removed.append),
        ):
            patcher = mock.patch.object(
                container.GLib, target, side_effect=side_effect
            )
            self.addCleanup(patcher.stop)
            patcher.start()
        self.osd = make_osd()

    def _add(self, delay_ms, callback):
        self.next_id += 1
        self.armed.append((delay_ms, callback))
        return self.next_id

    def fire(self, index=-1):
        return self.armed[index][1]()

    def test_show_box_arms_the_hide_timer(self):
        self.osd.show_box(box_to_show="audio")

        self.assertEqual([(2000, mock.ANY)], [(d, c) for d, c in self.armed])
        self.osd.set_visible.assert_called_once_with(True)
        self.assertTrue(self.osd._has_timeout(OSDContainer._HIDE_TIMER))

    def test_the_two_keys_do_not_collide(self):
        self.osd.show_box(box_to_show="audio")
        self.fire()

        self.assertFalse(self.osd._has_timeout(OSDContainer._HIDE_TIMER))
        self.assertTrue(self.osd._has_timeout(OSDContainer._FINALIZE_TIMER))
        self.assertEqual(250, self.armed[-1][0])

    def test_a_second_show_cancels_the_pending_finalize(self):
        """Re-triggering mid-animation must not leave the window hidden."""
        self.osd.show_box(box_to_show="audio")
        self.fire()

        self.osd.show_box(box_to_show="microphone")

        self.assertFalse(self.osd._has_timeout(OSDContainer._FINALIZE_TIMER))
        self.assertTrue(self.osd._has_timeout(OSDContainer._HIDE_TIMER))

    def test_a_second_show_rearms_rather_than_coalescing(self):
        self.osd.show_box(box_to_show="audio")
        first = self.osd._timeouts[OSDContainer._HIDE_TIMER]

        self.osd.show_box(box_to_show="audio")

        self.assertNotEqual(first, self.osd._timeouts[OSDContainer._HIDE_TIMER])
        self.assertIn(first, self.removed)

    def test_a_fired_timer_is_not_removed_again(self):
        """The old hand-rolled ids outlived their source, so re-triggering mid
        animation asked GLib to remove a dead id and take the warning with it."""
        self.osd.show_box(box_to_show="audio")
        fired_id = self.osd._timeouts[OSDContainer._HIDE_TIMER]
        self.fire()
        self.removed.clear()

        self.osd.show_box(box_to_show="audio")

        self.assertNotIn(fired_id, self.removed)

    def test_finalize_hides_the_window(self):
        self.osd.show_box(box_to_show="audio")
        self.fire()
        self.osd.set_visible.reset_mock()

        self.fire()

        self.osd.set_visible.assert_called_once_with(False)


if __name__ == "__main__":
    unittest.main()
