"""Tests for ``PolledCommandService``, the base both polled services share.

The base exists to make a poll that reads the same value again silent, to keep
a missing binary from costing one failed spawn per interval, and to give the
poller a teardown that actually works. Nothing here runs a real command.
"""

import unittest
from unittest import mock

from services import base as base_module
from services.base import IGNORED, PolledCommandService


class FakeService(PolledCommandService):
    """A polled service whose state is the first token of its stdout line."""

    def parse_status(self, line: str) -> str:
        parts = line.split()
        return parts[0] if parts else IGNORED


def make_service(binary: str | None = "/usr/bin/fake-cmd") -> FakeService:
    """A service with the poller stubbed, so no command is ever spawned."""
    with (
        mock.patch.object(base_module, "PollingController") as controller,
        mock.patch.object(base_module, "find_executable", return_value=binary),
    ):
        controller.return_value = mock.Mock(running=False)
        return FakeService(["fake-cmd", "status"], 1000, "parse_status", tag="Fake")


class StateTest(unittest.TestCase):
    """``changed`` is a transition signal, not a per-poll heartbeat."""

    def setUp(self):
        self.service = make_service()
        self.service.emit = mock.Mock()

    def test_a_new_value_is_published(self):
        self.service._on_line("ok")

        self.assertEqual("ok", self.service._state)
        self.service.emit.assert_called_once_with("changed")

    def test_the_same_value_again_is_silent(self):
        self.service._on_line("ok")

        self.service._on_line("ok")

        self.service.emit.assert_called_once_with("changed")

    def test_a_back_and_forth_is_two_transitions(self):
        self.service._on_line("ok")
        self.service._on_line("down")

        self.assertEqual(
            [mock.call("changed"), mock.call("changed")],
            self.service.emit.call_args_list,
        )

    def test_an_ignored_line_changes_nothing(self):
        self.service._on_line("ok")

        self.service._on_line("")

        self.assertEqual("ok", self.service._state)
        self.service.emit.assert_called_once_with("changed")

    def test_set_state_reports_whether_it_published(self):
        self.assertTrue(self.service._set_state("ok"))
        self.assertFalse(self.service._set_state("ok"))


class MissingBinaryTest(unittest.TestCase):
    """A command that is not installed must cost nothing to skip."""

    def setUp(self):
        self.service = make_service(binary=None)
        self.service.emit = mock.Mock()

    def test_the_poller_is_never_started(self):
        self.service._poller.start.assert_not_called()
        self.assertFalse(self.service._poller.running)

    def test_nothing_is_spawned(self):
        with mock.patch.object(base_module, "exec_shell_command_async") as spawn:
            self.service.resume_polling()

        spawn.assert_not_called()

    def test_the_state_degrades_to_its_default(self):
        self.assertIsNone(self.service._state)
        self.service.resume_polling()
        self.service.emit.assert_not_called()

    def test_a_later_install_is_picked_up(self):
        with mock.patch.object(
            base_module, "find_executable", return_value="/bin/fake-cmd"
        ):
            self.service.resume_polling()

        self.service._poller.start.assert_called_once_with()


class TeardownTest(unittest.TestCase):
    """Fabric's ``Service`` has no ``destroy``, so the base must not chain to it."""

    def test_destroy_stops_the_poller(self):
        service = make_service()

        service.destroy()

        service._poller.stop.assert_called_once_with()

    def test_destroy_leaves_the_service_usable(self):
        """The old ``_stop_polling()``/``super().destroy()`` pair raised instead."""
        service = make_service()

        service.destroy()

        service.resume_polling()
        service._poller.start.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
