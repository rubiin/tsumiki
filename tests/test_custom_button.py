"""Tests for ``CustomButtonWidget``'s icon visibility.

``show_icon`` was replaced by ``label_format``: the icon renders when the
button's format string names ``{icon}``. The button is icon-only; the
``label`` and ``label_text`` keys are gone.
"""

import unittest
from unittest import mock

from shared.custom_button import CustomButtonWidget
from shared.widget_container import ButtonWidget


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
        patcher = mock.patch(
            "shared.custom_button.nerd_font_icon", return_value="nerd-icon"
        )
        self.nerd_font_icon = patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_default_format_renders_the_icon(self):
        button = build_button(icon="󰈹")

        self.assertEqual(button.icon, "nerd-icon")

    def test_a_format_naming_the_icon_renders_it(self):
        button = build_button(icon="󰈹", label_format="{icon}")

        self.assertEqual(button.icon, "nerd-icon")

    def test_a_format_without_the_icon_field_drops_it(self):
        """The regression: show_icon was the toggle before label_format."""
        button = build_button(icon="󰈹", label_format="")

        self.assertFalse(hasattr(button, "icon"))
        button.container_box.add.assert_not_called()

    def test_a_missing_icon_stays_absent_even_with_the_format(self):
        button = build_button(label_format="{icon}")

        self.assertFalse(hasattr(button, "icon"))

    def test_the_constructor_no_longer_reads_show_icon(self):
        with open("shared/custom_button.py", encoding="utf-8") as source:
            self.assertNotIn('config.get("show_icon"', source.read())

    def test_the_label_keys_are_gone(self):
        """The icon is the whole content, so ``label``/``label_text`` are stale."""
        button = build_button(icon="󰈹", label=True, label_text="Firefox")

        self.assertFalse(hasattr(button, "label"))
        button.container_box.add.assert_called_once_with("nerd-icon")


if __name__ == "__main__":
    unittest.main()
