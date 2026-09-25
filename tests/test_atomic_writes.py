"""Tests for the atomic file writers in ``utils/functions.py``.

A crash or a failed dump must leave the previous file intact: a truncated
``config.toml`` or cache is worse than a stale one.
"""

import json
import os
import tempfile
import unittest
from unittest import mock

import psutil

from utils import functions as functions_module
from utils.functions import (
    CommandError,
    _atomic_write,
    ensure_directory,
    is_app_running,
    read_json_file,
    run_command,
    write_json_file,
    write_toml_file,
)


class EnsureDirectoryTest(unittest.TestCase):
    """ensure_directory is off-thread by default, which callers can race."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.target = os.path.join(self._tmpdir.name, "nested", "deeper")

    def test_sync_creates_the_directory_before_returning(self):
        ensure_directory(self.target, sync=True)

        self.assertTrue(os.path.isdir(self.target))

    def test_sync_is_repeatable(self):
        ensure_directory(self.target, sync=True)
        ensure_directory(self.target, sync=True)

        self.assertTrue(os.path.isdir(self.target))

    def test_the_default_is_off_thread(self):
        """A caller that writes straight after must ask for sync, or the
        write can land before the directory exists."""
        with mock.patch("utils.functions.thread") as pooled:
            ensure_directory(self.target)

        pooled.assert_called_once()

    def test_a_write_into_a_freshly_made_directory_succeeds(self):
        ensure_directory(self.target, sync=True)
        path = os.path.join(self.target, "data.json")
        write_json_file(path, {"a": 1}, sync=True)

        self.assertEqual({"a": 1}, read_json_file(path))


class AtomicWriteTest(unittest.TestCase):
    """The temp-file-then-rename contract."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.path = os.path.join(self._tmpdir.name, "data.json")
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("original")

    def test_replaces_the_file(self):
        _atomic_write(self.path, lambda handle: handle.write("replaced"))

        with open(self.path, encoding="utf-8") as handle:
            self.assertEqual("replaced", handle.read())

    def test_original_survives_a_failing_dump(self):
        def exploding_dump(handle):
            handle.write("half-written")
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            _atomic_write(self.path, exploding_dump)

        with open(self.path, encoding="utf-8") as handle:
            self.assertEqual("original", handle.read())

    def test_no_temp_files_are_left_behind(self):
        def exploding_dump(handle):
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            _atomic_write(self.path, exploding_dump)

        leftovers = [n for n in os.listdir(self._tmpdir.name) if n != "data.json"]
        self.assertEqual([], leftovers)

    def test_temp_file_is_created_beside_the_target(self):
        """A temp file elsewhere would be a cross-device rename."""
        with mock.patch.object(
            functions_module.tempfile,
            "mkstemp",
            wraps=functions_module.tempfile.mkstemp,
        ) as mkstemp:
            _atomic_write(self.path, lambda handle: handle.write("x"))

        self.assertEqual(
            self._tmpdir.name, mkstemp.call_args.kwargs["dir"]
        )


class WriteJsonFileTest(unittest.TestCase):
    """JSON writes are atomic and accept a list payload."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.path = os.path.join(self._tmpdir.name, "cache.json")

    def test_writes_a_list_payload(self):
        write_json_file(self.path, [{"id": 1}], sync=True)

        with open(self.path, encoding="utf-8") as handle:
            self.assertEqual([{"id": 1}], json.load(handle))

    def test_unserialisable_payload_keeps_the_old_file(self):
        write_json_file(self.path, {"keep": True}, sync=True)

        # A TypeError here is one the writer catches, so nothing is raised.
        write_json_file(self.path, {"bad": object()}, sync=True)

        with open(self.path, encoding="utf-8") as handle:
            self.assertEqual({"keep": True}, json.load(handle))

    def test_async_path_runs_on_the_pool(self):
        with mock.patch.object(functions_module, "thread") as worker:
            write_json_file(self.path, {"a": 1})

        worker.assert_called_once_with(write_json_file, self.path, {"a": 1}, sync=True)


class WriteTomlFileTest(unittest.TestCase):
    """TOML writes mirror the JSON writer's sync/async contract."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.path = os.path.join(self._tmpdir.name, "config.toml")

    def test_writes_toml(self):
        write_toml_file(self.path, {"styling": {"mode": "dark"}}, sync=True)

        from utils.functions import read_toml_file

        self.assertEqual({"styling": {"mode": "dark"}}, read_toml_file(self.path))

    def test_async_path_runs_on_the_pool(self):
        with mock.patch.object(functions_module, "thread") as worker:
            write_toml_file(self.path, {"a": 1})

        worker.assert_called_once_with(write_toml_file, self.path, {"a": 1}, sync=True)


class UpdateConfigKeyTest(unittest.TestCase):
    """The read-modify-write path must survive a failed dump."""

    """The read-modify-write path must not leave a truncated config behind."""

    def _write_config(self, text: str) -> str:
        path = os.path.join(self._tmpdir.name, "config.toml")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)

    def test_updates_a_nested_key(self):
        path = self._write_config('[styling]\nmode = "light"\n')

        with mock.patch.object(
            functions_module, "get_relative_path", return_value=path
        ):
            functions_module._update_config_key(["styling", "mode"], "dark")

        with open(path, encoding="utf-8") as handle:
            self.assertIn("'dark'", handle.read())

    def test_failed_dump_keeps_the_original_file(self):
        original = '[styling]\nmode = "light"\n'
        path = self._write_config(original)
        parsed = {"styling": {"mode": "light"}}

        with (
            mock.patch.object(functions_module, "get_relative_path", return_value=path),
            mock.patch.object(
                functions_module, "read_toml_file", return_value=parsed
            ),
            mock.patch.object(
                functions_module,
                "write_toml_file",
                side_effect=OSError("disk full"),
            ),
        ):
            # A failed write is logged, not raised, so this must not throw.
            functions_module._update_config_key(["styling", "mode"], "dark")

        with open(path, encoding="utf-8") as handle:
            self.assertEqual(original, handle.read())


