"""Tests for ``OverviewMenu`` teardown.

A debounce source and an in-flight fetch both outlive a destroyed menu, so
teardown has to cancel the timer and invalidate anything still in flight.
Built via ``__new__`` and stubs: real widget construction needs a display.
"""

import unittest
from unittest import mock

from modules.overview import OverviewMenu
from shared import widget_container as container


def make_menu() -> OverviewMenu:
    """Build a bare OverviewMenu with only the teardown state initialised."""
    menu = OverviewMenu.__new__(OverviewMenu)
    menu._destroyed = False
    menu._update_generation = 0
    menu._repeaters = []
    menu._handlers = []
    menu._timeouts = {}
    menu._service = mock.Mock()
    return menu


class OverviewTeardownTest(unittest.TestCase):
    """Teardown must cancel the debounce and invalidate in-flight work."""

    def test_schedule_update_arms_a_keyed_debounce(self):
        menu = make_menu()

        with mock.patch.object(container.GLib, "timeout_add", return_value=4242) as add:
            menu._schedule_update()

        add.assert_called_once()
        self.assertEqual(200, add.call_args[0][0])
        self.assertTrue(menu._has_timeout(OverviewMenu._UPDATE_TIMER))

    def test_repeated_events_coalesce_into_one_debounce(self):
        """Four window events must not queue four grid rebuilds."""
        menu = make_menu()

        with mock.patch.object(container.GLib, "timeout_add", return_value=4242) as add:
            for _ in range(4):
                menu._schedule_update()

        add.assert_called_once()

    def test_pending_debounce_is_cancelled(self):
        menu = make_menu()
        with mock.patch.object(container.GLib, "timeout_add", return_value=4242):
            menu._schedule_update()

        with mock.patch.object(container.GLib, "source_remove") as remove:
            menu._teardown()

        remove.assert_called_once_with(4242)
        self.assertFalse(menu._has_timeout(OverviewMenu._UPDATE_TIMER))

    def test_no_source_remove_when_nothing_is_pending(self):
        menu = make_menu()

        with mock.patch.object(container.GLib, "source_remove") as remove:
            menu._teardown()

        remove.assert_not_called()

    def test_in_flight_fetch_is_invalidated(self):
        """A fetch whose generation still matches must not touch the grid."""
        menu = make_menu()
        generation = menu._update_generation

        menu._on_destroy()

        self.assertNotEqual(generation, menu._update_generation)
        self.assertTrue(menu._destroyed)

    def test_update_after_destroy_is_a_noop(self):
        """Covers the on_ready callback, which cannot be disconnected."""
        menu = make_menu()
        menu._on_destroy()

        with mock.patch.object(OverviewMenu, "_refresh_app_cache_if_needed") as refresh:
            menu.update()

        refresh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
