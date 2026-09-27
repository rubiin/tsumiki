"""Tests for ``PollingController``.

The controller exists to stop a slow command overlapping itself: the next run is
armed when the previous process exits, and a stopped run's completion is
dropped. Gio is mocked so the ordering can be asserted synchronously; the one
exception is the stderr flood, which needs a real child and a real main loop.
"""

import sys
import time
import unittest
from unittest import mock

from fabric.utils import GLib

from services import base as base_module
from services.base import PollingController

# Captured before any patching, so the flood test still drains for real.
_REAL_DRAIN = base_module._drain_stderr


def pump_main_loop(until, timeout: float = 20.0) -> bool:
    """Iterate the default main context until *until* holds, as GTK would."""
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while not until() and time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        time.sleep(0.002)
    return bool(until())


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
            # Stay running until told otherwise, so the start/exit window is visible.
            process.wait_async.side_effect = lambda _c, cb: self.waits.append(
                (process, cb)
            )
            self.processes.append(process)
            return process, mock.Mock()

        self.exec_async.side_effect = spawn

        timeout = mock.patch.object(base_module.GLib, "timeout_add", return_value=7)
        self.timeout_add = timeout.start()
        self.addCleanup(timeout.stop)
        remove = mock.patch.object(base_module.GLib, "source_remove")
        self.source_remove = remove.start()
        self.addCleanup(remove.stop)
        # The mock process has no stderr pipe; the real drain is tested below.
        drain = mock.patch.object(base_module, "_drain_stderr")
        self.drain = drain.start()
        self.addCleanup(drain.stop)

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

    def test_stop_removes_the_armed_timer(self):
        """Without the source id, a paused poller still fires its last tick."""
        controller = make_controller()
        controller.start()
        self.finish()
        self.assertEqual(1, self.timeout_add.call_count)

        controller.stop()

        self.source_remove.assert_called_once_with(7)

    def test_a_timer_that_already_fired_is_not_removed_again(self):
        controller = make_controller()
        controller.start()
        self.finish()
        # The armed source fires, and the controller polls once more.
        controller._tick()

        controller.stop()

        self.source_remove.assert_not_called()

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


class SlowCycleTest(unittest.TestCase):
    """A wedged child must be reported, not just silently ignored."""

    def setUp(self):
        self.clock = [0.0]
        for target, name, replacement in (
            (base_module, "_monotonic", lambda: self.clock[0]),
            (base_module, "logger", mock.Mock()),
        ):
            patcher = mock.patch.object(target, name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.log = base_module.logger

    def run_one_cycle(self, elapsed: float) -> None:
        """Start a poll and let it exit *elapsed* seconds later."""
        controller = make_controller(interval_ms=1000)
        process = mock.Mock()
        with (
            mock.patch.object(base_module, "_drain_stderr"),
            mock.patch.object(base_module, "exec_shell_command_async") as spawn,
        ):
            spawn.return_value = (process, mock.Mock())
            controller.start()
            self.clock[0] = elapsed
            callback = process.wait_async.call_args.args[1]
            callback(process, mock.Mock())

    def test_a_cycle_over_twice_the_interval_is_reported(self):
        self.run_one_cycle(elapsed=5.0)

        self.log.warning.assert_called_once()

    def test_a_cycle_within_the_interval_is_silent(self):
        self.run_one_cycle(elapsed=0.2)

        self.log.warning.assert_not_called()


class StderrFloodTest(unittest.TestCase):
    """A child that fills the stderr pipe must not end the poll chain.

    Fabric opens ``STDERR_PIPE`` but only streams stdout, so an undrained pipe
    fills at ~64 KB: the child blocks in ``write``, never exits, and the chain
    dies with no log line anywhere.
    """

    FLOOD_BYTES = 200_000

    def setUp(self):
        self.spawns: list = []
        self.drains: list = []
        real_exec = base_module.exec_shell_command_async

        def counting(command, on_line=None):
            self.spawns.append(command)
            return real_exec(command, on_line)

        def counting_drain(process, tag):
            self.drains.append(tag)
            return _REAL_DRAIN(process, tag)

        for name, replacement in (
            ("exec_shell_command_async", counting),
            ("_drain_stderr", counting_drain),
        ):
            patcher = mock.patch.object(base_module, name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.controller = PollingController(
            [
                sys.executable,
                "-c",
                f"import sys; sys.stderr.write('x' * {self.FLOOD_BYTES})",
            ],
            20,
            lambda _line: None,
            tag="Flood",
        )
        self.addCleanup(self.controller.stop)

    def test_every_spawn_drains_its_stderr(self):
        self.controller.start()

        self.assertEqual(["Flood"], self.drains)

    def test_the_chain_survives_a_command_that_floods_stderr(self):
        self.controller.start()

        # Two spawns means the first child exited and the next one was armed.
        survived = pump_main_loop(lambda: len(self.spawns) >= 2)

        self.assertTrue(survived, "the poll chain died after flooding stderr")


if __name__ == "__main__":
    unittest.main()
