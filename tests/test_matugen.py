"""Tests for MatugenService.generate_sync failure handling.

The service is built with ``__new__`` and the command runner is mocked, so
nothing is spawned and no matugen install is required.
"""

import unittest
from unittest import mock

from services.matugen import MatugenService


def _make_service(**style_config) -> MatugenService:
    service = MatugenService.__new__(MatugenService)
    service._style_config = style_config
    service._mode = style_config.get("mode", "dark")
    service.emit = mock.Mock()
    return service


def _emitted(service, signal) -> list:
    return [c for c in service.emit.call_args_list if c.args and c.args[0] == signal]


class GenerateSyncResultTest(unittest.TestCase):
    """The return value is the only thing that tells the caller matugen ran."""

    def test_failure_emits_failed_and_returns_false(self):
        service = _make_service()

        with (
            mock.patch("services.matugen.os.path.exists", return_value=True),
            mock.patch("services.matugen.helpers.run_command", return_value=None),
        ):
            result = service.generate_sync("/tmp/wall.png")

        self.assertFalse(result)
        self.assertEqual(len(_emitted(service, "generation_failed")), 1)
        self.assertEqual(_emitted(service, "colors_generated"), [])

    def test_success_emits_generated_and_returns_true(self):
        service = _make_service()

        with (
            mock.patch("services.matugen.os.path.exists", return_value=True),
            mock.patch(
                "services.matugen.helpers.run_command", return_value="scheme written"
            ),
        ):
            result = service.generate_sync("/tmp/wall.png")

        self.assertTrue(result)
        self.assertEqual(len(_emitted(service, "colors_generated")), 1)
        self.assertEqual(_emitted(service, "generation_failed"), [])

    def test_empty_output_is_not_treated_as_failure(self):
        """``-q`` makes an empty stdout normal, so key off exit status alone."""
        service = _make_service()

        with (
            mock.patch("services.matugen.os.path.exists", return_value=True),
            mock.patch("services.matugen.helpers.run_command", return_value="") as run,
        ):
            result = service.generate_sync("/tmp/wall.png")

        run.assert_called_once()
        self.assertTrue(result)
        self.assertEqual(len(_emitted(service, "colors_generated")), 1)
        self.assertEqual(_emitted(service, "generation_failed"), [])

    def test_missing_image_short_circuits_before_running_command(self):
        service = _make_service()

        with (
            mock.patch("services.matugen.os.path.exists", return_value=False),
            mock.patch("services.matugen.helpers.run_command") as run,
        ):
            result = service.generate_sync("/tmp/missing.png")

        self.assertFalse(result)
        run.assert_not_called()
        self.assertEqual(len(_emitted(service, "generation_failed")), 1)
        self.assertEqual(_emitted(service, "colors_generated"), [])

    def test_runner_exception_is_reported_as_failure(self):
        service = _make_service()

        with (
            mock.patch("services.matugen.os.path.exists", return_value=True),
            mock.patch(
                "services.matugen.helpers.run_command", side_effect=OSError("boom")
            ),
        ):
            result = service.generate_sync("/tmp/wall.png")

        self.assertFalse(result)
        self.assertEqual(len(_emitted(service, "generation_failed")), 1)
        self.assertEqual(_emitted(service, "colors_generated"), [])


class BuildCmdTest(unittest.TestCase):
    """A list argv keeps the wallpaper path out of a shell."""

    def test_cmd_is_argv_list_with_path_as_one_element(self):
        service = _make_service(scheme="scheme-content", contrast=0.25, mode="light")
        path = "/tmp/my wall's paper.png"

        cmd = service._build_cmd(path)

        self.assertIsInstance(cmd, list)
        self.assertEqual(cmd[0], "matugen")
        self.assertIn(path, cmd)
        self.assertIn("scheme-content", cmd)
        self.assertIn("0.25", cmd)
        self.assertIn("light", cmd)
