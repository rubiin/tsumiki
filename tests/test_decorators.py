"""Tests for :func:`utils.decorators.run_worker_with_idle`.

The point of the helper is the hand-off: the worker runs off the GTK thread and
its value is delivered back through ``GLib.idle_add``, in that order.
"""

import contextlib
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import decorators
from utils.decorators import run_worker_with_idle


@contextlib.contextmanager
def captured_idle_adds():
    """Collect what would have been handed to the GTK main loop."""
    delivered: list = []
    with mock.patch.object(decorators.GLib, "idle_add") as idle_add:
        idle_add.side_effect = lambda fn, *args: delivered.append(args[0])
        yield delivered


class PoolIsolationTest(unittest.TestCase):
    """A hung helper must not be able to starve a queued file write."""

    def test_blocking_work_has_its_own_pool(self):
        self.assertIsNot(decorators._get_blocking_pool(), decorators._get_thread_pool())

    def test_hung_blocking_work_does_not_stall_the_quick_pool(self):
        release = threading.Event()
        self.addCleanup(release.set)
        # Two more than the quick pool holds, so a merged pool would be full.
        hung = [
            decorators.blocking_thread(release.wait, 10)
            for _ in range(decorators._cpu_count + 2)
        ]
        self.addCleanup(lambda: [future.cancel() for future in hung])

        self.assertEqual("written", decorators.thread(lambda: "written").result(5))

    def test_run_in_thread_submits_to_the_blocking_pool(self):
        with mock.patch.object(decorators, "blocking_thread") as blocking:

            @decorators.run_in_thread
            def work():
                return 1

            self.assertIs(blocking.return_value, work())

    def test_run_worker_with_idle_submits_to_the_blocking_pool(self):
        with mock.patch.object(decorators, "blocking_thread") as blocking:
            run_worker_with_idle(lambda: 1, lambda *_: None)

        blocking.assert_called_once()


class DebounceRemovalTest(unittest.TestCase):
    """The keyed helpers replaced it; it never wrapped or cleaned up."""

    def test_there_is_no_standalone_debounce_decorator(self):
        self.assertFalse(hasattr(decorators, "debounce"))


class RunWorkerWithIdleTest(unittest.TestCase):
    """The result reaches the callback on the main loop, not the worker."""

    def test_the_value_is_delivered_to_the_callback(self):
        with captured_idle_adds() as delivered:
            run_worker_with_idle(lambda a, b: a + b, lambda *_: None, 2, 3).result(2)

        self.assertEqual([5], delivered)

    def test_the_worker_runs_off_the_main_thread(self):
        main_thread = threading.get_ident()
        with captured_idle_adds() as delivered:
            run_worker_with_idle(lambda: threading.get_ident(), lambda *_: None).result(
                2
            )

        self.assertNotEqual(main_thread, delivered[0])

    def test_the_future_carries_the_value_too(self):
        with captured_idle_adds():
            future = run_worker_with_idle(lambda: "v", lambda *_: None)

        self.assertEqual("v", future.result(2))

    def test_keyword_arguments_reach_the_worker(self):
        seen = {}

        def worker(a, *, b):
            seen["args"] = (a, b)

        with captured_idle_adds():
            run_worker_with_idle(worker, lambda *_: None, 1, b=2).result(2)

        self.assertEqual((1, 2), seen["args"])

    def test_a_failing_worker_never_reaches_the_callback(self):
        def boom():
            raise ValueError("nope")

        with captured_idle_adds() as delivered:
            future = run_worker_with_idle(boom, lambda *_: None)

        with self.assertRaises(ValueError):
            future.result(2)
        self.assertEqual([], delivered)


if __name__ == "__main__":
    unittest.main()
