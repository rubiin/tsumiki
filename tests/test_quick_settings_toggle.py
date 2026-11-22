"""Tests for the shared Quick Settings toggle tile base."""

import unittest
from unittest import mock

from widgets.quick_settings.toggle_base import QuickSettingToggle


class _FakePopup:
    def __init__(self):
        self.hide_popover = mock.Mock()


class SetStateTest(unittest.TestCase):
    """set_state must update visuals once and skip unchanged refreshes."""

    def test_updates_labels_and_active_class(self):
        toggle = QuickSettingToggle(None, icon="off", title="Wi-Fi", subtitle="off")

        toggle.set_state(True, icon="on", status="connected")

        self.assertIn("active", toggle.get_style_classes())
        self.assertEqual("on", toggle.icon_label.get_label())
        self.assertEqual("connected", toggle.status_label.get_label())

    def test_unchanged_state_does_not_touch_labels(self):
        toggle = QuickSettingToggle(None, icon="off", title="Wi-Fi", subtitle="off")
        toggle.set_state(True, icon="on", status="connected")

        with (
            mock.patch.object(toggle.icon_label, "set_label") as set_icon,
            mock.patch.object(toggle.status_label, "set_label") as set_status,
        ):
            for _ in range(5):
                toggle.set_state(True, icon="on", status="connected")

        set_icon.assert_not_called()
        set_status.assert_not_called()

    def test_toggling_back_removes_active_class(self):
        toggle = QuickSettingToggle(None, icon="off", title="Wi-Fi", subtitle="off")
        toggle.set_state(True, icon="on", status="connected")

        toggle.set_state(False, icon="off", status="off")

        self.assertNotIn("active", toggle.get_style_classes())

    def test_missing_subtitle_is_tolerated(self):
        toggle = QuickSettingToggle(None, icon="x", title="Title")

        toggle.set_state(True, icon="y", status="ignored")

        self.assertEqual("y", toggle.icon_label.get_label())


class ClickTest(unittest.TestCase):
    """Clicking must hide the popover, and subclasses must implement on_click."""

    def test_click_hides_popup(self):
        popup = _FakePopup()
        toggle = QuickSettingToggle(popup, icon="x", title="Title")

        toggle._on_clicked()

        popup.hide_popover.assert_called_once()

    def test_click_without_popup_is_safe(self):
        toggle = QuickSettingToggle(None, icon="x", title="Title")

        toggle._on_clicked()  # must not raise

    def test_default_on_click_requires_implementation(self):
        toggle = QuickSettingToggle(None, icon="x", title="Title")

        with self.assertRaises(NotImplementedError):
            toggle.on_click()


class ActiveStyleTest(unittest.TestCase):
    """set_active_style must preserve the tile's existing style classes."""

    def test_preserves_base_classes(self):
        toggle = QuickSettingToggle(None, icon="x", title="Title")

        toggle.set_active_style(True)

        classes = toggle.get_style_classes()
        self.assertIn("active", classes)
        self.assertIn("quicksettings-toggler", classes)

        toggle.set_active_style(False)

        classes = toggle.get_style_classes()
        self.assertNotIn("active", classes)
        self.assertIn("quicksettings-toggler", classes)


if __name__ == "__main__":
    unittest.main()
