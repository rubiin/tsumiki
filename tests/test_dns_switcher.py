"""Tests for the DNS switch sequencing in ``services/dns_switcher.py``.

Fabric's ``exec_shell_command_async`` does not use a shell, so the steps are
run one after another and ``changed`` is published only once they succeed.
Built via ``__new__`` and stubs: the real service starts a poller.
"""

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from services import base as base_module
from services import dns_switcher as dns_module
from services.dns_switcher import DnsSwitcherService
from utils import decorators


def make_service() -> DnsSwitcherService:
    service = DnsSwitcherService.__new__(DnsSwitcherService)
    service.emit = mock.Mock()
    return service


def make_polling_service() -> DnsSwitcherService:
    """A service carrying the per-poll state ``_on_dns_line`` reads and writes."""
    service = DnsSwitcherService.__new__(DnsSwitcherService)
    service.emit = mock.Mock()
    service.notify = mock.Mock()
    service._state = None
    service._current_label = "Default"
    service._first_line_of_poll = True
    return service


def fake_process(status: int) -> mock.Mock:
    """A Gio.Subprocess stand-in; ``wait_async`` calls back immediately."""
    process = mock.Mock()
    process.wait_finish.return_value = status

    def wait_async(_cancellable, callback, *_args):
        callback(process, mock.Mock())

    process.wait_async.side_effect = wait_async
    return process


class PollCommandTest(unittest.TestCase):
    """The poller must read device DNS: ``con show`` has no IP4.DNS field."""

    def setUp(self):
        self.service = dns_module.dns_switcher_service
        # __new__ hands back the shared singleton, so restore its real poller.
        self.addCleanup(setattr, self.service, "_poller", self.service._poller)
        self.addCleanup(self.service.pause_polling)
        self.poller_class = self._patch(base_module, "PollingController")
        self._patch(
            base_module, "find_executable", mock.Mock(return_value="/usr/bin/nmcli")
        )
        self._patch(dns_module, "NM", None)
        DnsSwitcherService(3000)

    def _patch(self, target, name, replacement=mock.DEFAULT):
        patcher = mock.patch.object(target, name, replacement)
        started = patcher.start()
        self.addCleanup(patcher.stop)
        return started

    def test_the_poller_asks_for_device_dns(self):
        """Regression: "con show" exits non-zero and prints no DNS at all."""
        argv = self.poller_class.call_args.args[0]

        self.assertIn("dev", argv)
        self.assertNotIn("con", argv)
        self.assertEqual(["nmcli", "-t", "-f", "IP4.DNS", "dev", "show"], argv)

    def test_the_stubbed_poller_is_started_without_spawning_nmcli(self):
        self.poller_class.return_value.start.assert_called_once_with()

    def test_the_safety_net_is_not_a_hot_loop(self):
        """3 s meant 28,800 nmcli spawns a day for a rarely changing label."""
        self.assertGreaterEqual(dns_module._POLL_INTERVAL_MS, 15_000)


class MissingNmcliTest(unittest.TestCase):
    """Without nmcli there is nothing to poll, and nothing to fail either."""

    def setUp(self):
        self.service = dns_module.dns_switcher_service
        self.service.pause_polling()
        self.addCleanup(setattr, self.service, "_poller", self.service._poller)

    def test_nothing_is_spawned(self):
        with (
            mock.patch.object(base_module, "find_executable", return_value=None),
            mock.patch.object(dns_module, "NM", None),
            mock.patch.object(base_module, "exec_shell_command_async") as spawn,
        ):
            DnsSwitcherService()

        spawn.assert_not_called()

    def test_the_widget_reads_a_safe_default(self):
        with (
            mock.patch.object(base_module, "find_executable", return_value=None),
            mock.patch.object(dns_module, "NM", None),
        ):
            DnsSwitcherService()

        self.assertEqual("Default", self.service.current)
        self.assertEqual("Default", self.service._current_label)


