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


class RunWorkerWithIdleTest(unittest.TestCase):
    """The result reaches the callback on the main loop, not the worker."""

    def test_the_value_is_delivered_to_the_callback(self):
        with captured_idle_adds() as delivered:
            run_worker_with_idle(
                lambda a, b: a + b, lambda *_: None, 2, 3
            ).result(2)

        self.assertEqual([5], delivered)

    def test_the_worker_runs_off_the_main_thread(self):
        main_thread = threading.get_ident()
        with captured_idle_adds() as delivered:
            run_worker_with_idle(
                lambda: threading.get_ident(), lambda *_: None
            ).result(2)

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
