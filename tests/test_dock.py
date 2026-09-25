"""Tests for dock entry construction in ``modules/dock.py``.

A grouped app and a lone client build the same widget tree and the same drag
wiring, differing only in their drag id, indicator and bookkeeping. The GTK
classes are mocked so the wiring can be asserted without a display.
"""

import unittest
from unittest import mock

from modules import dock as dock_module
from modules.dock import AppBar
from shared import widget_container as container


class FakeClient:
    """The subset of HyprlandClient the entry builders touch."""

    def __init__(self, address: str = "0x1234", app_id: str = "firefox"):
        self._address = address
        self._app_id = app_id

    def get_address_str(self):
        return self._address

    def get_app_id(self):
        return self._app_id

    def get_activated(self):
        return False

    def get_title(self):
        return "title"


def make_appbar(orientation: str = "horizontal") -> AppBar:
    """A bare AppBar with only the state the entry builders read."""
    bar = AppBar.__new__(AppBar)
    bar.config = {"tooltip": False}
    bar.orientation = orientation
    bar._button_base_classes = ["buttons-basic"]
    bar.icon_size = 30
    bar._is_dragging = False
    bar._app_groups = {}
    bar._running_app_boxes = {}
    bar._running_app_count = 0
    bar._icon_resolver = mock.Mock()
    bar._icon_resolver.resolve_icon_pixbuf.return_value = "pixbuf"
    bar._on_drag_begin = mock.Mock()
    bar._on_drag_end = mock.Mock()
    bar._on_drag_data_get = mock.Mock()
    bar._on_drag_data_received = mock.Mock()
    bar._activate_group = mock.Mock()
    bar._on_button_press = mock.Mock(return_value=False)
    bar._on_button_release = mock.Mock(return_value=False)
    bar.add = mock.Mock()
    return bar


class DockEntryTest(unittest.TestCase):
    """The entry wiring must match the previous per-signal connects exactly."""

    def setUp(self):
        for name in ("Box", "Image", "Button", "DotIndicator", "MultiDotIndicator"):
            patcher = mock.patch.object(dock_module, name)
            setattr(self, f"{name}_mock", patcher.start())
            self.addCleanup(patcher.stop)
        # A fresh mock per call, so each entry's wiring is compared separately.
        self.Button_mock.side_effect = lambda **kwargs: mock.Mock()
        connect = mock.patch.object(dock_module, "bulk_connect")
        self.bulk_connect = connect.start()
        self.addCleanup(connect.stop)

    def _drag_signals(self, button):
        """The signal name -> handler recorded in the bulk_connect call."""
        return self.bulk_connect.call_args.args[1]

    def test_drag_handlers_receive_the_same_arguments_as_before(self):
        """The handlers are partials; their bound values must be the tail args.

        GTK supplies the leading arguments, so the bound tuple has to be
        exactly what the old ``connect(sig, handler, *args)`` passed.
        """
        bar = make_appbar()
        bar._create_app_group("firefox", [FakeClient()])

        signals = self.bulk_connect.call_args.args[1]
        entry = bar._app_groups["firefox"]
        box, image = entry["box"], entry["image"]

        # _on_drag_begin(self, widget, context, box, client_image)
        self.assertEqual(
            (box, image), signals["drag-begin"].args, "drag-begin bound args"
        )
        # _on_drag_data_get(..., data, info, time, address)
        self.assertEqual(("firefox",), signals["drag-data-get"].args)
        # _on_drag_end(self, widget, context, box)
        self.assertEqual((box,), signals["drag-end"].args)
        # press/release are the callers' own handlers, passed through as-is
        self.assertTrue(callable(signals["button-press-event"]))
        self.assertTrue(callable(signals["button-release-event"]))

    def test_press_and_release_are_wired_to_the_callers_handlers(self):
        bar = make_appbar()

        bar._create_app_group("firefox", [FakeClient()])

        signals = self.bulk_connect.call_args.args[1]
        # The group keeps its own release behaviour (activate the group).
        button = bar._app_groups["firefox"]["button"]
        signals["button-release-event"](button, mock.Mock(button=1))
        bar._activate_group.assert_called_once_with("firefox")

    def test_group_entry_drag_id_is_the_app_id(self):
        bar = make_appbar()

        bar._create_app_group("firefox", [FakeClient()])

        signals = self._drag_signals(None)
        self.assertEqual(("firefox",), signals["drag-data-get"].args)

    def test_ungrouped_entry_drag_id_is_the_client_address(self):
        bar = make_appbar()

        bar._add_ungrouped_client(FakeClient(address="0xdead"))

        signals = self._drag_signals(None)
        self.assertEqual(("0xdead",), signals["drag-data-get"].args)

    def test_both_entries_wire_the_same_drag_signals(self):
        bar = make_appbar()

        bar._create_app_group("firefox", [FakeClient()])
        bar._add_ungrouped_client(FakeClient(address="0xdead"))

        # Both entries go through one bulk_connect with the same signal set.
        self.assertEqual(2, self.bulk_connect.call_count)
        for call in self.bulk_connect.call_args_list:
            self.assertEqual(
                {
                    "button-press-event",
                    "button-release-event",
                    "drag-begin",
                    "drag-data-get",
                    "drag-end",
                },
                set(call.args[1]),
            )

    def test_vertical_layout_puts_the_indicator_first(self):
        bar = make_appbar(orientation="vertical")

        bar._create_app_group("firefox", [FakeClient()])

        _, kwargs = self.Box_mock.call_args
        self.assertEqual("horizontal", kwargs["orientation"])
        indicator = self.MultiDotIndicator_mock.return_value
        button = bar._app_groups["firefox"]["button"]
        self.assertEqual([indicator, button], kwargs["children"])

    def test_horizontal_layout_puts_the_indicator_last(self):
        bar = make_appbar(orientation="horizontal")

        bar._create_app_group("firefox", [FakeClient()])

        _, kwargs = self.Box_mock.call_args
        self.assertEqual("vertical", kwargs["orientation"])
        button = bar._app_groups["firefox"]["button"]
        self.assertEqual(
            [button, self.MultiDotIndicator_mock.return_value], kwargs["children"]
        )

    def test_group_uses_a_multi_dot_indicator_and_a_single_client_a_dot(self):
        bar = make_appbar()

        bar._create_app_group("firefox", [FakeClient(), FakeClient()])
        bar._add_ungrouped_client(FakeClient(address="0xdead"))

        self.MultiDotIndicator_mock.assert_called_once()
        self.DotIndicator_mock.assert_called_once()

    def test_bookkeeping_stays_with_each_caller(self):
        bar = make_appbar()

        bar._create_app_group("firefox", [FakeClient()])
        bar._add_ungrouped_client(FakeClient(address="0xdead"))

        self.assertIn("indicator", bar._app_groups["firefox"])
        self.assertNotIn("indicator", bar._running_app_boxes["0xdead"])
        self.assertEqual(1, bar._running_app_count)

    def test_entries_are_added_to_the_dock(self):
        bar = make_appbar()

        bar._create_app_group("firefox", [FakeClient()])
        bar._add_ungrouped_client(FakeClient(address="0xdead"))

        self.assertEqual(2, bar.add.call_count)

    def test_a_client_without_an_address_is_skipped(self):
        bar = make_appbar()

        bar._add_ungrouped_client(FakeClient(address=""))

        self.assertEqual({}, bar._running_app_boxes)
        bar.add.assert_not_called()


