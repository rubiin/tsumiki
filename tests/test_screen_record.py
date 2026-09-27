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


class AnnotatedScreenshotTest(unittest.TestCase):
    """``screenshot(annotation=True)`` hands off to satty exactly once."""

    TEMP_PATH = "/tmp/tsumiki shot/aBc123.png"

    def setUp(self):
        patcher = mock.patch.object(
            screen_record_module.tempfile, "NamedTemporaryFile", autospec=False
        )
        self.tempfile = patcher.start()
        self.addCleanup(patcher.stop)
        self.tempfile.return_value.__enter__.return_value.name = self.TEMP_PATH

        patcher = mock.patch.object(
            screen_record_module, "exec_shell_command_async", autospec=False
        )
        self.exec_async = patcher.start()
        self.addCleanup(patcher.stop)

        # Run the worker inline instead of handing it to the thread pool.
        patcher = mock.patch.object(
            screen_record_module, "thread", side_effect=lambda fn: fn(), autospec=False
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        # Run the callback inline, recording what idle_add was asked to return.
        self.idle_returns: list = []
        patcher = mock.patch.object(
            screen_record_module,
            "idle_add",
            side_effect=lambda fn: (self.idle_returns.append(fn()), False)[1],
            autospec=False,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        # Both shell-out paths are mocked, so nothing is actually executed.
        patcher = mock.patch.object(
            screen_record_module.helpers, "run_command", autospec=False
        )
        self.run_command = patcher.start()
        self.run_command.return_value = ""
        self.addCleanup(patcher.stop)

        patcher = mock.patch.object(
            screen_record_module, "exec_shell_command", autospec=False
        )
        self.exec_shell = patcher.start()
        self.exec_shell.return_value = ""
        self.addCleanup(patcher.stop)

        patcher = mock.patch.object(screen_record_module.os, "unlink", autospec=False)
        self.unlink = patcher.start()
        self.addCleanup(patcher.stop)

        patcher = mock.patch.object(screen_record_module, "logger", autospec=False)
        self.logger = patcher.start()
        self.addCleanup(patcher.stop)

        # On the class: the service is a singleton, so it would leak otherwise.
        patcher = mock.patch.object(
            ScreenRecorderService, "send_screenshot_notification", autospec=False
        )
        self.notify = patcher.start()
        self.addCleanup(patcher.stop)

        service = make_service()
        service.shutter_sound = "/assets/sounds/camera-shutter.mp3"
        self.service = service

    def _satty_argvs(self) -> list:
        """Every satty argv, whichever runner the code used to launch it."""
        return [
            call.args[0]
            for runner in (self.run_command, self.exec_shell)
            for call in runner.call_args_list
            if "satty" in str(call.args[0])
        ]

    def _capture(self, *, annotation: bool = True, **extra):
        config = {"path": "Pictures", "annotation": annotation, **extra}
        self.service.screenshot(config)
        # grimblast is mocked, so fire its completion callback by hand.
        self.exec_async.call_args.args[1]()

    def test_annotated_screenshot_launches_satty_once(self):
        self._capture()

        self.assertEqual(1, len(self._satty_argvs()))
        self.run_command.assert_called_once()
        self.exec_shell.assert_not_called()
        self.assertEqual("satty", self.run_command.call_args.args[0][0])

    def test_temp_file_is_unlinked_once(self):
        self._capture()

        self.unlink.assert_called_once_with(self.TEMP_PATH)

    def test_annotation_notifies_once(self):
        self._capture()

        self.notify.assert_called_once()
        notified_path = self.notify.call_args.kwargs["file_path"]
        self.assertNotEqual(self.TEMP_PATH, notified_path)

    def test_failed_satty_warns_and_keeps_the_temp_file(self):
        self.run_command.return_value = None

        self._capture()

        self.logger.warning.assert_called_once_with(
            "[SCREENSHOT] satty annotation failed"
        )
        self.unlink.assert_not_called()
        self.notify.assert_not_called()
        self.assertEqual([], self.idle_returns)

    def test_a_temp_path_with_a_space_stays_one_argv_element(self):
        self._capture()

        self.assertEqual(1, len(self._satty_argvs()))
        (argv,) = self._satty_argvs()
        self.assertEqual(
            ["satty", "--filename", self.TEMP_PATH, "--output-filename"],
            argv[:4],
        )
        self.assertIn(self.TEMP_PATH, argv)

    def test_capture_sound_plays_once_after_annotation(self):
        patcher = mock.patch.object(
            screen_record_module.helpers, "play_sound", autospec=False
        )
        play_sound = patcher.start()
        self.addCleanup(patcher.stop)

        self._capture(capture_sound=True)

        play_sound.assert_called_once_with("/assets/sounds/camera-shutter.mp3")

    def test_capture_without_annotation_never_launches_satty(self):
        self._capture(annotation=False)

        self.assertEqual([], self._satty_argvs())
        self.unlink.assert_not_called()
        self.notify.assert_called_once()


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
