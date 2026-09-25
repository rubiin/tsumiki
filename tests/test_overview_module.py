"""Tests for ``OverviewMenu`` teardown.

A debounce source and an in-flight fetch both outlive a destroyed menu, so
teardown has to cancel the timer and invalidate anything still in flight.
Built via ``__new__`` and stubs: real widget construction needs a display.
"""

import unittest
from unittest import mock

from modules import overview as overview_module
from modules.overview import OverviewMenu


def make_menu() -> OverviewMenu:
    """Build a bare OverviewMenu with only the teardown state initialised."""
    menu = OverviewMenu.__new__(OverviewMenu)
    menu._destroyed = False
    menu._update_source_id = None
    menu._update_generation = 0
    menu._handler_ids = []
    menu._service = mock.Mock()
    return menu


class OverviewTeardownTest(unittest.TestCase):
    """Teardown must cancel the debounce and invalidate in-flight work."""
    def test_pending_debounce_is_cancelled(self):
        menu = make_menu()
        menu._update_source_id = 4242

        with mock.patch.object(overview_module.GLib, "source_remove") as remove:
            menu._on_destroy()

        remove.assert_called_once_with(4242)
        self.assertIsNone(menu._update_source_id)

    def test_no_source_remove_when_nothing_is_pending(self):
        menu = make_menu()

        with mock.patch.object(overview_module.GLib, "source_remove") as remove:
            menu._on_destroy()

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

    def test_service_handlers_are_still_disconnected(self):
        menu = make_menu()
        menu._handler_ids = [1, 2]

        with mock.patch.object(overview_module, "safe_disconnect") as disconnect:
            menu._on_destroy()

        self.assertEqual(2, disconnect.call_count)


if __name__ == "__main__":
    unittest.main()
