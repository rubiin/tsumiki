"""Tests for the atomic file writers in ``utils/functions.py``.

A crash or a failed dump must leave the previous file intact: a truncated
``config.toml`` or cache is worse than a stale one.
"""

import json
import os
import tempfile
import unittest
from unittest import mock

from utils import functions as functions_module
from utils.functions import _atomic_write, write_json_file, write_toml_file


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


if __name__ == "__main__":
    unittest.main()
