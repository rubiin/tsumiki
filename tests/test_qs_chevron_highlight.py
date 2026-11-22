"""Tests for the Quick Settings chevron tile highlight."""

import unittest
from unittest import mock

from shared.buttons import QSChevronButton


class SubmenuOpenHighlightTest(unittest.TestCase):
    """The tile owning an open submenu must stay highlighted."""

    def _toggle_with_submenu(self, revealed: bool) -> QSChevronButton:
        toggle = QSChevronButton()
        toggle.submenu = mock.Mock()
        toggle.submenu.revealer.get_reveal_child.return_value = revealed
        return toggle

    def test_open_submenu_highlights_the_tile(self):
        toggle = self._toggle_with_submenu(True)

        toggle.update_reveal_state()

        self.assertIn("submenu-open", toggle.get_style_classes())

    def test_closed_submenu_clears_the_highlight(self):
        toggle = self._toggle_with_submenu(True)
        toggle.update_reveal_state()

        toggle.submenu.revealer.get_reveal_child.return_value = False
        toggle.update_reveal_state()

        self.assertNotIn("submenu-open", toggle.get_style_classes())

    def test_missing_submenu_is_tolerated(self):
        toggle = QSChevronButton()

        toggle.update_reveal_state()

        self.assertNotIn("submenu-open", toggle.get_style_classes())


if __name__ == "__main__":
    unittest.main()
