"""Tests for ``utils/icons.py`` — the nested nerd-font icon lookup."""

import unittest

from utils.icons import get_path, get_text_icon, text_nerd_icons


class GetTextIconTest(unittest.TestCase):
    """An icon name is a dotted path into the icon tree; a miss is not a crash."""

    def test_resolves_a_nested_icon(self):
        self.assertEqual(
            get_text_icon("wifi.strength_4"), text_nerd_icons["wifi"]["strength_4"]
        )

    def test_resolves_a_top_level_icon(self):
        self.assertTrue(get_text_icon("battery"))

    def test_unknown_leaf_falls_back(self):
        self.assertEqual(get_text_icon("nope", "FB"), "FB")

    def test_past_a_leaf_falls_back(self):
        # An icon name with one segment too many must not raise.
        self.assertEqual(get_text_icon("distro.arch.x", "FB"), "FB")
        self.assertEqual(get_text_icon("battery.charging.extra"), "")

    def test_missing_fallback_is_empty(self):
        self.assertEqual(get_text_icon("distro.arch.x"), "")


class GetPathTest(unittest.TestCase):
    """``get_path`` walks dicts only; anything else ends the walk."""

    def test_walks_to_a_leaf(self):
        self.assertEqual(get_path({"a": {"b": "c"}}, "a.b"), "c")

    def test_stops_at_a_non_dict(self):
        self.assertEqual(get_path({"a": "c"}, "a.b", fallback="FB"), "FB")

    def test_unknown_key_uses_the_fallback(self):
        self.assertEqual(get_path({"a": {}}, "a.b.c", fallback="FB"), "FB")

    def test_falsy_leaf_uses_the_fallback(self):
        self.assertEqual(get_path({"a": ""}, "a", fallback="FB"), "FB")


if __name__ == "__main__":
    unittest.main()
