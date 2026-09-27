"""Tests for the WARP toggle in ``services/cloudflare_warp.py``.

``warp-cli connect`` blocks on the privileged warp-svc daemon for seconds, so it
must never run on the GTK main thread, and ``changed`` must not fire until the
command has actually finished. The service is built via ``__new__`` because the
real one starts a poller; ``run_worker_with_idle`` is the real one, with
``idle_add`` captured so the main-loop hop is observable.
"""

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from services import cloudflare_warp as warp_module
from services.cloudflare_warp import CloudflareWarpService
from utils import decorators


def make_service() -> CloudflareWarpService:
    """The shared singleton with its poller halted, so nothing else emits."""
    service = CloudflareWarpService.__new__(CloudflareWarpService)
    service.pause_polling()
    service._connected = False
    service.emit = mock.Mock()
    return service


class WarpToggleTest(unittest.TestCase):
    """Drives the real worker/idle chain by hand, with a stuck ``warp-cli``."""

    def setUp(self):
        self.service = make_service()
        self.result = "Success"  # run_command's stdout, i.e. success
        self.entered = threading.Event()
        self.gate = threading.Event()  # released to let warp-cli "return"

        self.threads: list[int] = []
        self.idled: list[tuple] = []
        self.argv: list[str] = []
        self.kwargs: dict = {}

        # A per-test pool, so a stuck worker can be joined instead of leaking.
        self.pool = ThreadPoolExecutor(max_workers=1)
        self._patch(decorators, "thread", self.pool.submit)
        self._patch(warp_module, "run_command", self._fake_run_command)
        self._patch(warp_module, "exec_shell_command_async", mock.Mock())
        self._patch(decorators, "GLib", mock.Mock(idle_add=self._capture_idle))

        # Cleanups run last-in-first-out: release the worker, then join it, so it
        # can never reach the next test's idle_add.
        self.addCleanup(self.pool.shutdown)
        self.addCleanup(self.gate.set)

    def _patch(self, target, name, replacement):
        patcher = mock.patch.object(target, name, replacement)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _fake_run_command(self, argv, **kwargs):
        self.threads.append(threading.get_ident())
        self.argv, self.kwargs = argv, kwargs
        self.entered.set()
        self.gate.wait(5)  # warp-cli is stuck talking to warp-svc
        return self.result

    def _capture_idle(self, callback, *args):
        self.idled.append((callback, args))
        return 1

    def wait_for_worker(self) -> None:
        self.assertTrue(self.entered.wait(5), "warp-cli was never dispatched")

    def release_worker(self) -> None:
        """Let warp-cli return, then wait for the worker to hand off to idle_add."""
        self.gate.set()
        deadline = time.monotonic() + 5
        while not self.idled and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(self.idled, "the worker never reached idle_add")

    def dispatch(self) -> None:
        """Run the queued callbacks, as the GTK main loop would."""
        for callback, args in self.idled:
            callback(*args)

    # ── The GTK handler must not wait on the daemon ──

    def test_the_handler_does_not_block_on_warp_cli(self):
        """The reported bug: the main loop stopped for 0.5-3s on every toggle."""
        calling_thread = threading.get_ident()

        self.service.toggle_warp()

        self.wait_for_worker()
        self.assertNotEqual(calling_thread, self.threads[0], "warp-cli blocked us")
        self.assertFalse(self.gate.is_set(), "the worker should still be blocked")
        self.assertEqual([], self.idled, "nothing may be published before it exits")

    def test_the_command_is_bounded_by_a_timeout(self):
        """run_command defaults to no timeout, so a wedged daemon would leak."""
        self.service.connect_warp()

        self.wait_for_worker()
        self.assertEqual(warp_module._WARP_CLI_TIMEOUT, self.kwargs["timeout"])

    def test_the_argv_names_the_action(self):
        self.service.connect_warp()

        self.wait_for_worker()
        self.assertEqual(["warp-cli", "connect"], self.argv)

    # ── ``changed`` fires only after the command has run ──

    def test_nothing_is_published_before_the_main_loop_dispatch(self):
        self.service._connected = True
        self.service.disconnect_warp()
        self.wait_for_worker()
        self.release_worker()

        self.assertEqual(1, len(self.idled), "one callback should be queued")
        self.service.emit.assert_not_called()
        self.assertTrue(self.service.connected, "state must wait for the command")

    def test_success_updates_the_state_and_emits(self):
        self.service.connect_warp()
        self.wait_for_worker()
        self.release_worker()
        self.dispatch()

        self.assertTrue(self.service.connected)
        self.service.emit.assert_called_once_with("changed")

    def test_success_refreshes_the_status(self):
        self.service.connect_warp()
        self.wait_for_worker()
        self.release_worker()
        self.dispatch()

        self.assertEqual(
            "warp-cli status", warp_module.exec_shell_command_async.call_args.args[0]
        )

    def test_a_failed_command_publishes_nothing(self):
        self.result = None  # run_command reports failure as None
        self.service.connect_warp()
        self.wait_for_worker()
        self.release_worker()
        self.dispatch()

        self.service.emit.assert_not_called()
        self.assertFalse(self.service.connected, "a failed connect must not claim ok")


class WarpArgvTest(unittest.TestCase):
    """Which warp-cli action a toggle dispatches."""

    def setUp(self):
        self.service = make_service()
        self.ran: list[str] = []

        # Inline, so the action is observable without a main loop.
        def inline(worker, callback, *args):
            return callback(worker(*args))

        for name, replacement in (
            ("run_worker_with_idle", inline),
            ("run_command", self._record),
            ("exec_shell_command_async", mock.Mock()),
        ):
            patcher = mock.patch.object(warp_module, name, replacement)
            self.addCleanup(patcher.stop)
            patcher.start()

    def _record(self, argv, **_kwargs):
        self.ran.append(argv[-1])
        return ""

    def test_a_disconnected_service_connects(self):
        self.service.toggle_warp()

        self.assertEqual(["connect"], self.ran)

    def test_a_connected_service_disconnects(self):
        self.service._connected = True

        self.service.toggle_warp()

        self.assertEqual(["disconnect"], self.ran)


if __name__ == "__main__":
    unittest.main()
