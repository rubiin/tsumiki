"""Tests for ``WindowTitleWidget``'s fallback glyph.

The fallback title used to carry a hardcoded glyph, so the only way to drop it
was to disable mappings entirely. ``fallback_icon`` makes the glyph configurable,
with an empty string meaning "no glyph".
"""

import unittest
from unittest import mock

from fabric.hyprland.widgets import HyprlandActiveWindow

from widgets.window_title import WindowTitleWidget

SOURCE_PATH = "widgets/window_title.py"


def build_widget(**config) -> WindowTitleWidget:
    """Run the real constructor with a stub container and no Hyprland window."""
    def stub_init(self, **_kwargs):
        self.config = config

    with (
        mock.patch.object(HyprlandActiveWindow, "__init__", stub_init),
        mock.patch.object(WindowTitleWidget, "connect"),
        mock.patch.object(WindowTitleWidget, "_connect_hover_reveal"),
        mock.patch.object(WindowTitleWidget, "_sync_hover_cursor"),
        mock.patch.object(WindowTitleWidget, "_sync_occupancy"),
    ):
        return WindowTitleWidget()


def render(**config) -> str:
    """The label the widget builds for a class no title_map rule matches."""
    widget = build_widget(**config)
    with mock.patch.object(WindowTitleWidget, "_set_tooltip"):
        return widget._get_title("Some Window Title", "org.example.Nomatch")


class FallbackIconTest(unittest.TestCase):
    """``fallback_icon`` owns the glyph in front of the fallback title."""

    def test_the_default_glyph_is_unchanged(self):
        self.assertEqual("\U000f08c6 org.example.nomatch", render())

    def test_a_configured_glyph_replaces_the_default(self):
        self.assertEqual("A org.example.nomatch", render(fallback_icon="A"))

    def test_an_empty_glyph_drops_it_without_a_leading_space(self):
        self.assertEqual("org.example.nomatch", render(fallback_icon=""))

    def test_the_glyph_follows_the_fallback_source(self):
        title = render(fallback="title", fallback_icon="A")

        self.assertEqual("A some window title", title)

    def test_the_glyph_is_no_longer_hardcoded(self):
        with open(SOURCE_PATH, encoding="utf-8") as source:
            text = source.read()

        self.assertIn('self.config.get("fallback_icon"', text)
        # The literal may only survive as the default argument.
        self.assertNotIn("return f\"\U000f08c6", text)


if __name__ == "__main__":
    unittest.main()
