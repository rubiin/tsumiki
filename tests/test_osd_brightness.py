"""The brightness OSD watches a process-wide service singleton.

The bar is rebuilt in-process on a config edit and on every monitor hotplug, so
an untracked handler would keep waking a destroyed drawing area.
"""

import dis
import unittest
from typing import ClassVar
from unittest import mock

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GObject  # noqa: E402

from modules.osds.brightness import BrightnessOSDContainer  # noqa: E402
from shared.widget_container import TeardownMixin  # noqa: E402


class _Destroyable(TeardownMixin, GObject.Object):
    """A real GObject with a real ``destroy`` signal, so no display is needed."""

    __gsignals__: ClassVar = {"destroy": (GObject.SignalFlags.RUN_LAST, None, ())}


class _FakeService:
    """Stands in for the singleton, recording the handlers that stay live."""

    def __init__(self):
        self._next_id = 1
        self.live: set[int] = set()
        self.calls: list[tuple[str, object]] = []

    def connect(self, signal, callback):
        handler_id = self._next_id
        self._next_id += 1
        self.live.add(handler_id)
        self.calls.append((signal, callback))
        return handler_id

    def disconnect(self, handler_id):
        self.live.discard(handler_id)


class _BrightnessOSDProbe(_Destroyable):
    """The OSD's real service registration, off a real GObject."""

    _watch_brightness = BrightnessOSDContainer._watch_brightness

    def __init__(self, service: _FakeService):
        super().__init__()
        self.brightness_service = service
        self.on_brightness_changed = mock.Mock()
        self._watch_brightness()


class BrightnessOSDHandlerTest(unittest.TestCase):
    """The service connection has to be tracked, like every other OSD's."""

    def setUp(self):
        self.service = _FakeService()

    def test_the_handler_is_registered_on_the_singleton(self):
        probe = _BrightnessOSDProbe(self.service)

        self.assertEqual(
            [("brightness_changed", probe.on_brightness_changed)], self.service.calls
        )
        self.assertEqual({1}, self.service.live)

    def test_rebuilding_the_osd_does_not_stack_handlers(self):
        first = _BrightnessOSDProbe(self.service)

        # GTK tears the tree down from C, so only the signal runs cleanup.
        first.emit("destroy")

        _BrightnessOSDProbe(self.service)

        self.assertEqual({2}, self.service.live)

    def test_teardown_is_safe_to_repeat(self):
        probe = _BrightnessOSDProbe(self.service)

        probe.emit("destroy")
        probe.emit("destroy")

        self.assertEqual(set(), self.service.live)

    def test_the_container_does_not_bypass_the_tracking_mixin(self):
        """A bare ``connect`` here is what every other OSD stopped doing."""
        attrs = {
            instruction.argrepr.split(" ")[0]
            for instruction in dis.get_instructions(BrightnessOSDContainer.__init__)
            if instruction.opname in {"LOAD_METHOD", "LOAD_ATTR"}
        }

        self.assertIn("_watch_brightness", attrs)
        self.assertNotIn("connect", attrs)


if __name__ == "__main__":
    unittest.main()
