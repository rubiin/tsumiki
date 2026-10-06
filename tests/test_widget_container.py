"""Tests for ``ButtonWidget.add_panel_content``.

Every panel widget is an icon plus an optional label, and this is now the one
place that builds that pair. The GTK classes are mocked so the composition can
be checked without a display.
"""

import unittest
from pathlib import Path
from typing import ClassVar
from unittest import mock

from fabric.utils import Gtk
from fabric.widgets.label import Label

import utils.widget_utils as widget_utils
from shared import widget_container
from shared.widget_container import ButtonWidget
from utils.constants import DEFAULT_CONFIG


def make_widget() -> ButtonWidget:
    widget = ButtonWidget.__new__(ButtonWidget)
    widget.container_box = mock.Mock()
    return widget


class FakeWindow:
    """A Gdk.Window stand-in that records the cursors it was handed."""

    def __init__(self):
        self.cursors: list = []

    def set_cursor(self, cursor):
        self.cursors.append(cursor)


class ButtonCursorProbe:
    """ButtonWidget's real hover-cursor handler without GTK widget init."""

    _sync_hover_cursor = ButtonWidget._sync_hover_cursor

    def __init__(self, *, realized: bool = True):
        self.state = Gtk.StateFlags.NORMAL
        self.window = FakeWindow() if realized else None
        self.display = mock.Mock(name="display")

    def get_state_flags(self):
        return self.state

    def get_window(self):
        return self.window

    def get_display(self):
        return self.display

    def set_cursor(self, cursor_name: str):
        """Stand-in for fabric's setter, which needs a window that does not exist."""
        cursor = widget_utils.Gdk.Cursor.new_from_name(self.get_display(), cursor_name)
        self.get_window().set_cursor(cursor)  # None before realization

    def set_state(self, state: Gtk.StateFlags):
        self.state = state
        self._sync_hover_cursor()


class AddFormattedLabelTest(unittest.TestCase):
    """``label_format`` renders one label; a live glyph leads it."""

    def setUp(self):
        patcher = mock.patch.object(widget_container, "Label")
        self.Label_mock = patcher.start()
        self.addCleanup(patcher.stop)

    def _widget(self, template: str) -> ButtonWidget:
        widget = ButtonWidget.__new__(ButtonWidget)
        widget.container_box = mock.Mock()
        widget.label_format = template
        return widget

    def test_the_label_carries_the_format_class(self):
        """Per-widget icon sizing keys off ``panel-format`` now."""
        self._widget("󰅚").add_formatted_label("󰅚")

        self.Label_mock.assert_called_once_with(
            style_classes=["panel-text", "panel-format"]
        )

    def test_the_glyph_leads_the_format(self):
        widget = self._widget("Bluetooth")

        widget.add_formatted_label(widget.label_format, "󰅚")

        self.Label_mock.return_value.set_markup.assert_called_once_with(
            "󰅚 Bluetooth"
        )

    def test_refreshing_renders_the_current_glyph(self):
        widget = self._widget("Mic")
        widget.add_formatted_label(widget.label_format, "mic-off")

        widget.refresh_formatted_label("mic-on")

        self.Label_mock.return_value.set_markup.assert_called_with("mic-on Mic")


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

    def test_a_none_icon_leaves_the_label_as_the_only_content(self):
        widget = make_widget()

        widget.add_panel_content(None, "Text")

        self.nerd_font_icon.assert_not_called()
        widget.container_box.children = ()
        widget.container_box.add.assert_called_once_with(self.Label_mock.return_value)


class StatWidgetDefaultsTest(unittest.TestCase):
    """No widget keeps an ``icon`` prop or a ``{icon}`` field any more."""

    WIDGETS = ("cpu", "gpu", "memory", "storage")

    def test_the_stat_widgets_keep_a_glyph_in_label_format(self):
        """Their ``label_format`` is the glyph itself: no other field to hold."""
        for name in self.WIDGETS:
            with self.subTest(widget=name):
                config = DEFAULT_CONFIG["widgets"][name]

                self.assertNotIn("icon", config)
                self.assertTrue(config["label_format"].strip())

    def test_no_widget_keeps_an_icon_prop(self):
        """A fixed glyph belongs in ``label_format``, so ``icon`` is redundant."""
        offenders = [
            name
            for name, config in DEFAULT_CONFIG["widgets"].items()
            if isinstance(config, dict)
            and "icon" in config
            and "label_format" in config
        ]

        self.assertEqual([], offenders)

    def test_no_widget_format_still_asks_for_the_icon_field(self):
        offenders = [
            name
            for name, config in DEFAULT_CONFIG["widgets"].items()
            if isinstance(config, dict) and "{icon}" in config.get("label_format", "")
        ]

        self.assertEqual([], offenders)


