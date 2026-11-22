"""Tests for the launcher's empty-query view and launch-count tracking.

The empty query shows Pinned, Frequent and All apps sections, and the launch
counts behind ``Frequent`` are persisted next to the dock's pinned list. ``Launcher``
itself needs a display, so these exercise the methods on a bare instance.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fabric.utils import DesktopApp

from modules import launcher as launcher_module
from modules.launcher import Launcher, _SectionHeader


def make_app(name: str) -> DesktopApp:
    """A real DesktopApp without a display or a D-Bus session."""
    app = DesktopApp.__new__(DesktopApp)
    app.name = name
    app.display_name = name.title()
    return app


def make_launcher(*, usage=None, all_apps=(), find_map=None) -> Launcher:
    """A Launcher with only the state the default view touches."""
    launcher = Launcher.__new__(Launcher)
    launcher._usage = dict(usage or {})
    launcher._all_apps = list(all_apps)
    launcher._first_app = None
    launcher.config = mock.Mock(FREQUENT_LIMIT=5, PINNED_LIMIT=6)
    find_map = find_map or {}
    launcher.app_util = mock.Mock(find_app=lambda identifier: find_map.get(identifier))
    return launcher


def titles(items) -> list[str]:
    return [item.title for item in items if isinstance(item, _SectionHeader)]


def names(items) -> list[str]:
    return [item.name for item in items if not isinstance(item, _SectionHeader)]


class DefaultViewTest(unittest.TestCase):
    """Pinned first, then frequent, then everything else, without repeats."""

    def setUp(self):
        self.pinned = make_app("pinned")
        self.frequent = make_app("frequent")
        self.rest = make_app("rest")
        self.launcher = make_launcher(
            usage={"frequent": 4, "pinned": 9},
            all_apps=[self.pinned, self.frequent, self.rest],
            find_map={"pinned": self.pinned, "frequent": self.frequent},
        )
        self.find_patch = mock.patch.object(
            launcher_module, "read_json_file", return_value=["pinned"]
        )
        self.find_patch.start()
        self.addCleanup(self.find_patch.stop)

    def test_sections_are_ordered_pinned_frequent_all(self):
        items = list(self.launcher._default_view())

        self.assertEqual(["Pinned", "Frequent", "All apps"], titles(items))

    def test_each_app_appears_in_exactly_one_section(self):
        items = list(self.launcher._default_view())

        self.assertEqual(["pinned", "frequent", "rest"], names(items))

    def test_the_first_shown_app_is_the_enter_target(self):
        list(self.launcher._default_view())

        self.assertIs(self.pinned, self.launcher._first_app)

    def test_an_unpinned_system_falls_back_to_frequent(self):
        find_map = {"frequent": self.frequent}
        self.launcher.app_util.find_app = lambda identifier: find_map.get(identifier)
        launcher_module.read_json_file.return_value = []

        items = list(self.launcher._default_view())

        self.assertEqual(["Frequent", "All apps"], titles(items))
        self.assertIs(self.frequent, self.launcher._first_app)

    def test_a_fresh_install_shows_only_all_apps(self):
        launcher = make_launcher(
            all_apps=[self.rest],
            find_map={"rest": self.rest},
        )
        launcher_module.read_json_file.return_value = []

        items = list(launcher._default_view())

        self.assertEqual(["All apps"], titles(items))
        self.assertEqual(["rest"], names(items))


class UsageTrackingTest(unittest.TestCase):
    """Launch counts are filtered on load and written after every launch."""

    def test_load_usage_keeps_only_positive_counts(self):
        launcher = make_launcher()
        with mock.patch.object(
            launcher_module,
            "read_json_file",
            return_value={"a": 2, "b": 0, "c": "nope", "d": 1.9, "e": -3},
        ):
            usage = launcher._load_usage()

        self.assertEqual({"a": 2, "d": 1}, usage)

    def test_load_usage_ignores_a_malformed_file(self):
        launcher = make_launcher()
        with mock.patch.object(launcher_module, "read_json_file", return_value=None):
            self.assertEqual({}, launcher._load_usage())

    def test_record_launch_increments_and_persists(self):
        launcher = make_launcher(usage={"other": 1})
        app = make_app("firefox")

        with (
            mock.patch.object(launcher_module, "write_json_file") as write,
            mock.patch.object(launcher_module.os, "makedirs"),
        ):
            launcher._record_launch(app)

        self.assertEqual({"other": 1, "firefox": 1}, launcher._usage)
        write.assert_called_once_with(
            launcher_module.LAUNCHER_USAGE_FILE, {"other": 1, "firefox": 1}
        )

    def test_record_launch_skips_an_unnamed_app(self):
        launcher = make_launcher()
        app = make_app("")
        app.display_name = ""

        with mock.patch.object(launcher_module, "write_json_file") as write:
            launcher._record_launch(app)

        self.assertEqual({}, launcher._usage)
        write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
