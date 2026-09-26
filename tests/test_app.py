"""Tests for ``utils/app.py`` desktop-app lookup.

The app list is loaded lazily to save startup memory, so any entry point that
touches the identifier map has to trigger the load itself: ``find_app`` is
routinely the very first thing called, before any property has run.
"""

import unittest
from unittest import mock

from utils.app import AppUtils


def make_app(name="WezTerm", window_class="org.wezfurlong.wezterm"):
    """A stand-in for fabric's DesktopApp, which this module only reads from."""
    return mock.Mock(
        name=name,
        display_name=name,
        window_class=window_class,
        executable="wezterm",
        command_line="wezterm start --cwd .",
    )


class FindAppTest(unittest.TestCase):
    """``find_app`` must work on a freshly constructed singleton."""

    def setUp(self):
        AppUtils.reset_instance()
        self.addCleanup(AppUtils.reset_instance)

        self.app = make_app()
        patcher = mock.patch(
            "utils.app.get_desktop_applications", return_value=[self.app]
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_find_app_loads_lazily_on_a_cold_singleton(self):
        """The reported bug: find_app raised before any property ran."""
        util = AppUtils()
        self.assertIsNone(util._all_applications)

        self.assertIs(self.app, util.find_app("org.wezfurlong.wezterm"))
        self.assertIsNotNone(util._all_applications)

    def test_find_app_returns_none_for_an_empty_identifier(self):
        """An empty id must not pay for loading the whole app database."""
        util = AppUtils()

        self.assertIsNone(util.find_app(""))
        self.assertIsNone(util._all_applications)

    def test_find_app_matches_a_partial_identifier(self):
        util = AppUtils()

        self.assertIs(self.app, util.find_app("wezterm"))


if __name__ == "__main__":
    unittest.main()