class LabelToggleIsGoneTest(unittest.TestCase):
    """``label_format`` replaced the ``label`` boolean; the label is mandatory."""

    WIDGETS: ClassVar = {
        "hyprpicker": "widgets/hyprpicker.py",
        "keyboard": "widgets/keyboard_layout.py",
        "microphone": "widgets/microphone.py",
        "ocr": "widgets/ocr.py",
        "power": "widgets/power_button.py",
        "submap": "widgets/submap.py",
        "updates": "widgets/updates.py",
        "bluetooth": "widgets/bluetooth.py",
        "clipboard": "widgets/clipboard.py",
        "emoji_picker": "widgets/emoji_picker.py",
        "kanban": "widgets/kanban.py",
        "overview_button": "widgets/overview_button.py",
        "screenshot": "widgets/screenshot.py",
        "settings": "widgets/settings.py",
        "usb_manager": "widgets/usb_manager.py",
        "wallpaper": "widgets/wallpaper.py",
    }

    def test_no_widget_declares_a_label_toggle(self):
        for name in self.WIDGETS:
            with self.subTest(widget=name):
                config = DEFAULT_CONFIG["widgets"][name]

                self.assertNotIn("label", config)
                self.assertIn("label_format", config)

    def test_no_widget_reads_the_label_toggle(self):
        for name, path in self.WIDGETS.items():
            with self.subTest(widget=name):
                source = Path(path).read_text(encoding="utf-8")

                self.assertNotIn('config.get("label"', source)

    def test_no_widget_declares_a_label_toggle_at_all(self):
        """Sweep every widget default: ``label`` was a bool everywhere."""
        offenders = [
            name
            for name, config in DEFAULT_CONFIG["widgets"].items()
            if isinstance(config, dict) and "label" in config
        ]

        self.assertEqual([], offenders)


class HoverCursorTest(unittest.TestCase):
    """Every bar button flips its cursor on hover, and none of them are realized."""

    def setUp(self):
        patcher = mock.patch.object(widget_utils, "Gdk")
        self.Gdk = patcher.start()
        self.addCleanup(patcher.stop)
        self.Gdk.Cursor.new_from_name.side_effect = lambda _display, name: (
            f"cursor:{name}"
        )
        widget_utils._cursors.clear()
        self.addCleanup(widget_utils._cursors.clear)

    def test_a_state_change_before_realization_does_not_raise(self):
        probe = ButtonCursorProbe(realized=False)

        probe.set_state(Gtk.StateFlags.PRELIGHT)
        probe.set_state(Gtk.StateFlags.NORMAL)

    def test_no_cursor_is_built_before_the_widget_has_a_window(self):
        probe = ButtonCursorProbe(realized=False)

        probe.set_state(Gtk.StateFlags.PRELIGHT)

        self.Gdk.Cursor.new_from_name.assert_not_called()

    def test_prelight_points_at_the_pointer(self):
        probe = ButtonCursorProbe()

        probe.set_state(Gtk.StateFlags.PRELIGHT)

        self.assertEqual(["cursor:pointer"], probe.window.cursors)

    def test_losing_prelight_returns_the_default_cursor(self):
        probe = ButtonCursorProbe()
        probe.set_state(Gtk.StateFlags.PRELIGHT)

        probe.set_state(Gtk.StateFlags.NORMAL)

        self.assertEqual(["cursor:pointer", "cursor:default"], probe.window.cursors)

    def test_focus_alone_is_not_a_hover(self):
        """The old bare ``& 2`` mask treated FOCUSED (6) as prelit."""
        probe = ButtonCursorProbe()

        probe.set_state(Gtk.StateFlags.FOCUSED)

        self.assertEqual(["cursor:default"], probe.window.cursors)

    def test_repeated_state_changes_reuse_one_cursor_each(self):
        probe = ButtonCursorProbe()

        for _ in range(5):
            probe.set_state(Gtk.StateFlags.PRELIGHT)
            probe.set_state(Gtk.StateFlags.NORMAL)

        self.assertEqual(2, self.Gdk.Cursor.new_from_name.call_count)


if __name__ == "__main__":
    unittest.main()