class NetworkManagerWatchTest(unittest.TestCase):
    """NM's own signals, not the interval, are what drive the refresh."""

    def setUp(self):
        self.service = make_polling_service()
        self.service._nm_client = None
        self.service._nm_handlers = []
        self.service._poller = mock.Mock()

        self.device = mock.Mock()
        self.connection = mock.Mock()
        self.connection.get_devices.return_value = [self.device]
        self.client = mock.Mock()
        self.client.get_primary_connection.return_value = self.connection

    def attach(self) -> None:
        self.service._on_nm_client(self.client, mock.Mock())

    def test_the_client_is_watched_for_the_primary_connection(self):
        self.attach()

        self.client.connect.assert_called_once_with(
            "notify::primary-connection", self.service._on_primary_connection
        )

    def test_the_connection_and_its_devices_are_watched(self):
        self.attach()

        self.connection.connect.assert_called_once_with(
            "notify::ip4-config", self.service._on_nm_dns_changed
        )
        self.device.connect.assert_called_once_with(
            "notify::ip4-config", self.service._on_nm_dns_changed
        )

    def test_an_ip_config_change_re_reads_the_dns(self):
        self.attach()
        self.service._poller.poll_now.reset_mock()

        self.service._on_nm_dns_changed()

        self.service._poller.poll_now.assert_called_once_with()

    def test_the_first_connection_still_re_reads_the_dns(self):
        self.attach()

        self.service._poller.poll_now.assert_called_once_with()

    def test_switching_connections_drops_the_old_handlers(self):
        self.attach()
        old_connection = self.client.get_primary_connection()
        replacement = mock.Mock()
        replacement.get_devices.return_value = []

        self.client.get_primary_connection.return_value = replacement
        self.service._on_primary_connection()

        old_connection.disconnect.assert_called_once()
        self.assertEqual(1, len(self.service._nm_handlers))

    def test_teardown_drops_the_handlers_and_stops_the_poller(self):
        self.attach()

        self.service.destroy()

        self.assertEqual([], self.service._nm_handlers)
        self.service._poller.stop.assert_called_once_with()

    def test_missing_bindings_leave_the_poll_in_charge(self):
        with mock.patch.object(dns_module, "NM", None):
            self.service._watch_network_manager()

        self.service._poller.poll_now.assert_not_called()

    def test_no_daemon_leaves_the_poll_in_charge(self):
        self.service._on_nm_client(None, mock.Mock())

        self.assertIsNone(self.service._nm_client)
        self.service._poller.poll_now.assert_not_called()


class DnsLineTest(unittest.TestCase):
    """One stdout line from ``nmcli dev show`` becomes the current DNS."""

    def setUp(self):
        self.service = make_polling_service()

    def feed(self, *lines: str) -> None:
        """Hand lines to the poller's callback, as the shared base does."""
        for line in lines:
            self.service._on_line(line)

    def test_a_device_line_sets_the_current_dns(self):
        self.feed("IP4.DNS[1]:192.168.18.1")

        self.assertEqual("192.168.18.1", self.service._state)
        self.assertEqual("192.168.18.1", self.service.current)

    def test_a_known_provider_is_labelled(self):
        self.feed("IP4.DNS[1]:1.1.1.1")

        self.assertEqual("Cloudflare", self.service._current_label)

    def test_an_unknown_server_is_labelled_with_its_own_address(self):
        self.feed("IP4.DNS[1]:192.168.18.1")

        self.assertEqual("192.168.18.1", self.service._current_label)

    def test_only_the_first_entry_of_a_poll_is_used(self):
        """``dev show`` lists every device; the first DNS line wins."""
        self.feed("IP4.DNS[1]:1.1.1.1", "IP4.DNS[1]:8.8.8.8")

        self.assertEqual("1.1.1.1", self.service._state)

    def test_a_new_dns_notifies_once(self):
        self.feed("IP4.DNS[1]:192.168.18.1")

        self.service.notify.assert_called_once_with("current")
        self.service.emit.assert_called_once_with("changed")

    def test_an_unchanged_dns_is_silent(self):
        self.feed("IP4.DNS[1]:192.168.18.1")
        self.service._mark_poll_start()

        self.feed("IP4.DNS[1]:192.168.18.1")

        self.service.notify.assert_called_once_with("current")
        self.service.emit.assert_called_once_with("changed")

    def test_an_empty_line_falls_back_to_the_default(self):
        """nmcli prints nothing for a device with no DNS field."""
        self.feed("IP4.DNS[1]:192.168.18.1")
        self.service._mark_poll_start()

        self.feed("")

        self.assertEqual("Default", self.service.current)
        self.assertEqual("Default", self.service._current_label)

    def test_a_realistic_provider_block_is_read(self):
        """The terse output of ``nmcli -t -f IP4.DNS dev show``, verbatim."""
        self.service._mark_poll_start()
        self.feed("IP4.DNS[1]:1.1.1.1", "IP4.DNS[2]:1.0.0.1")

        self.assertEqual("1.1.1.1", self.service.current)
        self.assertEqual("Cloudflare", self.service._current_label)


