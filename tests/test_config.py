"""Tests for utils/config.py — configuration loading and merging."""

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from utils.config import (
    _EXCLUDED_SCHEMA_KEYS,
    _LIST_CONFIG_KEYS,
    TsumikiConfig,
)

_DEFAULT_PARSED = {
    "general": {},
    "widgets": {},
    "layout": {},
    "modules": {},
    "styling": {},
}


class ExcludedKeysTest(unittest.TestCase):
    """Verify the frozen config constants for schema merging."""

    def test_schema_key_excluded(self):
        self.assertIn("$schema", _EXCLUDED_SCHEMA_KEYS)

    def test_list_config_keys(self):
        self.assertIn("widget_groups", _LIST_CONFIG_KEYS)
        self.assertIn("collapsible_groups", _LIST_CONFIG_KEYS)


class TsumikiConfigSingletonTest(unittest.TestCase):
    """Test singleton behaviour of TsumikiConfig."""

    def setUp(self):
        TsumikiConfig._instance = None

    def tearDown(self):
        TsumikiConfig._instance = None

    def _make_config(self, parsed_data=None):
        if parsed_data is None:
            parsed_data = dict(_DEFAULT_PARSED)
        with (
            mock.patch(
                "utils.config.get_relative_path",
                return_value="/tmp",
            ),
            mock.patch(
                "utils.config.os.path.exists",
                return_value=True,
            ),
            mock.patch(
                "utils.config.read_toml_file",
                return_value=parsed_data,
            ),
            mock.patch("utils.config.validate_config_enums"),
            mock.patch("utils.config.validate_widgets"),
        ):
            return TsumikiConfig()

    def test_same_instance(self):
        a = self._make_config()
        b = TsumikiConfig()
        self.assertIs(a, b)

    def test_loaded_only_once(self):
        a = self._make_config()
        b = TsumikiConfig()
        self.assertIs(a, b)


class LoadConfigTest(unittest.TestCase):
    """Test _load_config with mocked file I/O."""

    def setUp(self):
        TsumikiConfig._instance = None

    def tearDown(self):
        TsumikiConfig._instance = None

    def _make_config(self, parsed_data=None):
        if parsed_data is None:
            parsed_data = dict(_DEFAULT_PARSED)
        with (
            mock.patch(
                "utils.config.get_relative_path",
                return_value="/tmp",
            ),
            mock.patch(
                "utils.config.os.path.exists",
                return_value=True,
            ),
            mock.patch(
                "utils.config.read_toml_file",
                return_value=parsed_data,
            ),
            mock.patch("utils.config.validate_config_enums"),
            mock.patch("utils.config.validate_widgets"),
        ):
            return TsumikiConfig()

    def test_missing_toml_raises(self):
        with (
            mock.patch(
                "utils.config.get_relative_path",
                return_value="/tmp",
            ),
            mock.patch(
                "utils.config.os.path.exists",
                return_value=False,
            ),
            self.assertRaises(FileNotFoundError),
        ):
            TsumikiConfig()

    def test_valid_toml_merges_with_defaults(self):
        parsed = {
            "general": {"debug": False},
            "widgets": {},
            "layout": {},
            "modules": {},
            "styling": {},
        }
        cfg = self._make_config(parsed_data=parsed)
        self.assertFalse(cfg.config["general"]["debug"])
        self.assertIn("widgets", cfg.config)
        self.assertIn("layout", cfg.config)

    def test_list_keys_not_deep_merged(self):
        parsed = {
            "widget_groups": [{"widgets": ["battery"]}],
            "general": {},
            "widgets": {},
            "layout": {},
            "modules": {},
            "styling": {},
        }
        cfg = self._make_config(parsed_data=parsed)
        groups = cfg.config["widget_groups"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["widgets"], ["battery"])

    def test_invalid_config_exits(self):
        with (
            mock.patch(
                "utils.config.get_relative_path",
                return_value="/tmp",
            ),
            mock.patch(
                "utils.config.os.path.exists",
                return_value=True,
            ),
            mock.patch(
                "utils.config.read_toml_file",
                return_value={},
            ),
            mock.patch(
                "utils.config.validate_config_enums",
                side_effect=ValueError("bad config"),
            ),
            mock.patch("utils.config.validate_widgets"),
            self.assertRaises(SystemExit),
        ):
            TsumikiConfig()

    def test_none_toml_uses_defaults(self):
        with (
            mock.patch(
                "utils.config.get_relative_path",
                return_value="/tmp",
            ),
            mock.patch(
                "utils.config.os.path.exists",
                return_value=True,
            ),
            mock.patch(
                "utils.config.read_toml_file",
                return_value=None,
            ),
            mock.patch("utils.config.validate_config_enums"),
            mock.patch("utils.config.validate_widgets"),
        ):
            cfg = TsumikiConfig()
        self.assertIn("general", cfg.config)


class ConfigImportIsolationTest(unittest.TestCase):
    """Importing the shared widget layer must not parse config.toml.

    Runs in a subprocess because this test process has already imported
    utils.config through other modules.
    """

    def test_widget_layer_import_does_not_load_config(self):
        project_root = Path(__file__).resolve().parents[1]
        code = (
            "import sys\n"
            "import shared.widget_container\n"
            "print('utils.config' in sys.modules)\n"
        )

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=project_root,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "False")


if __name__ == "__main__":
    unittest.main()
