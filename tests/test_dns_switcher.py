"""Tests for the DNS switch sequencing in ``services/dns_switcher.py``.

Fabric's ``exec_shell_command_async`` does not use a shell, so the steps are
run one after another and ``changed`` is published only once they succeed.
Built via ``__new__`` and stubs: the real service starts a poller.
"""

import unittest
from unittest import mock

from services import dns_switcher as dns_module
from services.dns_switcher import DnsSwitcherService


def make_service() -> DnsSwitcherService:
    service = DnsSwitcherService.__new__(DnsSwitcherService)
    service.emit = mock.Mock()
    return service


def make_polling_service() -> DnsSwitcherService:
    """A service carrying the per-poll state ``_on_dns_line`` reads and writes."""
    service = DnsSwitcherService.__new__(DnsSwitcherService)
    service.emit = mock.Mock()
    service.notify = mock.Mock()
    service._current = None
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
        patcher = mock.patch.object(dns_module, "PollingController")
        self.poller_class = patcher.start()
        self.addCleanup(patcher.stop)
        DnsSwitcherService(3000)

    def test_the_poller_asks_for_device_dns(self):
        """Regression: "con show" exits non-zero and prints no DNS at all."""
        argv = self.poller_class.call_args.args[0]

        self.assertIn("dev", argv)
        self.assertNotIn("con", argv)
        self.assertEqual(["nmcli", "-t", "-f", "IP4.DNS", "dev", "show"], argv)

    def test_the_stubbed_poller_is_started_without_spawning_nmcli(self):
        self.poller_class.return_value.start.assert_called_once_with()


class DnsLineTest(unittest.TestCase):
    """One stdout line from ``nmcli dev show`` becomes the current DNS."""

    def setUp(self):
        self.service = make_polling_service()

    def test_a_device_line_sets_the_current_dns(self):
        self.service._on_dns_line("IP4.DNS[1]:192.168.18.1")

        self.assertEqual("192.168.18.1", self.service._current)
        self.assertEqual("192.168.18.1", self.service.current)

    def test_a_known_provider_is_labelled(self):
        self.service._on_dns_line("IP4.DNS[1]:1.1.1.1")

        self.assertEqual("Cloudflare", self.service._current_label)

    def test_an_unknown_server_is_labelled_with_its_own_address(self):
        self.service._on_dns_line("IP4.DNS[1]:192.168.18.1")

        self.assertEqual("192.168.18.1", self.service._current_label)

    def test_only_the_first_entry_of_a_poll_is_used(self):
        """``dev show`` lists every device; the first DNS line wins."""
        self.service._on_dns_line("IP4.DNS[1]:1.1.1.1")
        self.service._on_dns_line("IP4.DNS[1]:8.8.8.8")

        self.assertEqual("1.1.1.1", self.service._current)

    def test_a_new_dns_notifies_once(self):
        self.service._on_dns_line("IP4.DNS[1]:192.168.18.1")

        self.service.notify.assert_called_once_with("current")
        self.service.emit.assert_called_once_with("changed")

    def test_an_unchanged_dns_is_silent(self):
        self.service._on_dns_line("IP4.DNS[1]:192.168.18.1")
        self.service._mark_poll_start()

        self.service._on_dns_line("IP4.DNS[1]:192.168.18.1")

        self.service.notify.assert_called_once_with("current")
        self.service.emit.assert_called_once_with("changed")


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


class SetDnsTest(unittest.TestCase):
    """set_dns routes through the runner instead of emitting eagerly."""

    """``set_dns`` must route through the sequence, not emit straight away."""

    def setUp(self):
        self.service = make_service()
        patcher = mock.patch.object(
            DnsSwitcherService, "_get_active_connection", return_value="UUID"
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        runner = mock.patch.object(DnsSwitcherService, "_run_commands")
        self.run_commands = runner.start()
        self.addCleanup(runner.stop)

    def test_switch_runs_the_command_sequence(self):
        self.service.set_dns("1.1.1.1", "1.0.0.1")

        commands = self.run_commands.call_args.args[0]
        self.assertEqual("1.1.1.1 1.0.0.1", commands[0][-1])

    def test_nothing_is_emitted_before_the_commands_run(self):
        self.service.set_dns("1.1.1.1")

        self.service.emit.assert_not_called()

    def test_invalid_dns_never_reaches_the_runner(self):
        self.service.set_dns("1.1.1.1; rm -rf /")

        self.run_commands.assert_not_called()
        self.service.emit.assert_not_called()

    def test_reset_uses_the_same_sequence(self):
        self.service.reset_to_default()

        commands = self.run_commands.call_args.args[0]
        self.assertIn("", commands[0])


if __name__ == "__main__":
    unittest.main()
