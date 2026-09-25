"""Tests for the settings GUI's section builder.

One generic builder now produces the five section shapes. What matters is that
each caller still gets its own presentation and, above all, that every control
is handed the config path its value actually lives at - a wrong path does not
crash, it silently writes to the wrong key and saves it.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import settings_gui as settings_module
from modules.settings_gui import SettingsGUI


def make_gui() -> SettingsGUI:
    """A SettingsGUI with the widget factories stubbed, so no GTK is built."""
    gui = SettingsGUI.__new__(SettingsGUI)
    gui.config = {}
    gui.theme = {}
    gui._created_expanders = []

    def new_expander(label):
        expander = mock.Mock(_label=label)
        gui._created_expanders.append(expander)
        return expander

    gui._create_expander = mock.Mock(side_effect=new_expander)
    gui._create_section_header = mock.Mock(
        side_effect=lambda label: mock.Mock(_label=label)
    )
    gui._create_grid = mock.Mock(
        side_effect=lambda margin_bottom=0: mock.Mock(_margin_bottom=margin_bottom)
    )
    gui._create_label = mock.Mock(side_effect=lambda key: mock.Mock(_key=key))
    return gui


class BuildSectionTest(unittest.TestCase):
    """Presentation flags drive the shape; the control factory is passed in."""

    def setUp(self):
        patcher = mock.patch.object(settings_module, "Box")
        self.addCleanup(patcher.stop)
        self.box = patcher.start()
        self.gui = make_gui()
        self.container = mock.Mock()
        self.controls = []

    def control(self, path, key, value):
        self.controls.append((path, key, value))
        return mock.Mock()

    def drop_nested(self, *_):
        """Stand-in for the nested builder; these cases carry no dict values."""

    def test_a_plain_section_gets_a_header_and_a_body(self):
        self.gui._build_section(
            self.container,
            "dock",
            {"a": 1},
            "config.modules",
            control=self.control,
            nested=self.drop_nested,
        )

        self.gui._create_section_header.assert_called_once_with("Dock")
        self.assertFalse(self.gui._create_expander.called)
        # header and box are siblings on the container
        self.assertEqual(2, self.container.add.call_count)

    def test_an_expander_owns_its_body(self):
        self.gui._build_section(
            self.container,
            "dock",
            {"a": 1},
            "config.modules",
            control=self.control,
            nested=self.drop_nested,
            expander=True,
        )

        disclosure = self.gui._created_expanders[0]
        disclosure.add.assert_called_once()
        self.container.add.assert_called_once_with(disclosure)

    def test_indent_is_independent_of_the_header_style(self):
        """The theme module section is a plain header that still indents."""
        self.gui._build_section(
            self.container,
            "dock",
            {"a": 1},
            "theme.modules",
            control=self.control,
            nested=self.drop_nested,
            indent=True,
        )

        style = self.box.call_args.kwargs["style"]
        self.assertEqual("margin-left: 20px;", style)

    def test_no_indent_leaves_the_style_unset(self):
        self.gui._build_section(
            self.container,
            "bar",
            {"a": 1},
            "theme",
            control=self.control,
            nested=self.drop_nested,
        )

        self.assertIsNone(self.box.call_args.kwargs["style"])

    def test_the_underscored_name_is_titled_for_display_only(self):
        self.gui._build_section(
            self.container,
            "my_thing",
            {"a": 1},
            "config.modules",
            control=self.control,
            nested=self.drop_nested,
        )

        self.gui._create_section_header.assert_called_once_with("My Thing")
        # the path keeps the raw name
        self.assertEqual("config.modules.my_thing", self.controls[0][0])

    def test_list_values_are_skipped(self):
        self.gui._build_section(
            self.container,
            "dock",
            {"a": 1, "items": ["x", "y"], "b": 2},
            "config.modules",
            control=self.control,
            nested=self.drop_nested,
        )

        self.assertEqual(["a", "b"], [key for _, key, _ in self.controls])

    def test_nested_dicts_go_to_the_nested_builder_with_this_sections_path(self):
        seen = []

        def nested(container, name, items, path):
            seen.append((name, path))

        self.gui._build_section(
            self.container,
            "dock",
            {"colors": {"bg": "#fff"}, "a": 1},
            "config.modules",
            control=self.control,
            nested=nested,
        )

        self.assertEqual([("colors", "config.modules.dock")], seen)

    def test_the_grid_gap_is_passed_through(self):
        self.gui._build_section(
            self.container,
            "dock",
            {"a": 1},
            "config.modules",
            control=self.control,
            nested=self.drop_nested,
            margin_bottom=15,
        )

        self.gui._create_grid.assert_called_once_with(margin_bottom=15)


class ControlPathTests(unittest.TestCase):
    """Every leaf must be handed the path its value really lives at.

    A wrong path does not raise: _update_nested_dict creates whatever segments
    are missing, so the old duplicated-segment path wrote a value to an invented
    key like ``config.modules.dock.deep.deep`` and saved it to config.toml.
    """

    def setUp(self):
        patcher = mock.patch.object(settings_module, "Box")
        self.addCleanup(patcher.stop)
        patcher.start()
        self.gui = make_gui()
        self.container = mock.Mock()
        self.controls = []

    def control(self, path, key, value):
        self.controls.append((path, key))
        return mock.Mock()

    def paths_from(self, build, *args):
        with mock.patch.object(SettingsGUI, "_create_control", self.control):
            build(*args)
        return self.controls

    def drop_nested(self, *_):
        """Stand-in for the nested builder; these cases carry no dict values."""

    def test_two_levels_of_nesting_keep_the_full_path(self):
        paths = self.paths_from(
            self.gui._create_nested_section,
            self.container,
            "colors",
            {"bg": "#fff", "fg": "#000"},
            "config.modules.dock",
        )

        self.assertEqual(
            [
                ("config.modules.dock.colors", "bg"),
                ("config.modules.dock.colors", "fg"),
            ],
            paths,
        )

    def test_three_levels_of_nesting_are_not_duplicated(self):
        """The regression: the recursion used to append the key twice."""
        paths = self.paths_from(
            self.gui._create_nested_section,
            self.container,
            "colors",
            {"deep": {"x": 1}},
            "config.modules.dock",
        )

        self.assertEqual([("config.modules.dock.colors.deep", "x")], paths)

    def test_a_child_group_nests_under_its_parent(self):
        paths = self.paths_from(
            self.gui._create_nested_section,
            self.container,
            "colors",
            {"bg": "#fff", "border": {"radius": 8}},
            "config.modules.dock",
        )

        self.assertEqual(
            [
                ("config.modules.dock.colors", "bg"),
                ("config.modules.dock.colors.border", "radius"),
            ],
            paths,
        )

    def test_two_sibling_groups_each_keep_their_own_name(self):
        with mock.patch.object(SettingsGUI, "_create_control", self.control):
            self.gui._create_config_section(
                self.container,
                "dock",
                {"colors": {"bg": "#fff"}, "border": {"radius": 8}},
                "config.modules",
            )

        self.assertEqual(
            [
                ("config.modules.dock.colors", "bg"),
                ("config.modules.dock.border", "radius"),
            ],
            self.controls,
        )

    def test_four_levels_stay_correct(self):
        paths = self.paths_from(
            self.gui._create_nested_section,
            self.container,
            "a",
            {"b": {"c": {"d": {"e": 1}}}},
            "config.modules",
        )

        self.assertEqual([("config.modules.a.b.c.d", "e")], paths)

    def test_the_config_section_prefixes_its_own_name(self):
        with mock.patch.object(SettingsGUI, "_create_control", self.control):
            self.gui._create_config_section(
                self.container,
                "dock",
                {"a": 1, "sub": {"b": 2}},
                "config.modules",
            )

        self.assertEqual(
            [
                ("config.modules.dock", "a"),
                ("config.modules.dock.sub", "b"),
            ],
            self.controls,
        )

    def test_theme_nested_sections_keep_their_path(self):
        with mock.patch.object(SettingsGUI, "_create_theme_control", self.control):
            self.gui._create_theme_nested_section(
                self.container, "border", {"radius": 8, "sub": {"w": 1}}, "theme.bar"
            )

        self.assertEqual(
            [("theme.bar.border", "radius"), ("theme.bar.border.sub", "w")],
            self.controls,
        )

    def test_theme_module_sections_keep_their_path(self):
        with mock.patch.object(SettingsGUI, "_create_theme_control", self.control):
            self.gui._create_theme_module_section(
                self.container, "dock", {"a": 1}, "theme.modules"
            )

        self.assertEqual([("theme.modules.dock", "a")], self.controls)

    def test_the_modules_theme_section_dispatches_to_the_module_builder(self):
        with (
            mock.patch.object(SettingsGUI, "_create_theme_control", self.control),
            mock.patch.object(self.gui, "_create_theme_module_section") as module_sec,
            mock.patch.object(self.gui, "_create_theme_nested_section") as nested_sec,
        ):
            self.gui._create_theme_section(
                self.container, "modules", {"dock": {"a": 1}}, "theme"
            )

        module_sec.assert_called_once()
        nested_sec.assert_not_called()
        self.assertEqual("theme.modules", module_sec.call_args.args[3])
        self.assertEqual("dock", module_sec.call_args.args[1])

    def test_other_theme_sections_dispatch_to_the_nested_builder(self):
        with (
            mock.patch.object(SettingsGUI, "_create_theme_control", self.control),
            mock.patch.object(self.gui, "_create_theme_module_section") as module_sec,
            mock.patch.object(self.gui, "_create_theme_nested_section") as nested_sec,
        ):
            self.gui._create_theme_section(
                self.container, "bar", {"border": {"radius": 8}}, "theme"
            )

        nested_sec.assert_called_once()
        module_sec.assert_not_called()
        # the child is handed its parent's path and appends its own name
        self.assertEqual("theme.bar", nested_sec.call_args.args[3])
        self.assertEqual("border", nested_sec.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
