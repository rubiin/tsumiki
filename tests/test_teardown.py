"""Tests for TeardownMixin's handler tracking."""

import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
