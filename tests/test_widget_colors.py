import unittest

from utils.widget_colors import (
    build_widget_colors_css,
    is_color_literal,
    is_theme_token,
    merge_widget_colors,
    normalize_color_value,
    resolve_color_value,
)


class WidgetColorDetectionTest(unittest.TestCase):
    """Tests for token/literal detection and normalization."""

    def test_color_literals_accepted(self):
        for value in (
            "#fff",
            "#1e66f5",
            "#1e66f580",
            "rgb(0,0,0)",
            "rgba(0,0,0,0.5)",
            "hsl(0,0%,0%)",
        ):
            with self.subTest(value=value):
                self.assertTrue(is_color_literal(value))
                self.assertEqual(normalize_color_value(value), value)

    def test_theme_tokens_accepted(self):
        for value in ("accent-blue", "text-main", "background-dark"):
            with self.subTest(value=value):
                self.assertTrue(is_theme_token(value))
                self.assertEqual(normalize_color_value(value), value)

    def test_theme_token_validation_against_set(self):
        theme_tokens = {"accent-blue", "text-main"}
        self.assertTrue(is_theme_token("accent-blue", theme_tokens))
        self.assertFalse(is_theme_token("unknown-token", theme_tokens))
        self.assertEqual(
            normalize_color_value("accent-blue", theme_tokens), "accent-blue"
        )
        self.assertIsNone(normalize_color_value("unknown-token", theme_tokens))

    def test_invalid_and_empty_values_rejected(self):
        garbage = [
            "",
            "   ",
            None,
            "#12",
            "#12345",
            "rgb()",
            "rgba(0,0,0)",
            "hsl(0,0,0)",
            "Accent-Blue",
            "accent blue",
            "has.dot",
            123,
            {},
            [],
        ]
        for value in garbage:
            with self.subTest(value=value):
                self.assertIsNone(normalize_color_value(value))
                self.assertIsNone(normalize_color_value(value, {"accent-blue"}))

    def test_unknown_token_rejected_when_set_provided(self):
        self.assertIsNone(normalize_color_value("not-a-color", {"accent-blue"}))
        self.assertIsNone(
            resolve_color_value("not-a-color", {"accent-blue": "#89b4fa"})
        )

    def test_normalize_never_raises(self):
        for value in (object(), float("nan"), b"#fff"):
            with self.subTest(value=value):
                self.assertIsNone(normalize_color_value(value))


class WidgetColorResolutionTest(unittest.TestCase):
    """Tests for resolving color values at runtime."""

    def test_resolve_token_from_theme_map(self):
        self.assertEqual(
            resolve_color_value("accent-blue", {"accent-blue": "#89b4fa"}),
            "#89b4fa",
        )

    def test_resolve_literal_passthrough(self):
        self.assertEqual(resolve_color_value("#fff", {}), "#fff")
        self.assertEqual(
            resolve_color_value("rgb(0,0,0)", {"x": "#000"}), "rgb(0,0,0)"
        )

    def test_resolve_unknown_or_missing_returns_none(self):
        self.assertIsNone(
            resolve_color_value("missing", {"accent-blue": "#89b4fa"})
        )
        self.assertIsNone(resolve_color_value("missing", {}))
        self.assertIsNone(resolve_color_value("", {"accent-blue": "#89b4fa"}))
        self.assertIsNone(resolve_color_value(None, {"accent-blue": "#89b4fa"}))
        self.assertIsNone(resolve_color_value("not-a-color", {}))


class WidgetColorMergeTest(unittest.TestCase):
    """Tests for per-field/per-state color config merging."""

    def test_instance_wins_and_inherits_per_field_state(self):
        type_colors = {
            "background": "#111",
            "foreground": "#eee",
            "hover": {"background": "#222", "foreground": "#ddd"},
            "active": {"background": "#333"},
        }
        instance_colors = {
            "foreground": "#fff",
            "hover": {"background": "#abc"},
        }
        merged = merge_widget_colors(type_colors, instance_colors)
        self.assertEqual(merged["background"], "#111")
        self.assertEqual(merged["foreground"], "#fff")
        self.assertEqual(merged["hover"]["background"], "#abc")
        self.assertEqual(merged["hover"]["foreground"], "#ddd")
        self.assertEqual(merged["active"], {"background": "#333"})

    def test_empty_none_and_empty_strings_omitted(self):
        self.assertEqual(merge_widget_colors(None, None), {})
        self.assertEqual(merge_widget_colors({}, {}), {})
        merged = merge_widget_colors(
            {"background": "", "foreground": None, "hover": {"background": ""}},
            {"active": {}},
        )
        self.assertEqual(merged, {})

    def test_invalid_instance_root_field_falls_back_to_type(self):
        merged = merge_widget_colors(
            {"foreground": "#eee", "background": "#111"},
            {"foreground": "not a color", "background": "###"},
        )
        self.assertEqual(merged["foreground"], "#eee")
        self.assertEqual(merged["background"], "#111")

    def test_invalid_instance_state_fields_fall_back_to_type(self):
        type_colors = {
            "hover": {"background": "#222", "foreground": "#ddd"},
            "active": {"background": "#333", "foreground": "#ccc"},
        }
        instance_colors = {
            "hover": {"background": "###", "foreground": "Accent-Blue"},
            "active": {"background": "has.dot", "foreground": "not a color"},
        }
        merged = merge_widget_colors(type_colors, instance_colors)
        self.assertEqual(
            merged["hover"], {"background": "#222", "foreground": "#ddd"}
        )
        self.assertEqual(
            merged["active"], {"background": "#333", "foreground": "#ccc"}
        )


class WidgetColorCssTest(unittest.TestCase):
    """Tests for scoped CSS generation."""

    def test_build_css_base_and_hover_no_active(self):
        css = build_widget_colors_css(
            "#battery",
            {
                "background": "#111",
                "foreground": "#eee",
                "hover": {"background": "#222"},
            },
            as_theme_refs=False,
            theme_map={},
        )
        self.assertIn("#battery", css)
        self.assertIn("background-color: #111", css)
        self.assertIn("color: #eee", css)
        self.assertIn("#battery:hover", css)
        self.assertIn("background-color: #222", css)
        self.assertNotIn(".active", css)

    def test_build_css_emits_theme_refs(self):
        css = build_widget_colors_css(
            "#cpu",
            {"background": "accent-blue"},
            as_theme_refs=True,
            theme_map={},
        )
        self.assertIn("theme.$accent-blue", css)

    def test_build_css_resolves_tokens_and_skips_invalid(self):
        css = build_widget_colors_css(
            "#cpu",
            {"background": "accent-blue", "foreground": "missing"},
            as_theme_refs=False,
            theme_map={"accent-blue": "#89b4fa"},
        )
        self.assertIn("#89b4fa", css)
        self.assertNotIn("missing", css)
        self.assertNotIn(
            "color:",
            css.split("background-color")[0] if "background-color" in css else "",
        )

    def test_build_css_empty_returns_empty_string(self):
        self.assertEqual(
            build_widget_colors_css("#x", {}, as_theme_refs=False, theme_map={}),
            "",
        )
        self.assertEqual(
            build_widget_colors_css(
                "#x",
                {"background": "missing"},
                as_theme_refs=False,
                theme_map={},
            ),
            "",
        )


if __name__ == "__main__":
    unittest.main()
