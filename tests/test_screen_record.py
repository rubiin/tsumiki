"""Tests for the shared file-notification helper in ``screen_record.py``.

Screenshot and screencast notifications are the same notify-send invocation
with a different action set, and the chosen action comes back on stdout as the
key. The GTK/Gio calls are mocked; the service is built via ``__new__``.
"""

import unittest
from unittest import mock

from gi.repository import GLib

from services import screen_record as screen_record_module
from services.screen_record import ScreenRecorderService


def make_service() -> ScreenRecorderService:
    service = ScreenRecorderService.__new__(ScreenRecorderService)
    service.screenshot_path = "/home/u/Pictures"
    service.screenrecord_path = "/home/u/Videos"
    service.home_dir = "/home/u"
    return service


class SendFileNotificationTest(unittest.TestCase):
    """The shared notifier builds one argv and dispatches the chosen action."""

    def setUp(self):
        patcher = mock.patch.object(
            screen_record_module.Gio, "Subprocess", autospec=False
        )
        self.Subprocess = patcher.start()
        self.addCleanup(patcher.stop)
        self.proc = self.Subprocess.new.return_value
        self.proc.communicate_utf8_finish.return_value = (None, "view\n", None)

        service = make_service()
        service._open_in_file_manager = mock.Mock()
        service._open_path = mock.Mock()
        self.service = service

        self.dispatched: list[str] = []
        self.kwargs = {
            "log_tag": "SCREENSHOT",
            "summary": "Screenshot Saved",
            "body": "Saved Screenshot at /tmp/a.png",
            "icon": "camera-symbolic",
            "utility": "Screenshot Utility",
            "icon_hint": "STRING:image-path:/tmp/a.png",
            "actions": (
                ("files", "Show in Files", lambda: self.dispatched.append("files")),
                ("view", "View", lambda: self.dispatched.append("view")),
            ),
        }

    def _fire(self, stdout: str):
        """Run the completion callback the way Gio would, with *stdout*."""
        self.proc.communicate_utf8_finish.return_value = (None, stdout, None)
        # communicate_utf8_async(stdin, cancellable, callback)
        callback = self.proc.communicate_utf8_async.call_args.args[2]
        callback(self.proc, mock.Mock())

    def test_argv_carries_every_flag_and_action(self):
        self.service._send_file_notification(**self.kwargs)

        argv = self.Subprocess.new.call_args.args[0]
        self.assertEqual("notify-send", argv[0])
        self.assertIn("files=Show in Files", argv)
        self.assertIn("view=View", argv)
        self.assertIn("STRING:image-path:/tmp/a.png", argv)
        self.assertEqual(
            ["Screenshot Saved", "Saved Screenshot at /tmp/a.png"], argv[-2:]
        )

    def test_chosen_action_runs_only_its_handler(self):
        self.service._send_file_notification(**self.kwargs)

        self._fire("view\n")

        self.assertEqual(["view"], self.dispatched)

    def test_an_unknown_action_does_nothing(self):
        self.service._send_file_notification(**self.kwargs)

        self._fire("something-else\n")

        self.assertEqual([], self.dispatched)

    def test_a_read_error_does_not_dispatch(self):
        self.service._send_file_notification(**self.kwargs)
        self.proc.communicate_utf8_finish.side_effect = GLib.Error("closed")

        self._fire("view\n")

        self.assertEqual([], self.dispatched)


class NotificationActionMappingTest(unittest.TestCase):
    """Each caller's actions point at its own paths."""

    def setUp(self):
        patcher = mock.patch.object(
            screen_record_module.Gio, "Subprocess", autospec=False
        )
        self.Subprocess = patcher.start()
        self.addCleanup(patcher.stop)
        self.service = make_service()
        self.service._open_in_file_manager = mock.Mock()
        self.service._open_path = mock.Mock()

    def _fire(self, stdout: str):
        self.Subprocess.new.return_value.communicate_utf8_finish.return_value = (
            None,
            stdout,
            None,
        )
        proc = self.Subprocess.new.return_value
        callback = proc.communicate_utf8_async.call_args.args[2]
        callback(self.Subprocess.new.return_value, mock.Mock())

    def test_screenshot_files_action_opens_its_own_directory(self):
        self.service.send_screenshot_notification(file_path="/tmp/a.png")

        self._fire("files\n")

        self.service._open_in_file_manager.assert_called_once_with("/home/u/Pictures")

    def test_screencast_files_action_opens_its_own_directory(self):
        self.service.send_screenrecord_notification(file_path="/tmp/a.webm")

        self._fire("files\n")

        self.service._open_in_file_manager.assert_called_once_with("/home/u/Videos")

    def test_screenshot_offers_an_edit_action_that_screencast_does_not(self):
        self.service.send_screenshot_notification(file_path="/tmp/a.png")
        self._fire("edit\n")
        self.service._open_path.assert_called_once_with("/tmp/a.png", "swappy", "-f")

    def test_clipboard_capture_sends_a_bare_notification(self):
        self.service.send_screenshot_notification(file_path=None)

        self.Subprocess.new.assert_called_once()
        argv = self.Subprocess.new.call_args.args[0]
        self.assertEqual(["notify-send", "Screenshot Sent to Clipboard"], argv)


if __name__ == "__main__":
    unittest.main()
