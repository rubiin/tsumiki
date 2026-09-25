"""Regression tests for ``modules/notification.py`` widget lifecycle.

Runs without a display: the GTK widgets are built via ``__new__`` and the
handlers under test are stubbed, so only the signal bookkeeping executes.
"""

import unittest
from unittest import mock

from fabric.notifications import Notification
from fabric.widgets.revealer import Revealer

from modules import notification as notification_module
from modules.notification import NotificationRevealer
from tests.helpers import make_notification


class NotificationRevealerClosedHandlerTest(unittest.TestCase):
    """The ``closed`` handler must follow the current notification, not stack.

    A revealer is reused when a notification is replaced (``replaces_id``), so a
    rebind that forgets to disconnect leaves the previous notification holding a
    live handler into a widget that outlives it.
    """

    def _make_revealer(self, notification: Notification) -> NotificationRevealer:
        revealer = NotificationRevealer.__new__(NotificationRevealer)
        revealer._notification = notification
        revealer._closed_handler_id = None
        revealer.resolved = []
        revealer.on_resolved = lambda *args: revealer.resolved.append(args)
        return revealer

    def test_bind_then_unbind_detaches_handler(self):
        notification = make_notification()
        revealer = self._make_revealer(notification)

        revealer._bind_closed_handler()
        self.assertIsNotNone(revealer._closed_handler_id)

        notification.emit("closed", None)
        self.assertEqual(len(revealer.resolved), 1)

        revealer._unbind_closed_handler()
        self.assertIsNone(revealer._closed_handler_id)

        notification.emit("closed", None)
        self.assertEqual(len(revealer.resolved), 1, "handler still connected")

    def test_rebind_does_not_leave_previous_notification_connected(self):
        first = make_notification(1)
        second = make_notification(2)
        revealer = self._make_revealer(first)

        revealer._bind_closed_handler()

        revealer._unbind_closed_handler()
        revealer._notification = second
        revealer._bind_closed_handler()

        first.emit("closed", None)
        self.assertEqual(revealer.resolved, [], "old notification still wired up")

        second.emit("closed", None)
        self.assertEqual(len(revealer.resolved), 1)

    def test_unbind_without_handler_is_a_noop(self):
        revealer = self._make_revealer(make_notification())

        revealer._unbind_closed_handler()

        self.assertIsNone(revealer._closed_handler_id)

    def test_replace_notification_detaches_previous_handler(self):
        first = make_notification(1)
        second = make_notification(2)
        revealer = self._make_revealer(first)
        revealer.notification_box = mock.MagicMock()
        revealer._bind_closed_handler()

        with (
            mock.patch.object(notification_module, "NotificationWidget") as box_cls,
            mock.patch.object(NotificationRevealer, "add"),
            mock.patch.object(
                NotificationRevealer, "get_reveal_child", return_value=True
            ),
        ):
            # timeout 0 keeps replace_notification off the reveal/timer paths.
            box_cls.return_value.get_timeout.return_value = 0
            revealer.replace_notification(second)

        first.emit("closed", None)
        self.assertEqual(revealer.resolved, [], "old notification still wired up")

        second.emit("closed", None)
        self.assertEqual(len(revealer.resolved), 1)

    def test_destroy_detaches_handler(self):
        notification = make_notification()
        revealer = self._make_revealer(notification)
        revealer._bind_closed_handler()

        with mock.patch.object(Revealer, "destroy", return_value=None):
            NotificationRevealer.destroy(revealer)

        self.assertIsNone(revealer._closed_handler_id)

        notification.emit("closed", None)
        self.assertEqual(revealer.resolved, [], "handler survived destroy")


if __name__ == "__main__":
    unittest.main()
