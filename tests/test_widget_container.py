"""Tests for ``ButtonWidget.add_panel_content``.

Every panel widget is an icon plus an optional label, and this is now the one
place that builds that pair. The GTK classes are mocked so the composition can
be checked without a display.
"""

import unittest
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


class FormatShowsIconTest(unittest.TestCase):
    """``show_icon`` is gone: the ``{icon}`` field of ``label_format`` decides."""

    @staticmethod
    def _widget(**config) -> ButtonWidget:
        widget = ButtonWidget.__new__(ButtonWidget)
        widget.config = config
        return widget

    def test_the_default_format_keeps_the_icon(self):
        self.assertTrue(self._widget().format_shows_icon())

    def test_a_format_naming_the_icon_keeps_the_icon(self):
        self.assertTrue(self._widget(label_format="{icon}").format_shows_icon())

    def test_a_format_without_the_icon_field_drops_it(self):
        """The regression: ``show_icon = false`` no longer has any effect."""
        self.assertFalse(self._widget(label_format="").format_shows_icon())

    def test_an_unrelated_field_does_not_bring_the_icon_back(self):
        self.assertFalse(self._widget(label_format="{count}").format_shows_icon())

    def test_a_non_string_format_is_treated_as_no_icon(self):
        self.assertFalse(self._widget(label_format=None).format_shows_icon())


class IconOnlyWidgetDefaultsTest(unittest.TestCase):
    """The icon-plus-text widgets ship ``label_format = "{icon}"`` and gate on it."""

    WIDGETS = ("dns_switcher", "pomodoro", "cloudflare_warp", "github_tray")

    def test_every_widget_defaults_to_showing_its_icon(self):
        for name in self.WIDGETS:
            with self.subTest(widget=name):
                widget = ButtonWidget.__new__(ButtonWidget)
                widget.config = DEFAULT_CONFIG["widgets"][name]

                self.assertEqual("{icon}", widget.config["label_format"])
                self.assertTrue(widget.format_shows_icon())

    def test_every_widget_drops_the_icon_without_the_field(self):
        for name in self.WIDGETS:
            with self.subTest(widget=name):
                widget = ButtonWidget.__new__(ButtonWidget)
                widget.config = {"label_format": ""}

                self.assertFalse(widget.format_shows_icon())


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