class SyncSchedulingTest(unittest.TestCase):
    """A pending debounce must win over an immediate sync request."""

    def make_dock(self) -> AppBar:
        dock = AppBar.__new__(AppBar)
        dock._repeaters = []
        dock._handlers = []
        dock._timeouts = {}
        dock._sync_clients = mock.Mock()
        return dock

    def test_an_event_arms_a_debounced_sync(self):
        dock = self.make_dock()

        with mock.patch.object(container.GLib, "timeout_add", return_value=7) as add:
            dock._schedule_sync_clients()

        add.assert_called_once()
        self.assertEqual(dock_module.DOCK_SYNC_DEBOUNCE_MS, add.call_args[0][0])
        dock._sync_clients.assert_not_called()

    def test_zero_delay_syncs_immediately(self):
        dock = self.make_dock()

        with mock.patch.object(container.GLib, "timeout_add") as add:
            dock._schedule_sync_clients(delay_ms=0)

        add.assert_not_called()
        dock._sync_clients.assert_called_once_with()

    def test_zero_delay_does_not_duplicate_a_pending_debounce(self):
        """_on_active_window_event asks for an immediate sync; the debounce
        already armed will deliver the same thing."""
        dock = self.make_dock()

        with mock.patch.object(container.GLib, "timeout_add", return_value=7):
            dock._schedule_sync_clients()
            dock._schedule_sync_clients(delay_ms=0)

        dock._sync_clients.assert_not_called()
        self.assertTrue(dock._has_timeout(AppBar._SYNC_TIMER))

    def test_the_debounce_fires_once_and_frees_the_key(self):
        dock = self.make_dock()

        with mock.patch.object(container.GLib, "timeout_add", return_value=7) as add:
            dock._schedule_sync_clients()
            dock._schedule_sync_clients()  # coalesces

        add.assert_called_once()
        add.call_args[0][1]()  # the main loop runs it

        dock._sync_clients.assert_called_once_with()
        self.assertFalse(dock._has_timeout(AppBar._SYNC_TIMER))


if __name__ == "__main__":
    unittest.main()
