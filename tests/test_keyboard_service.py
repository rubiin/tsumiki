"""Tests for the Hyprland-backed keyboard service."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.keyboard import KeyboardService, _led_state

DEVICES = {
    "keyboards": [
        {
            "main": True,
            "layout": "us,ara",
            "active_layout_index": 1,
            "active_keymap": "Arabic",
            "capsLock": True,
            "numLock": False,
        }
    ]
}


def _service(devices: dict | None = None) -> KeyboardService:
    service = KeyboardService.__new__(KeyboardService)
    service._layouts = []
    service._layout_index = 0
    service._layout_name = ""
    service._caps_lock = False
    service._num_lock = False
    service._caps_leds = []
    service._num_leds = []
    service._polls = 0
    service._connection = mock.Mock()
    service._connection.send_command.return_value.reply = json.dumps(
        devices if devices is not None else DEVICES
    ).encode()
    service.notify = mock.Mock()
    return service


class LedStateTest(unittest.TestCase):
    """LEDs are the cheapest source of lock state, when the hardware has them."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _led(self, name: str, value: str) -> str:
        path = self.root / name
        path.write_text(value)
        return str(path)

    def test_any_lit_led_reads_as_on(self):
        paths = [self._led("one", "0"), self._led("two", "1")]

        self.assertTrue(_led_state(paths))

    def test_all_unlit_leds_read_as_off(self):
        self.assertFalse(_led_state([self._led("one", "0"), self._led("two", "0")]))

    def test_a_missing_led_is_ignored(self):
        paths = [str(self.root / "gone"), self._led("two", "1")]

        self.assertTrue(_led_state(paths))


class RefreshTest(unittest.TestCase):
    """``refresh`` mirrors the main keyboard's devices entry into properties."""

    def test_layouts_index_name_and_locks_are_synced(self):
        service = _service()

        service.refresh()

        self.assertEqual(["us", "ara"], service._layouts)
        self.assertEqual(1, service._layout_index)
        self.assertEqual("Arabic", service._layout_name)
        self.assertTrue(service._caps_lock)
        self.assertFalse(service._num_lock)
        self.assertEqual(
            [
                mock.call("layouts"),
                mock.call("layout-index"),
                mock.call("layout-name"),
                mock.call("caps-lock"),
            ],
            service.notify.call_args_list,
        )

    def test_an_unchanged_refresh_stays_silent(self):
        service = _service()
        service._layouts = ["us", "ara"]
        service._layout_index = 1
        service._layout_name = "Arabic"
        service._caps_lock = True

        service.refresh()

        service.notify.assert_not_called()

    def test_a_missing_keyboard_leaves_the_state_alone(self):
        service = _service(devices={"keyboards": []})
        service._layout_name = "English (US)"

        service.refresh()

        self.assertEqual("English (US)", service._layout_name)
        service.notify.assert_not_called()

    def test_led_state_wins_over_the_devices_reply(self):
        service = _service()
        service._caps_leds = ["/nonexistent"]

        service.refresh()

        self.assertFalse(service._caps_lock)


class SetLocksTest(unittest.TestCase):
    """Each lock notifies only when its own value changes."""

    def test_caps_and_num_emit_their_own_signals(self):
        service = _service()

        service._set_locks(True, True)

        self.assertEqual(
            [mock.call("caps-lock"), mock.call("num-lock")],
            service.notify.call_args_list,
        )

    def test_repeating_the_same_state_is_silent(self):
        service = _service()

        service._set_locks(False, False)

        service.notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
