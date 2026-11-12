"""Tests for theme palette parsing and widget color settings emission."""

import os
import tempfile
import unittest
from unittest.mock import patch

from services.style import StyleService
from utils.widget_colors import format_settings_color_value, parse_scss_theme_variables


class ParseScssThemeVariablesTest(unittest.TestCase):
    """Tests for parsing $name: value assignments from theme SCSS."""

    def test_parses_variable_assignments(self):
        text = "$accent-blue: #89b4fa;\n$background: #1e1e2e;\n"
        self.assertEqual(
            parse_scss_theme_variables(text),
            {"accent-blue": "#89b4fa", "background": "#1e1e2e"},
        )

    def test_ignores_invalid_lines(self):
        text = "// comment\n$ok: #fff;\nnot-a-var: 1;\n$bad value;\n"
        self.assertEqual(parse_scss_theme_variables(text), {"ok": "#fff"})


class FormatSettingsColorValueTest(unittest.TestCase):
    """Tests for formatting color values for settings SCSS emission."""

    def test_formats_theme_token_as_scss_ref(self):
        self.assertEqual(
            format_settings_color_value("accent-blue"),
            "theme.$accent-blue",
        )

    def test_formats_literal_color_as_is(self):
        self.assertEqual(format_settings_color_value("#fff"), "#fff")

    def test_invalid_value_returns_none(self):
        self.assertIsNone(format_settings_color_value("not a color"))


class StyleServiceThemeMapAndSettingsTest(unittest.TestCase):
    """Tests for theme map access and widget color settings emission."""
    def _make_service(self) -> StyleService:
        service = StyleService.__new__(StyleService)
        service._styles_dir = tempfile.mkdtemp()
        service._theme_contents = {"accent-blue": "#89b4fa", "foreground": "#cdd6f4"}
        service._config = {
            "styling": {
                "mode": "dark",
                "bar": {
                    "widgets": {
                        "clock": {
                            "colors": {
                                "foreground": "accent-blue",
                                "background": "#111111",
                                "hover": {"foreground": "foreground"},
                            }
                        }
                    }
                },
            }
        }
        return service

    def test_get_theme_color_map_from_theme_contents(self):
        service = self._make_service()
        self.assertEqual(
            service.get_theme_color_map(),
            {"accent-blue": "#89b4fa", "foreground": "#cdd6f4"},
        )

    def test_get_theme_color_map_from_theme_scss_when_matugen(self):
        service = self._make_service()
        service._theme_contents = None
        theme_path = os.path.join(service._styles_dir, "_theme.scss")
        with open(theme_path, "w", encoding="utf-8") as f:
            f.write("$accent-blue: #89b4fa;\n$surface: #313244;\n")
        self.assertEqual(
            service.get_theme_color_map(),
            {"accent-blue": "#89b4fa", "surface": "#313244"},
        )

    def test_write_settings_css_emits_theme_refs_for_color_tokens(self):
        service = self._make_service()
        service.write_settings_css()
        settings_path = os.path.join(service._styles_dir, "_settings.scss")
        with open(settings_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn('@use "theme";', content)
        self.assertIn(
            "$bar-widgets-clock-colors-foreground: theme.$accent-blue;",
            content,
        )
        self.assertIn("$bar-widgets-clock-colors-background: #111111;", content)
        self.assertIn(
            "$bar-widgets-clock-colors-hover-foreground: theme.$foreground;",
            content,
        )
        # non-color string unchanged
        self.assertIn("$mode: dark;", content)

    def test_write_settings_css_ignores_invalid_color_values_with_warning(self):
        service = self._make_service()
        service._theme_contents = {"accent-blue": "#89b4fa"}
        service._config["styling"]["bar"]["widgets"]["clock"]["colors"].update(
            {
                "background": "not a color",
                "active": {"foreground": "missing-token"},
            }
        )
        with patch("services.style.logger.warning") as warn:
            service.write_settings_css()
        settings_path = os.path.join(service._styles_dir, "_settings.scss")
        with open(settings_path, encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("not a color", content)
        self.assertNotIn("missing-token", content)
        self.assertTrue(warn.called)
        logs = " ".join(str(call.args[0]) for call in warn.call_args_list)
        self.assertIn("clock", logs)
        self.assertIn("not a color", logs)


if __name__ == "__main__":
    unittest.main()
