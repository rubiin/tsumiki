"""Regression tests for ``modules/osds/lockkeys.py``.

The ``j/devices`` query is async, so the first reply always lands after the
constructor returned. With a ``None`` baseline the seed read always looked like
a change, so every login popped the OSD open before the keyboard was touched.
"""

import unittest
from unittest import mock

from modules.osds.lockkeys import LockkeysOSDContainer

IDLE = {"keyboards": [{"main": True, "capsLock": False, "numLock": False}]}
CAPS_ON = {"keyboards": [{"main": True, "capsLock": True, "numLock": False}]}
BOTH_OFF = {"keyboards": [{"main": True, "capsLock": False, "numLock": False}]}


class LockkeysSeedTest(unittest.TestCase):
    """The seed read fills the display; only a real change reveals the OSD."""

    def setUp(self):
        container = LockkeysOSDContainer.__new__(LockkeysOSDContainer)
        container.config = {}
        container.previous_capslock = None
        container.previous_numlock = None
        container._seeded = False
        container.displayed: list[tuple[bool, bool]] = []
        container._update_display = lambda caps, num: container.displayed.append(
            (caps, num)
        )
        self.container = container

        patcher = mock.patch.object(LockkeysOSDContainer, "emit")
        self.emit = patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_first_reply_does_not_reveal_the_osd(self):
        self.container._on_devices_data(CAPS_ON)

        self.assertEqual(0, self.emit.call_count)

    def test_the_first_reply_still_fills_the_display(self):
        self.container._on_devices_data(CAPS_ON)

        self.assertEqual([(True, False)], self.container.displayed)
        self.assertTrue(self.container._seeded)

    def test_a_real_change_after_the_seed_reveals_the_osd(self):
        self.container._on_devices_data(IDLE)

        self.container._on_devices_data(CAPS_ON)

        self.emit.assert_called_once_with("locks-changed")

    def test_turning_a_lock_back_off_reveals_the_osd(self):
        self.container._on_devices_data(CAPS_ON)
        self.emit.reset_mock()

        self.container._on_devices_data(BOTH_OFF)

        self.emit.assert_called_once_with("locks-changed")
        self.assertEqual([(True, False), (False, False)], self.container.displayed)

    def test_a_repeated_identical_reply_reveals_nothing(self):
        self.container._on_devices_data(IDLE)
        self.emit.reset_mock()

        for _ in range(3):
            self.container._on_devices_data(IDLE)

        self.assertEqual(0, self.emit.call_count)

    def test_an_empty_reply_leaves_the_osd_quiet(self):
        self.container._on_devices_data(None)
        self.container._on_devices_data({"keyboards": []})

        self.assertEqual(0, self.emit.call_count)
        self.assertFalse(self.container._seeded)

    def test_a_malformed_reply_does_not_emit(self):
        self.container._on_devices_data({"keyboards": "not-a-list"})

        self.assertEqual(0, self.emit.call_count)


if __name__ == "__main__":
    unittest.main()