class SwitchCommandsTest(unittest.TestCase):
    """The nmcli steps are argv lists, not a shell chain."""

    def test_steps_are_argv_lists_in_order(self):
        commands = DnsSwitcherService._switch_commands("UUID", "1.1.1.1", "yes")

        self.assertEqual(
            [
                ["pkexec", "nmcli", "con", "mod", "UUID", "ipv4.dns", "1.1.1.1"],
                [
                    "pkexec",
                    "nmcli",
                    "con",
                    "mod",
                    "UUID",
                    "ipv4.ignore-auto-dns",
                    "yes",
                ],
                ["nmcli", "con", "down", "UUID"],
                ["nmcli", "con", "up", "UUID"],
            ],
            commands,
        )

    def test_no_shell_metacharacters_leak_into_a_step(self):
        """A literal '&&' would be passed to nmcli as an argument."""
        commands = DnsSwitcherService._switch_commands("UUID", "1.1.1.1", "yes")

        for command in commands:
            self.assertNotIn("&&", command)
            for argument in command:
                self.assertNotIn("&&", argument)

    def test_reset_clears_the_server_list(self):
        commands = DnsSwitcherService._switch_commands("UUID", "", "no")

        self.assertIn("", commands[0])
        self.assertEqual("no", commands[1][-1])


class RunCommandsTest(unittest.TestCase):
    """Steps run in order and stop at the first failure."""

    def setUp(self):
        self.service = make_service()
        patcher = mock.patch.object(dns_module, "exec_shell_command_async")
        self.exec_async = patcher.start()
        self.addCleanup(patcher.stop)

    def _queue(self, *statuses: int):
        """Make exec return one process per call, reporting *statuses*."""
        self.exec_async.side_effect = [
            (fake_process(status), mock.Mock()) for status in statuses
        ]

    def _run(self, commands, results):
        with mock.patch.object(DnsSwitcherService, "_on_switch_finished") as done:
            self.service._run_commands(commands, done)
        return done

    def test_runs_every_step_in_order(self):
        commands = [["first"], ["second"], ["third"]]
        self._queue(0, 0, 0)

        self._run(commands, None)

        self.assertEqual(
            [call.args[0] for call in self.exec_async.call_args_list], commands
        )

    def test_reports_success_only_after_the_last_step(self):
        self._queue(0, 0, 0)
        seen_after_calls = []

        def on_finished(ok):
            seen_after_calls.append((ok, self.exec_async.call_count))

        self.service._run_commands([["a"], ["b"]], on_finished)

        self.assertEqual([(True, 2)], seen_after_calls)

    def test_stops_at_the_first_failure(self):
        self._queue(0, 3)
        results = []

        self.service._run_commands([["a"], ["b"], ["c"]], results.append)

        self.assertEqual([False], results)
        self.assertEqual(2, self.exec_async.call_count, "third step should not run")

    def test_spawn_failure_reports_failure(self):
        self.exec_async.side_effect = dns_module.GLib.Error("no such command")
        results = []

        self.service._run_commands([["a"]], results.append)

        self.assertEqual([False], results)


class SwitchFinishedTest(unittest.TestCase):
    """Only a completed switch publishes a change."""

    def setUp(self):
        self.service = make_service()

    def test_success_emits_changed(self):
        self.service._on_switch_finished(True)

        self.service.emit.assert_called_once_with("changed")

    def test_failure_stays_silent(self):
        self.service._on_switch_finished(False)

        self.service.emit.assert_not_called()


