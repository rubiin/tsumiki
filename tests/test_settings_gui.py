"""Tests for saving, resetting and the value ranges of the settings GUI.

Three ways this window used to eat a user's configuration: the save handler
referenced a ``theme_config_file`` that does not exist (so it reported a failure
after the real write had landed, and never reset the Save button), reset
aliased its sub-tables onto the live global config, and every int field was
given a fixed 0..100 adjustment, which clamps the value in the config on the
next save.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import settings_gui as settings_module
from modules.settings_gui import SettingsGUI


def make_gui() -> SettingsGUI:
    """A SettingsGUI with only the attributes these tests drive, no GTK window."""
    gui = SettingsGUI.__new__(SettingsGUI)
    gui.config = {}
    gui.theme = {}
    gui.modified = False
    gui.save_btn = mock.Mock()
    gui._refresh_tabs = mock.Mock()
    return gui


class SaveTest(unittest.TestCase):
    """One write, one success notification, and a Save button that disarms."""

    def setUp(self):
        self.gui = make_gui()
        self.gui.config = {"styling": {"font": {"weight": 400}}}
        self.gui.theme = self.gui.config["styling"]
        self.gui.modified = True

        patches = [
            mock.patch.object(settings_module, "configuration"),
            mock.patch.object(settings_module, "write_toml_file"),
            mock.patch.object(settings_module, "send_notification"),
        ]
        for patcher in patches:
            self.addCleanup(patcher.stop)
        self.configuration, self.write, self.notify = (p.start() for p in patches)
        self.configuration.toml_config_file = "/tmp/config.toml"

    def test_saving_writes_the_config_once_and_succeeds(self):
        """The regression: the bogus second write raised, so the user was told
        the save failed even though it worked, and the button stayed armed."""
        self.gui._on_save()

        self.write.assert_called_once_with("/tmp/config.toml", self.gui.config)
        self.assertEqual(
            [mock.call("Tsumiki", "Configuration saved")], self.notify.call_args_list
        )

    def test_saving_clears_the_modified_flag(self):
        self.gui._on_save()

        self.assertFalse(self.gui.modified)
        self.gui.save_btn.set_sensitive.assert_called_with(False)

    def test_theme_edits_are_part_of_the_single_write(self):
        """self.theme is a reference into self.config, so the one write covers it."""
        self.gui.theme["font"]["weight"] = 700

        self.gui._on_save()

        written = self.write.call_args.args[1]
        self.assertEqual(700, written["styling"]["font"]["weight"])


class ResetTest(unittest.TestCase):
    """Reset must leave the live global config alone."""

    def test_reset_does_not_alias_the_global_config(self):
        """The regression: dict() is shallow, so later edits wrote straight into
        tsumiki_config with no file write and no watcher notification."""
        live = {"modules": {"dock": {"autohide": True}}, "styling": {"blur": 10}}
        with mock.patch.object(settings_module, "tsumiki_config", live):
            gui = make_gui()
            gui._on_reset()

            gui.config["modules"]["dock"]["autohide"] = False
            gui.config["styling"]["blur"] = 40

        self.assertTrue(live["modules"]["dock"]["autohide"])
        self.assertEqual(10, live["styling"]["blur"])

    def test_reset_repoints_the_theme_at_the_fresh_config(self):
        live = {"modules": {}, "styling": {"blur": 10}}
        with mock.patch.object(settings_module, "tsumiki_config", live):
            gui = make_gui()
            gui._on_reset()

        self.assertIs(gui.theme, gui.config["styling"])
        self.assertIsNot(gui.config, live)

    def test_reset_clears_the_modified_flag(self):
        with mock.patch.object(settings_module, "tsumiki_config", {}):
            gui = make_gui()
            gui.modified = True
            gui._on_reset()

        self.assertFalse(gui.modified)
        gui.save_btn.set_sensitive.assert_called_with(False)
        gui._refresh_tabs.assert_called_once()


class IntRangeTest(unittest.TestCase):
    """A spin button must never clamp the value the config already holds."""

    def setUp(self):
        self.gui = make_gui()

    def spin_for(self, value, path="config.modules.notification.timeout", key="x"):
        return self.gui._create_control(path, key, value)

    def test_a_long_timeout_gets_a_range_that_holds_it(self):
        spin = self.spin_for(15000, key="critical")

        self.assertGreaterEqual(spin.get_adjustment().get_upper(), 15000)
        self.assertEqual(15000, spin.get_value())

    def test_a_short_value_keeps_the_normal_range(self):
        spin = self.spin_for(5)

        self.assertEqual(100, spin.get_adjustment().get_upper())
        self.assertEqual(5, spin.get_value())

    def test_the_theme_font_weight_survives_its_wider_range(self):
        spin = self.gui._create_theme_control("theme.font", "weight", 600)

        self.assertGreaterEqual(spin.get_adjustment().get_upper(), 600)
        self.assertEqual(600, spin.get_value())

    def test_a_theme_value_above_the_default_bound_widens_the_range(self):
        spin = self.gui._create_theme_control("theme.font", "size", 200000)

        self.assertGreaterEqual(spin.get_adjustment().get_upper(), 200000)
        self.assertEqual(200000, spin.get_value())


if __name__ == "__main__":
    unittest.main()
