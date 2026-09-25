"""Tests for ``PollingController``.

The controller exists to stop a slow command overlapping itself: the next run is
armed when the previous process exits, and a stopped run's completion is
dropped. Gio is mocked so the ordering can be asserted synchronously.
"""

import unittest
from unittest import mock

from services import base as base_module
from services.base import PollingController


def make_controller(**kwargs) -> PollingController:
    """A controller whose processes invoke their wait callback immediately."""
    self = PollingController(
        kwargs.pop("command", ["poll-cmd"]),
        kwargs.pop("interval_ms", 1000),
        kwargs.pop("on_line", mock.Mock()),
        **kwargs,
    )
    return self


class PollingControllerTest(unittest.TestCase):
    """The next run is armed on exit, and a stopped run never arms one."""

    def setUp(self):
        patcher = mock.patch.object(base_module, "exec_shell_command_async")
        self.exec_async = patcher.start()
        self.addCleanup(patcher.stop)

        self.processes = []
        self.waits = []

        def spawn(command, on_line):
            process = mock.Mock()
            process.wait_finish.return_value = 0
            # The process stays "running" until the test says otherwise, so the
            # window between starting a command and it exiting is observable.
            process.wait_async.side_effect = lambda _c, cb: self.waits.append(
                (process, cb)
            )
            self.processes.append(process)
            return process, mock.Mock()

        self.exec_async.side_effect = spawn

        timeout = mock.patch.object(base_module.GLib, "timeout_add")
        self.timeout_add = timeout.start()
        self.addCleanup(timeout.stop)

    def finish(self, index: int = 0) -> None:
        """Let the process started at *index* exit."""
        process, callback = self.waits[index]
        callback(process, mock.Mock())

    def test_start_polls_immediately(self):
        controller = make_controller()

        controller.start()

        self.exec_async.assert_called_once()
        self.assertEqual(["poll-cmd"], self.exec_async.call_args.args[0])
        self.assertTrue(controller.running)

    def test_start_twice_does_not_double_poll(self):
        controller = make_controller()

        controller.start()
        controller.start()

        self.assertEqual(1, self.exec_async.call_count)

    def test_next_run_is_armed_only_after_the_process_exits(self):
        """The overlap fix: no timer while the command is still running."""
        controller = make_controller()
        controller.start()

        self.assertEqual(0, self.timeout_add.call_count, "armed while still running")

    def test_the_exit_arms_exactly_one_more_run(self):
        controller = make_controller()
        controller.start()

        self.finish()

        self.assertEqual(1, self.timeout_add.call_count)
        interval, callback = self.timeout_add.call_args.args
        self.assertEqual(1000, interval)
        # Bound methods compare equal only by __self__/__func__.
        self.assertEqual(controller._tick.__func__, callback.__func__)
        self.assertIs(controller, callback.__self__)

    def test_the_tick_starts_the_next_run_and_repeats(self):
        controller = make_controller()
        controller.start()
        self.processes[0].wait_async.call_args.args[1](self.processes[0], mock.Mock())

        self.assertFalse(controller._tick())
        self.assertEqual(2, self.exec_async.call_count)
        # ...and the second exit arms a third.
        self.finish(1)
        self.assertEqual(2, self.timeout_add.call_count)

    def test_stop_drops_the_exit_of_a_run_in_flight(self):
        """Pausing must not leave a timer armed."""
        controller = make_controller()
        controller.start()

        controller.stop()
        self.finish()

        self.assertEqual(0, self.timeout_add.call_count)
        self.assertFalse(controller.running)

    def test_a_restart_does_not_get_the_old_runs_completion(self):
        controller = make_controller()
        controller.start()

        controller.stop()
        controller.start()
        # The first process finally exits, long after it was superseded.
        self.finish(0)

        self.assertEqual(0, self.timeout_add.call_count, "stale exit armed a timer")

    def test_a_command_that_cannot_start_still_keeps_polling(self):
        self.exec_async.side_effect = base_module.GLib.Error("no such command")
        controller = make_controller()

        controller.start()

        self.assertEqual(1, self.timeout_add.call_count)

    def test_on_start_runs_before_each_command(self):
        starts = []
        controller = make_controller(on_start=lambda: starts.append(1))

        controller.start()
        self.finish()
        controller._tick()

        self.assertEqual(2, len(starts))

    def test_lines_are_forwarded_to_the_callback(self):
        on_line = mock.Mock()
        controller = make_controller(on_line=on_line)

        controller.start()
        # Fabric calls the per-line callback itself.
        on_line("STATUS Connected")

        on_line.assert_called_once_with("STATUS Connected")


if __name__ == "__main__":
    unittest.main()