class ActiveConnectionTest(unittest.TestCase):
    """The ``nmcli con show`` lookup must not run on the GTK main thread."""

    def setUp(self):
        self.service = make_service()
        self.output = "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d\n"
        self.threads: list[int] = []
        self.entered = threading.Event()
        self.idled: list[tuple] = []
        self.gate = threading.Event()  # held so nmcli is still running

        self.pool = ThreadPoolExecutor(max_workers=1)
        self._patch(decorators, "thread", self.pool.submit)
        self._patch(dns_module, "exec_shell_command", self._fake_exec)
        self._patch(decorators, "GLib", mock.Mock(idle_add=self._capture_idle))
        runner = mock.patch.object(DnsSwitcherService, "_run_commands")
        self.run_commands = runner.start()
        self.addCleanup(runner.stop)

        # Release the worker, then join it, so it cannot reach the next test.
        self.addCleanup(self.pool.shutdown)
        self.addCleanup(self.gate.set)

    def _patch(self, target, name, replacement):
        patcher = mock.patch.object(target, name, replacement)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _fake_exec(self, _command):
        self.threads.append(threading.get_ident())
        self.entered.set()
        self.gate.wait(5)
        return self.output

    def _capture_idle(self, callback, *args):
        self.idled.append((callback, args))
        return 1

    def wait_for_worker(self) -> None:
        self.assertTrue(self.entered.wait(5), "nmcli was never queried")

    def release_worker(self) -> None:
        self.gate.set()
        deadline = time.monotonic() + 5
        while not self.idled and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(self.idled, "the worker never reached idle_add")

    def dispatch(self) -> None:
        for callback, args in self.idled:
            callback(*args)

    def test_the_lookup_does_not_block_the_caller(self):
        calling_thread = threading.get_ident()

        self.service.reset_to_default()
        self.wait_for_worker()

        self.assertNotEqual(calling_thread, self.threads[0], "nmcli blocked the loop")
        self.assertEqual([], self.idled, "the switch was queued before the lookup")

    def test_the_switch_runs_after_the_main_loop_dispatch(self):
        self.service.reset_to_default()
        self.wait_for_worker()
        self.release_worker()
        self.assertEqual([], self.run_commands.call_args_list)

        self.dispatch()

        commands = self.run_commands.call_args.args[0]
        self.assertEqual("9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d", commands[0][4])

    def test_no_active_connection_runs_nothing(self):
        self.output = ""

        self.service.reset_to_default()
        self.wait_for_worker()
        self.release_worker()
        self.dispatch()

        self.run_commands.assert_not_called()
        self.service.emit.assert_not_called()

    def test_nmcli_error_text_is_not_mistaken_for_a_connection(self):
        self.output = "Error: unknown connection"

        self.service.set_dns("1.1.1.1")
        self.wait_for_worker()
        self.release_worker()
        self.dispatch()

        self.run_commands.assert_not_called()


class SetDnsTest(unittest.TestCase):
    """set_dns routes through the runner instead of emitting eagerly."""

    def setUp(self):
        self.service = make_service()
        patcher = mock.patch.object(
            DnsSwitcherService,
            "_with_active_connection",
            # Deliver a UUID, as the main-loop hop would.
            side_effect=lambda on_found: on_found("UUID"),
        )
        self.with_connection = patcher.start()
        self.addCleanup(patcher.stop)
        runner = mock.patch.object(DnsSwitcherService, "_run_commands")
        self.run_commands = runner.start()
        self.addCleanup(runner.stop)

    def test_switch_runs_the_command_sequence(self):
        self.service.set_dns("1.1.1.1", "1.0.0.1")

        commands = self.run_commands.call_args.args[0]
        self.assertEqual("UUID", commands[0][4])
        self.assertEqual("1.1.1.1 1.0.0.1", commands[0][-1])

    def test_nothing_is_emitted_before_the_commands_run(self):
        self.service.set_dns("1.1.1.1")

        self.service.emit.assert_not_called()

    def test_invalid_dns_never_reaches_the_runner(self):
        self.service.set_dns("1.1.1.1; rm -rf /")

        self.run_commands.assert_not_called()
        self.with_connection.assert_not_called()
        self.service.emit.assert_not_called()

    def test_reset_uses_the_same_sequence(self):
        self.service.reset_to_default()

        commands = self.run_commands.call_args.args[0]
        self.assertIn("", commands[0])


if __name__ == "__main__":
    unittest.main()
