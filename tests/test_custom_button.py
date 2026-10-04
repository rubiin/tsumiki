"""Tests for ``CustomButtonWidget``'s label rendering.

``show_icon`` was replaced by ``label_format``, and the icon now shares one
label with whatever literal text the format carries. The ``label`` and
``label_text`` keys are gone.
"""

import unittest
from unittest import mock

from shared.custom_button import CustomButtonWidget
from shared.widget_container import ButtonWidget, format_panel_label


def build_button(**config) -> CustomButtonWidget:
    """Run the real constructor with a stub container and no GTK window."""
    container_box = mock.Mock()

    def stub_init(self, **_kwargs):
        self.container_box = container_box
        self.tooltips_enabled = False

    with (
        mock.patch.object(ButtonWidget, "__init__", stub_init),
        mock.patch.object(CustomButtonWidget, "connect"),
    ):
        return CustomButtonWidget(config={"command": "firefox", **config})


class CustomButtonIconFormatTest(unittest.TestCase):
    """The icon follows label_format, the way every other panel widget does."""

    def setUp(self):
        patcher = mock.patch.object(ButtonWidget, "add_formatted_label")
        self.add_formatted_label = patcher.start()
        self.addCleanup(patcher.stop)

    def _rendered(self, **config):
        build_button(**config)
        return self.add_formatted_label.call_args.args

    def test_the_default_format_renders_the_icon(self):
        template, glyph = self._rendered(icon="󰈹")

        self.assertEqual("{icon}", template)
        self.assertEqual("󰈹", glyph)

    def test_a_format_without_the_icon_field_drops_it(self):
        """The regression: show_icon was the toggle before label_format."""
        template, glyph = self._rendered(icon="󰈹", label_format="")

        self.assertEqual("", format_panel_label(template, glyph))

    def test_literal_text_in_the_format_is_kept(self):
        template, glyph = self._rendered(icon="󰈹", label_format="{icon} Firefox")

        self.assertEqual("󰈹 Firefox", format_panel_label(template, glyph))

    def test_a_missing_icon_renders_only_the_literal_text(self):
        template, glyph = self._rendered(label_format="{icon} Firefox")

        self.assertEqual("Firefox", format_panel_label(template, glyph or ""))

    def test_the_constructor_no_longer_reads_show_icon(self):
        with open("shared/custom_button.py", encoding="utf-8") as source:
            self.assertNotIn('config.get("show_icon"', source.read())

    def test_the_label_keys_are_gone(self):
        with open("shared/custom_button.py", encoding="utf-8") as source:
            self.assertNotIn('config.get("label"', source)


if __name__ == "__main__":
    unittest.main()
