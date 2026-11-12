import unittest
from unittest.mock import patch

from utils.widget_colors import (
    get_widget_instance_selector,
    resolve_color_value,
    resolve_widget_instance_colors,
)


class WidgetInstanceColorLookupTest(unittest.TestCase):
    """Tests for per-instance override lookup and merged effective colors."""

    def test_type_only_no_override_returns_empty(self):
        styling = {
            "bar": {
                "widgets": {
                    "battery": {"colors": {"background": "#111", "foreground": "#eee"}},
                }
            }
        }
        merged = resolve_widget_instance_colors("battery", "bat-1", styling)
        self.assertEqual(merged, {})

    def test_instance_id_match_merges_per_field(self):
        styling = {
            "bar": {
                "widgets": {
                    "custom_widget": {
                        "colors": {
                            "background": "#111",
                            "foreground": "#eee",
                            "hover": {"background": "#222", "foreground": "#ddd"},
                        },
                        "overrides": {
                            "volume": {
                                "colors": {
                                    "foreground": "#fff",
                                    "hover": {"background": "accent-blue"},
                                }
                            }
                        },
                    }
                }
            }
        }
        merged = resolve_widget_instance_colors("custom_widget", "volume", styling)
        self.assertEqual(merged["background"], "#111")
        self.assertEqual(merged["foreground"], "#fff")
        self.assertEqual(merged["hover"]["background"], "accent-blue")
        self.assertEqual(merged["hover"]["foreground"], "#ddd")

    def test_unknown_instance_id_returns_no_override(self):
        styling = {
            "bar": {
                "widgets": {
                    "cpu": {
                        "overrides": {"cpu-a": {"colors": {"background": "#123"}}}
                    }
                }
            }
        }
        self.assertEqual(resolve_widget_instance_colors("cpu", "cpu-b", styling), {})

    def test_token_values_preserved_for_runtime_resolution(self):
        styling = {
            "bar": {
                "widgets": {
                    "memory": {
                        "colors": {"background": "surface"},
                        "overrides": {
                            "main": {
                                "colors": {
                                    "foreground": "accent-blue",
                                    "hover": {"background": "surface-bright"},
                                }
                            }
                        },
                    }
                }
            }
        }
        merged = resolve_widget_instance_colors("memory", "main", styling)
        self.assertEqual(merged["background"], "surface")
        self.assertEqual(merged["foreground"], "accent-blue")
        self.assertEqual(merged["hover"]["background"], "surface-bright")

    def test_invalid_instance_override_warns_and_is_ignored(self):
        styling = {
            "bar": {
                "widgets": {
                    "custom_widget": {
                        "colors": {"foreground": "#eee"},
                        "overrides": {
                            "vol": {
                                "colors": {
                                    "background": "not a color",
                                    "hover": {"foreground": "###"},
                                }
                            }
                        },
                    }
                }
            }
        }
        with patch("utils.widget_colors.logger.warning") as warn:
            merged = resolve_widget_instance_colors(
                "custom_widget", "vol", styling, warn=True
            )
        self.assertEqual(merged, {"foreground": "#eee"})
        self.assertTrue(warn.called)
        messages = " ".join(str(call.args[0]) for call in warn.call_args_list)
        self.assertIn("custom_widget", messages)
        self.assertIn("vol", messages)
        self.assertIn("not a color", messages)

    def test_unknown_token_runtime_resolution_warns_with_context(self):
        with patch("utils.widget_colors.logger.warning") as warn:
            self.assertIsNone(
                resolve_color_value(
                    "missing-token",
                    {"accent": "#fff"},
                    warn_context={
                        "widget_type": "cpu",
                        "instance_id": "main",
                        "state": "hover",
                        "field": "background",
                    },
                )
            )
        self.assertTrue(warn.called)
        messages = " ".join(str(call.args[0]) for call in warn.call_args_list)
        self.assertIn("missing-token", messages)
        self.assertIn("cpu", messages)
        self.assertIn("main", messages)
        self.assertIn("hover", messages)
        self.assertIn("background", messages)


class WidgetInstanceSelectorTest(unittest.TestCase):
    """Tests for stable selector targeting for instance overrides."""

    def test_selector_targets_specific_instance(self):
        self.assertEqual(
            get_widget_instance_selector("custom_widget", "volume"),
            "#custom_widget.instance-volume",
        )

    def test_selector_uses_widget_name_when_provided(self):
        self.assertEqual(
            get_widget_instance_selector(
                "custom_widget", "volume", widget_name="custom_widget-volume"
            ),
            "#custom_widget-volume",
        )


if __name__ == "__main__":
    unittest.main()
