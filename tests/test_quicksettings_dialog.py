"""The quick settings popover is built once and reused.

``show_dialog`` used to hide the menu's parent before opening the power dialog,
which left the cached popover blank on every later open. It must only dismiss
the popover itself.
"""

import unittest
from unittest import mock

from widgets.quick_settings.quick_settings import QuickSettingsMenu


class FakeMenu:
    """Stand-in for QuickSettingsMenu: show_dialog only needs the popup handle."""

    def __init__(self):
        self.popup = mock.Mock()


class QuickSettingsDialogTest(unittest.TestCase):
    """Guard the cached-menu lifecycle in show_dialog."""

    def test_power_dialog_does_not_hide_the_cached_menu(self):
        menu = FakeMenu()

        with mock.patch("widgets.quick_settings.quick_settings.Dialog") as dialog_cls:
            QuickSettingsMenu.show_dialog(menu, "Reboot", "Are you sure?", "reboot")

        menu.popup.hide_popover.assert_called_once_with()
        dialog_cls.return_value.add_content.assert_called_once_with(
            title="Reboot", body="Are you sure?", command="reboot"
        )
        dialog_cls.return_value.add_content.return_value.toggle_popup.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
