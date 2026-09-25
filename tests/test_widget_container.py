"""Tests for ``ButtonWidget.add_panel_content``.

Every panel widget is an icon plus an optional label, and this is now the one
place that builds that pair. The GTK classes are mocked so the composition can
be checked without a display.
"""

import unittest
from unittest import mock

from fabric.widgets.label import Label

from shared import widget_container
from shared.widget_container import ButtonWidget


def make_widget() -> ButtonWidget:
    widget = ButtonWidget.__new__(ButtonWidget)
    widget.container_box = mock.Mock()
    return widget


class AddPanelContentTest(unittest.TestCase):
    """The icon/label pair is built the same way for every panel widget."""

    def setUp(self):
        patcher = mock.patch.object(widget_container, "Label")
        self.Label_mock = patcher.start()
        self.addCleanup(patcher.stop)
        # nerd_font_icon is imported inside the method; patch it where it lives.
        import utils.widget_utils as widget_utils

        patcher = mock.patch.object(
            widget_utils, "nerd_font_icon", return_value="nerd-icon"
        )
        self.nerd_font_icon = patcher.start()
        self.addCleanup(patcher.stop)

    def test_icon_string_becomes_a_nerd_font_icon(self):
        widget = make_widget()

        widget.add_panel_content("󰇁")

        self.nerd_font_icon.assert_called_once_with(
            icon="󰇁", props={"style_classes": ["panel-font-icon"]}
        )
        widget.container_box.children = "nerd-icon"

    def test_label_string_becomes_a_panel_text_label(self):
        widget = make_widget()

        widget.add_panel_content("󰇁", "Text")

        self.Label_mock.assert_called_once_with(
            label="Text", style_classes="panel-text"
        )
        widget.container_box.add.assert_called_once_with(self.Label_mock.return_value)

    def test_show_label_false_omits_the_label(self):
        widget = make_widget()

        widget.add_panel_content("󰇁", "Text", show_label=False)

        self.Label_mock.assert_not_called()
        widget.container_box.add.assert_not_called()

    def test_no_label_never_builds_one(self):
        widget = make_widget()

        widget.add_panel_content("󰇁")

        self.Label_mock.assert_not_called()

    def test_prebuilt_icon_widget_is_used_as_is(self):
        widget = make_widget()
        icon = Label(label="prebuilt")

        widget.add_panel_content(icon, "Text")

        self.nerd_font_icon.assert_not_called()
        widget.container_box.children = icon

    def test_prebuilt_label_widget_is_used_as_is(self):
        widget = make_widget()
        label = Label(label="prebuilt")

        widget.add_panel_content("󰇁", label)

        self.Label_mock.assert_not_called()
        widget.container_box.add.assert_called_once_with(label)


if __name__ == "__main__":
    unittest.main()
