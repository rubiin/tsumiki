"""Tests for the Hyprland dispatch commands built in ``utils/hyprland.py``.

Hyprland 0.55+ evaluates ``/dispatch`` as Lua, so the old
``dispatch <name> <args>`` form is a syntax error. Every reply used to be
discarded, which let a wholesale API break look like a no-op click - so these
tests pin the exact expressions, and the reply handler is asserted to surface
errors instead of swallowing them.
"""

import unittest
from unittest import mock

from utils import hyprland as hyprland_module
from utils.hyprland import HyprlandService

ADDR = "0x563d29cf89d0"


def make_service() -> tuple[HyprlandService, mock.Mock]:
    """A service with a stubbed connection, plus the connection mock."""
    service = HyprlandService.__new__(HyprlandService)
    connection = mock.Mock()
    service._connection = connection
    return service, connection


class DispatchCommandTest(unittest.TestCase):
    """Each helper must emit a ``hl.dsp.*`` call with an ``address:`` selector."""

    def setUp(self):
        self.service, self.connection = make_service()

    def sent(self) -> str:
        return self.connection.send_command_async.call_args.args[0]

    def test_focus_window(self):
        self.service.focus_window(ADDR)
        self.assertEqual(
            f'dispatch hl.dsp.focus({{window="address:{ADDR}"}})', self.sent()
        )

    def test_close_window(self):
        self.service.close_window(ADDR)
        self.assertEqual(
            f'dispatch hl.dsp.window.close({{window="address:{ADDR}"}})', self.sent()
        )

    def test_move_window_to_workspace_follows_focus_by_default(self):
        self.service.move_window_to_workspace(ADDR, 4)
        self.assertEqual(
            f'dispatch hl.dsp.window.move({{workspace=4, follow=true, '
            f'window="address:{ADDR}"}})',
            self.sent(),
        )

    def test_silent_move_keeps_focus_put(self):
        """The old movetoworkspacesilent: the window moves, focus does not."""
        self.service.move_window_to_workspace(ADDR, 4, silent=True)
        self.assertIn("follow=false", self.sent())

    def test_toggle_floating(self):
        self.service.toggle_floating(ADDR)
        self.assertEqual(
            f'dispatch hl.dsp.window.float({{action="toggle", '
            f'window="address:{ADDR}"}})',
            self.sent(),
        )

    def test_set_fullscreen_on_and_off(self):
        self.service.set_fullscreen(True)
        self.assertIn('action="set"', self.sent())

        self.connection.send_command_async.reset_mock()
        self.service.set_fullscreen(False)
        self.assertIn('action="unset"', self.sent())

    def test_close_windows_by_class_uses_a_class_selector(self):
        self.service.close_windows_by_class("org.wezfurlong.wezterm")
        self.assertEqual(
            'dispatch hl.dsp.window.close({window="class:org.wezfurlong.wezterm"})',
            self.sent(),
        )

    def test_no_command_uses_the_removed_legacy_syntax(self):
        """Guard the whole class of bug, not just today's call sites."""
        for call in (
            lambda: self.service.focus_window(ADDR),
            lambda: self.service.close_window(ADDR),
            lambda: self.service.move_window_to_workspace(ADDR, 2),
            lambda: self.service.move_window_to_workspace(ADDR, 2, silent=True),
            lambda: self.service.toggle_floating(ADDR),
            lambda: self.service.set_fullscreen(True),
            lambda: self.service.set_fullscreen(False),
            lambda: self.service.close_windows_by_class("x"),
        ):
            self.connection.send_command_async.reset_mock()
            call()
            sent = self.sent()
            with self.subTest(command=sent):
                self.assertTrue(sent.startswith("dispatch hl.dsp."), sent)
                # A legacy command is "dispatch <name> ..." with no parens.
                self.assertNotRegex(sent, r"dispatch \w+ +\w")


class MalformedAddressTest(unittest.TestCase):
    """The address is interpolated into Lua, so refuse anything unexpected."""

    def setUp(self):
        self.service, self.connection = make_service()

    def test_nothing_is_sent_for_a_bad_address(self):
        for bad in ("", None, "563d29cf89d0", "0xZZZ", '0x1" os.execute("x'):
            with self.subTest(address=bad):
                self.connection.send_command_async.reset_mock()
                self.service.focus_window(bad)
                self.connection.send_command_async.assert_not_called()

    def test_uppercase_hex_is_accepted(self):
        self.service.focus_window("0xABCDEF0123456789")
        self.connection.send_command_async.assert_called_once()


class DispatchReplyTest(unittest.TestCase):
    """A rejected dispatch must be logged, not dropped."""

    def setUp(self):
        self.service, self.connection = make_service()

    def _reply(self, payload: bytes):
        return mock.Mock(command="dispatch hl.dsp.focus(...)", reply=payload)

    def test_error_reply_is_logged(self):
        with mock.patch.object(hyprland_module, "logger") as log:
            HyprlandService._on_dispatch_reply(self._reply(b"error: bad lua"))
        log.error.assert_called_once()
        self.assertIn("bad lua", log.error.call_args.args[0])

    def test_ok_reply_is_silent(self):
        with mock.patch.object(hyprland_module, "logger") as log:
            HyprlandService._on_dispatch_reply(self._reply(b"ok"))
        log.error.assert_not_called()

    def test_helpers_register_the_reply_handler(self):
        self.service.focus_window(ADDR)
        self.assertIs(
            self.connection.send_command_async.call_args.args[1],
            HyprlandService._on_dispatch_reply,
        )


if __name__ == "__main__":
    unittest.main()
