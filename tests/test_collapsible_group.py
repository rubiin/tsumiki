"""Tests for ``CollapsibleGroupWidget``'s toggle button label.

The button rendered an icon label and, separately, an optional ``label`` text
behind ``show_label``. ``label_format`` now drives the one label and carries the
glyph itself, so ``icon`` / ``show_icon`` / ``show_label`` / ``label`` are gone.
"""

import unittest
from unittest import mock

from shared.collapsible_group import CollapsibleGroupWidget
from shared.widget_container import ButtonWidget, format_panel_label

SOURCE_PATH = "shared/collapsible_group.py"


def build_group(**config) -> CollapsibleGroupWidget:
    """Run the real constructor with a stub container and no GTK window."""
    container_box = mock.Mock()
    popover = mock.Mock()

    def stub_init(self, **_kwargs):
        self.config = config
        self.container_box = container_box
        self.tooltips_enabled = False
        self.setup_popover = mock.Mock(return_value=popover)

    with (
        mock.patch.object(ButtonWidget, "__init__", stub_init),
        mock.patch.object(CollapsibleGroupWidget, "connect"),
    ):
        return CollapsibleGroupWidget()


class CollapsibleGroupLabelFormatTest(unittest.TestCase):
    """The toggle button is one label built from ``label_format``."""

    def setUp(self):
        patcher = mock.patch.object(ButtonWidget, "add_formatted_label")
        self.add_formatted_label = patcher.start()
        self.addCleanup(patcher.stop)

    def _rendered(self, **config):
        build_group(**config)
        return self.add_formatted_label.call_args.args

    def test_the_default_format_carries_the_glyph(self):
        template = self._rendered()[0]

        self.assertEqual("󰍽", template)

    def test_an_empty_format_renders_nothing(self):
        template = self._rendered(label_format="")[0]

        self.assertEqual("", format_panel_label(template))

    def test_literal_text_after_the_glyph_is_kept(self):
        template = self._rendered(label_format="󰍽 Tools")[0]

        self.assertEqual("󰍽 Tools", format_panel_label(template))

    def test_the_icon_prop_is_gone(self):
        """The glyph lives in ``label_format``, so ``icon`` is redundant."""
        from utils.validation import _VALID_COLLECTION_LABEL_FORMATS

        with open(SOURCE_PATH, encoding="utf-8") as source:
            self.assertNotIn('config.get("icon"', source.read())

        formats = _VALID_COLLECTION_LABEL_FORMATS["collapsible_groups"]
        self.assertEqual(set(), formats["label_format"])

    def test_the_toggle_keys_are_gone(self):
        with open(SOURCE_PATH, encoding="utf-8") as source:
            text = source.read()

        for gone in (
            'config.get("show_icon"',
            'config.get("show_label"',
            'config.get("label"',
        ):
            with self.subTest(key=gone):
                self.assertNotIn(gone, text)

    def test_the_button_keeps_exactly_one_label(self):
        """A sibling text label would escape ``label_format`` and restyling."""
        with open(SOURCE_PATH, encoding="utf-8") as source:
            text = source.read()

        self.assertIn("add_formatted_label(", text)
        self.assertNotIn("self.container_box.add(", text)


class CollapsibleGroupUpdateConfigTest(unittest.TestCase):
    """A config reload re-renders the label with the new format."""

    def test_update_config_rebuilds_the_label(self):
        widget = build_group(label_format="󰍽")
        widget.add_formatted_label = mock.Mock()
        widget.container_box.get_children.return_value = [mock.Mock()]
        widget.set_tooltip_text = mock.Mock()

        widget.update_config({"label_format": "󰌌 Tools"})

        widget.add_formatted_label.assert_called_once_with("󰌌 Tools")

    def test_update_config_drops_the_deprecated_keys(self):
        """``icon``/``show_icon``/``label`` in a config no longer reach the widget."""
        widget = build_group(label_format="󰍽")
        widget.add_formatted_label = mock.Mock()
        widget.container_box.get_children.return_value = [mock.Mock()]
        widget.set_tooltip_text = mock.Mock()

        widget.update_config(
            {"icon": "󰌌", "show_icon": False, "label": "Tools", "show_label": True}
        )

        template = widget.add_formatted_label.call_args.args[0]
        self.assertEqual("󰍽", template)


if __name__ == "__main__":
    unittest.main()
