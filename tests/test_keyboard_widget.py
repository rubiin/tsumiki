"""``widgets.keyboard_widget`` renders the shared ``KeyboardService`` state."""

import unittest
from types import SimpleNamespace
from unittest import mock

from services import keyboard_service
from widgets import keyboard_widget
from widgets.keyboard_widget import KeyboardWidget, layout_display_name


class LayoutDisplayNameTest(unittest.TestCase):
    """User names win over the built-in short-name map."""

    def test_user_name_overrides_builtin(self):
        names = {"English (US)": "EN"}
        self.assertEqual("EN", layout_display_name("English (US)", names))

    def test_unmapped_layout_falls_back_to_builtin(self):
        names = {"English (US)": "EN"}
        self.assertEqual("DE", layout_display_name("German", names))

    def test_unknown_layout_falls_back_to_raw_name(self):
        self.assertEqual("Klingon", layout_display_name("Klingon", {}))

    def test_no_map_keeps_builtin(self):
        self.assertEqual("US", layout_display_name("English (US)", None))


class KeyboardWidgetRenderTest(unittest.TestCase):
    """The panel label and tooltip mirror the service properties."""

    def _widget(self, layout="English (US)", caps=False, num=False, names=None):
        widget = KeyboardWidget.__new__(KeyboardWidget)
        widget.config = {"tooltip": True}
        widget.name_map = names or {}
        widget._service = SimpleNamespace(
            layout_name=layout,
            caps_lock=caps,
            num_lock=num,
        )
        widget.refresh_formatted_label = mock.Mock()
        widget.set_tooltip_if_enabled = mock.Mock()
        return widget

    def test_the_widget_uses_the_shared_service(self):
        self.assertIs(keyboard_widget.keyboard_service, keyboard_service)

    def test_layout_changes_refresh_the_label_and_tooltip(self):
        widget = self._widget(layout="German", names={"German": "DE"})

        widget._on_layout_changed()

        widget.refresh_formatted_label.assert_called_once_with(
            layout="DE", caps_state="off", num_state="off"
        )
        widget.set_tooltip_if_enabled.assert_called_once()

    def test_lock_changes_refresh_both_fields_and_the_tooltip(self):
        widget = self._widget(caps=True, num=False)

        widget._on_lock_changed()

        widget.refresh_formatted_label.assert_called_once_with(
            layout="US", caps_state="on", num_state="off"
        )
        tooltip = widget.set_tooltip_if_enabled.call_args.args[0]
        self.assertIn("Caps Lock 󰪛: On", tooltip)
        self.assertIn("Num Lock \uea90: Off", tooltip)

    def test_an_empty_layout_renders_the_fallback(self):
        widget = self._widget(layout="")

        widget._on_layout_changed()

        widget.refresh_formatted_label.assert_called_once_with(
            layout="Unknown", caps_state="off", num_state="off"
        )


if __name__ == "__main__":
    unittest.main()
