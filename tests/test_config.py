"""Tests for utils/config.py — configuration loading and merging."""

import subprocess
import sys
import unittest
from pathlib import Path

from tests.helpers import make_tsumiki_config
from utils.config import (
    _EXCLUDED_SCHEMA_KEYS,
    TsumikiConfig,
)
from utils.constants import DEFAULT_CONFIG


class ExcludedKeysTest(unittest.TestCase):
    """Verify the frozen config constants for schema merging."""

    def test_schema_key_excluded(self):
        self.assertIn("$schema", _EXCLUDED_SCHEMA_KEYS)

    def test_group_keys_have_no_defaults(self):
        # The schema puts both at the top level, so a default under ``widgets``
        # would be unreachable; neither is defaulted.
        self.assertNotIn("widget_groups", DEFAULT_CONFIG)
        self.assertNotIn("collapsible_groups", DEFAULT_CONFIG)
        self.assertNotIn("widget_groups", DEFAULT_CONFIG["widgets"])
        self.assertNotIn("collapsible_groups", DEFAULT_CONFIG["widgets"])


class TsumikiConfigSingletonTest(unittest.TestCase):
    """Test singleton behaviour of TsumikiConfig."""

    def setUp(self):
        TsumikiConfig.reset_instance()

    def tearDown(self):
        TsumikiConfig.reset_instance()

    def test_same_instance(self):
        a = make_tsumiki_config()
        b = TsumikiConfig()
        self.assertIs(a, b)

    def test_loaded_only_once(self):
        a = make_tsumiki_config()
        b = TsumikiConfig()
        self.assertIs(a, b)


class LoadConfigTest(unittest.TestCase):
    """Test _load_config with mocked file I/O."""

    def setUp(self):
        TsumikiConfig.reset_instance()

    def tearDown(self):
        TsumikiConfig.reset_instance()

    def test_missing_toml_raises(self):
        with self.assertRaises(FileNotFoundError):
            make_tsumiki_config(exists=False)

    def test_valid_toml_merges_with_defaults(self):
        parsed = {
            "general": {"debug": False},
            "widgets": {},
            "layout": {},
            "modules": {},
            "styling": {},
        }
        cfg = make_tsumiki_config(parsed_data=parsed)
        self.assertFalse(cfg.config["general"]["debug"])
        self.assertIn("widgets", cfg.config)
        self.assertIn("layout", cfg.config)

    def test_user_group_list_survives_the_merge(self):
        parsed = {
            "widget_groups": [{"widgets": ["battery"]}],
            "general": {},
            "widgets": {},
            "layout": {},
            "modules": {},
            "styling": {},
        }
        cfg = make_tsumiki_config(parsed_data=parsed)
        groups = cfg.config["widget_groups"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["widgets"], ["battery"])

    def test_invalid_config_exits(self):
        with self.assertRaises(SystemExit):
            make_tsumiki_config(parsed_data={}, enums_error=ValueError("bad config"))

    def test_none_toml_uses_defaults(self):
        cfg = make_tsumiki_config(parsed_data=None)
        self.assertIn("general", cfg.config)


class DefaultsNotAliasedTest(unittest.TestCase):
    """The live config must not share mutable leaves with ``DEFAULT_CONFIG``.

    A widget doing ``config["widgets"]["mpris"]["ignore"].sort()`` would rewrite
    the module-level defaults, silently, for every later reader.
    """

    def setUp(self):
        TsumikiConfig.reset_instance()
        self._ignore = DEFAULT_CONFIG["widgets"]["mpris"]["ignore"]
        self.addCleanup(self._restore_defaults)

    def _restore_defaults(self):
        DEFAULT_CONFIG["widgets"]["mpris"]["ignore"] = self._ignore

    def _config_without_overrides(self):
        return make_tsumiki_config(
            parsed_data={
                "general": {},
                "widgets": {},
                "layout": {},
                "modules": {},
                "styling": {},
            }
        ).config

    def test_inherited_lists_are_copies(self):
        ignore = self._config_without_overrides()["widgets"]["mpris"]["ignore"]

        self.assertIsNot(ignore, self._ignore)
        self.assertEqual(ignore, self._ignore)

    def test_mutating_the_live_config_leaves_the_defaults_alone(self):
        ignore = self._config_without_overrides()["widgets"]["mpris"]["ignore"]
        before = len(self._ignore)

        ignore.append("injected")

        self.assertEqual(len(self._ignore), before)


class ConfigImportIsolationTest(unittest.TestCase):
    """Importing the shared widget layer must not parse config.toml."""

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