class RunCommandCheckTest(unittest.TestCase):
    """check=True raises instead of reporting a failure as None."""

    def test_success_returns_stdout(self):
        self.assertEqual("hello\n", run_command(["echo", "hello"], check=True))

    def test_a_non_zero_exit_raises(self):
        with self.assertRaises(CommandError) as caught:
            run_command(["sh", "-c", "exit 3"], check=True)

        self.assertEqual(3, caught.exception.returncode)

    def test_the_exception_carries_stderr(self):
        with self.assertRaises(CommandError) as caught:
            run_command(["sh", "-c", "echo boom >&2; exit 3"], check=True)

        self.assertEqual("boom", caught.exception.stderr.strip())
        self.assertIn("boom", str(caught.exception))

    def test_the_exception_carries_stdout_too(self):
        """A command that fails after printing still has useful output."""
        with self.assertRaises(CommandError) as caught:
            run_command(["sh", "-c", "echo partial; exit 1"], check=True)

        self.assertEqual("partial", caught.exception.stdout.strip())

    def test_a_missing_program_raises_and_is_tagged(self):
        with self.assertRaises(CommandError) as caught:
            run_command(["definitely-not-a-real-binary-xyz"], check=True)

        self.assertEqual("missing", caught.exception.kind)
        self.assertIsNone(caught.exception.returncode)

    def test_a_timeout_raises_and_is_tagged(self):
        with self.assertRaises(CommandError) as caught:
            run_command(["sleep", "5"], timeout=0.1, check=True)

        self.assertEqual("timeout", caught.exception.kind)

    def test_a_plain_failure_is_tagged_neither_missing_nor_timeout(self):
        with self.assertRaises(CommandError) as caught:
            run_command(["false"], check=True)

        self.assertEqual("failed", caught.exception.kind)

    def test_the_default_contract_is_unchanged(self):
        """check=False must still return None and log, not raise."""
        self.assertIsNone(run_command(["false"]))
        self.assertIsNone(run_command(["definitely-not-a-real-binary-xyz"]))

    def test_the_timeout_reaches_the_process(self):
        with mock.patch.object(
            functions_module.subprocess, "run", return_value=mock.Mock(returncode=0)
        ) as run:
            run_command(["true"], timeout=2.5)

        self.assertEqual(2.5, run.call_args.kwargs["timeout"])

    def test_no_timeout_by_default(self):
        with mock.patch.object(
            functions_module.subprocess, "run", return_value=mock.Mock(returncode=0)
        ) as run:
            run_command(["true"])

        self.assertIsNone(run.call_args.kwargs["timeout"])

    def test_a_list_never_goes_through_a_shell(self):
        with mock.patch.object(
            functions_module.subprocess, "run", return_value=mock.Mock(returncode=0)
        ) as run:
            run_command(["echo", "hi"])

        self.assertFalse(run.call_args.kwargs["shell"])

    def test_a_string_always_goes_through_a_shell(self):
        with mock.patch.object(
            functions_module.subprocess, "run", return_value=mock.Mock(returncode=0)
        ) as run:
            run_command("echo hi")

        self.assertTrue(run.call_args.kwargs["shell"])


class RunCommandTest(unittest.TestCase):
    """``run_command`` is the one place that reports success reliably.

    Fabric's ``exec_shell_command`` returns the error text on a non-zero exit,
    so a caller testing it for ``False`` never sees a failure.
    """

    def test_returns_stdout_on_success(self):
        self.assertEqual("hello\n", run_command(["echo", "hello"]))

    def test_returns_none_on_failure(self):
        """The case exec_shell_command reports as a truthy error string."""
        self.assertIsNone(run_command(["sh", "-c", "echo boom >&2; exit 3"]))

    def test_failure_is_reported_even_with_empty_stderr(self):
        self.assertIsNone(run_command(["false"]))

    def test_list_arguments_are_not_shell_parsed(self):
        """A path with a space and a metacharacter must survive verbatim."""
        self.assertEqual("a b; rm -rf /\n", run_command(["echo", "a b; rm -rf /"]))

    def test_missing_program_is_not_an_exception(self):
        self.assertIsNone(run_command(["definitely-not-a-real-binary-xyz"]))

    def test_a_timeout_is_logged_rather_than_raised_by_default(self):
        with mock.patch("utils.functions.logger") as logger:
            self.assertIsNone(run_command(["sleep", "5"], timeout=0.1))

        logger.warning.assert_called_once()
        self.assertIn("timed out", logger.warning.call_args[0][0])

    def test_is_app_running_keys_off_the_exit_status(self):
        # pidof matches the process name, which is versioned in a venv, so ask
        # about this very process rather than a hardcoded name.
        self.assertTrue(is_app_running(psutil.Process().name()))
        self.assertFalse(is_app_running("definitely-not-a-real-binary-xyz"))


if __name__ == "__main__":
    unittest.main()
