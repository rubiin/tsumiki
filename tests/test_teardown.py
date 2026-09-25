"""Tests for TeardownMixin's handler tracking."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.widget_container import TeardownMixin


class FakeSource:
    """A GObject-shaped signal source that counts live handlers."""

    def __init__(self):
        self._next_id = 1
        self.live: set[int] = set()
        self.calls: list[tuple[str, int]] = []

    def connect(self, signal, callback):
        handler_id = self._next_id
        self._next_id += 1
        self.live.add(handler_id)
        self.calls.append((signal, handler_id))
        return handler_id

    def disconnect(self, handler_id):
        if handler_id not in self.live:
            raise ValueError(f"handler {handler_id} is not connected")
        self.live.discard(handler_id)


class Widget(TeardownMixin):
    """The smallest thing TeardownMixin can be grafted onto."""

    def __init__(self):
        self.destroy_hooks: list = []
        self.connect("destroy", self._on_destroy)

    def connect(self, signal, callback):
        assert signal == "destroy"
        self.destroy_hooks.append(callback)

    def _on_destroy(self, *_):
        self._teardown()


class TeardownMixinTests(unittest.TestCase):
    """TeardownMixin must leave no connection of its own behind."""

    def test_bulk_registration_connects_every_signal(self):
        widget, source = Widget(), FakeSource()

        handler_ids = widget._register_handlers(
            source,
            {"changed": lambda *_: None, "notify::volume": lambda *_: None},
        )

        self.assertEqual(
            [signal for signal, _ in source.calls], ["changed", "notify::volume"]
        )
        self.assertEqual(sorted(handler_ids), sorted(source.live))

    def test_bulk_registration_tracks_ids_for_teardown(self):
        """The ids used to be discarded, so these connections outlived the widget."""
        widget, source = Widget(), FakeSource()
        widget._register_handlers(
            source, {"changed": lambda *_: None, "closed": lambda *_: None}
        )
        self.assertEqual(len(source.live), 2)

        widget._on_destroy()

        self.assertEqual(source.live, set())

    def test_single_registration_still_returns_the_id(self):
        widget, source = Widget(), FakeSource()

        handler_id = widget._register_handler(
            source, source.connect("changed", lambda *_: None)
        )

        self.assertIn(handler_id, source.live)
        widget._on_destroy()
        self.assertEqual(source.live, set())

    def test_teardown_is_safe_to_repeat(self):
        widget, source = Widget(), FakeSource()
        widget._register_handlers(source, {"changed": lambda *_: None})

        widget._on_destroy()
        widget._on_destroy()

        self.assertEqual(source.live, set())


class TimeoutTests(unittest.TestCase):
    """_schedule_timeout is a debounce by default and a restart on replace."""

    def setUp(self):
        from shared import widget_container as container

        self.container = container
        self.armed: list[tuple[int, object]] = []
        self.removed: list[int] = []
        self.next_id = 100
        patcher_add = mock.patch.object(
            container.GLib, "timeout_add", side_effect=self._fake_timeout_add
        )
        patcher_remove = mock.patch.object(
            container.GLib, "source_remove", side_effect=self.removed.append
        )
        self.addCleanup(patcher_add.stop)
        self.addCleanup(patcher_remove.stop)
        patcher_add.start()
        patcher_remove.start()
        self.widget = Widget()

    def _fake_timeout_add(self, delay_ms, callback):
        self.next_id += 1
        self.armed.append((delay_ms, callback))
        return self.next_id

    def fire(self, index: int = -1):
        """Run a pending callback, as the main loop would."""
        return self.armed[index][1]()

    def test_a_pending_timer_blocks_a_second_arm(self):
        fired = []
        self.assertTrue(
            self.widget._schedule_timeout("hide", 200, lambda: fired.append(1) or False)
        )
        self.assertFalse(
            self.widget._schedule_timeout("hide", 200, lambda: fired.append(1) or False)
        )
        self.assertEqual(1, len(self.armed))

    def test_replace_restarts_from_the_latest_call(self):
        self.widget._schedule_timeout("hide", 200, lambda: False)
        self.assertTrue(
            self.widget._schedule_timeout("hide", 900, lambda: False, replace=True)
        )
        self.assertEqual([101], self.removed)
        self.assertEqual(200, self.armed[0][0])
        self.assertEqual(900, self.armed[1][0])

    def test_different_keys_do_not_collide(self):
        self.widget._schedule_timeout("hide", 200, lambda: False)
        self.assertTrue(self.widget._schedule_timeout("finalize", 200, lambda: False))
        self.assertEqual([], self.removed)

    def test_the_key_is_free_once_the_timer_fires(self):
        fired = []
        self.widget._schedule_timeout("hide", 200, lambda: fired.append(1) or False)
        self.assertTrue(self.widget._has_timeout("hide"))

        self.assertFalse(self.fire())
        self.assertFalse(self.widget._has_timeout("hide"))
        # A poll re-arming under the same key must not be clobbered.
        self.assertTrue(
            self.widget._schedule_timeout("hide", 200, lambda: fired.append(1) or False)
        )
        self.assertEqual(1, len(fired))

    def test_cancel_removes_only_the_named_timer(self):
        self.widget._schedule_timeout("hide", 200, lambda: False)
        self.widget._schedule_timeout("finalize", 200, lambda: False)

        self.widget._cancel_timeout("hide")

        self.assertFalse(self.widget._has_timeout("hide"))
        self.assertTrue(self.widget._has_timeout("finalize"))
        self.assertEqual([101], self.removed)

    def test_cancel_is_a_noop_when_nothing_is_pending(self):
        self.widget._cancel_timeout("hide")
        self.assertEqual([], self.removed)

    def test_teardown_drops_a_pending_timer(self):
        self.widget._schedule_timeout("hide", 200, lambda: False)

        self.widget._on_destroy()

        self.assertEqual([101], self.removed)
        self.assertEqual({}, self.widget._timeouts)


if __name__ == "__main__":
    unittest.main()
