"""Regression tests for quick settings submenu reveal timing.

Content that appears only after the reveal makes the popover jump instead of
growing with the animation.
"""

import unittest
from unittest import mock

from shared.submenu import QuickSubMenu


class TrackingSubMenu(QuickSubMenu):
    """Submenu that records when its content is prepared."""

    def __init__(self):
        self.order = []
        super().__init__(scan_button=None, child=None)

    def prepare_content(self):
        self.order.append("prepare")


class RevealTimingTest(unittest.TestCase):
    """Lazy content must exist before the expand animation starts."""

    def _tracking_submenu(self, revealed: bool) -> TrackingSubMenu:
        submenu = TrackingSubMenu()
        submenu.revealer = mock.Mock()
        submenu.revealer.get_reveal_child.return_value = revealed
        submenu.revealer.set_reveal_child.side_effect = (
            lambda value: submenu.order.append(("reveal", value))
        )
        return submenu

    def test_expand_prepares_content_before_revealing(self):
        submenu = self._tracking_submenu(revealed=False)

        submenu.toggle_reveal()

        self.assertEqual(submenu.order, ["prepare", ("reveal", True)])

    def test_collapse_does_not_rebuild_content(self):
        submenu = self._tracking_submenu(revealed=True)

        submenu.toggle_reveal()

        self.assertEqual(submenu.order, [("reveal", False)])

    def test_reveal_helper_prepares_before_revealing(self):
        submenu = self._tracking_submenu(revealed=False)

        submenu._reveal(True)

        self.assertEqual(submenu.order, ["prepare", ("reveal", True)])


class PowerProfileContentTest(unittest.TestCase):
    """Power profile rows and visibility follow the reveal timing."""

    def test_rows_are_built_before_the_reveal(self):
        from widgets.quick_settings.submenu import power_profiles

        service = mock.Mock(
            profiles=[{"Profile": "power-saver"}, {"Profile": "balanced"}],
            active_profile="balanced",
        )
        with mock.patch.object(power_profiles, "power_profile_service", service):
            submenu = power_profiles.PowerProfileSubMenu()

        self.assertEqual(submenu.profile_box.get_children(), [])

        with mock.patch.object(power_profiles, "power_profile_service", service):
            submenu.prepare_content()

        self.assertEqual(len(submenu.profile_box.get_children()), 2)

    def test_collapse_hides_the_submenu(self):
        from widgets.quick_settings.submenu import power_profiles

        service = mock.Mock(profiles=[], active_profile="balanced")
        with mock.patch.object(power_profiles, "power_profile_service", service):
            submenu = power_profiles.PowerProfileSubMenu()
            submenu.set_visible(True)

            revealer = mock.Mock()
            revealer.get_reveal_child.return_value = False
            submenu.on_child_revealed(revealer)

        self.assertFalse(submenu.get_visible())


if __name__ == "__main__":
    unittest.main()
