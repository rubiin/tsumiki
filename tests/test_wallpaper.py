"""Tests for the wallpaper picker's state helpers and output parsing."""

import os
import tempfile
import unittest
from unittest import mock

from utils import wallpaper as wallpaper_module
from utils.wallpaper import (
    apply_wallpaper,
    get_last_wallpaper,
    list_wallpapers,
    parse_awww_query,
    parse_listactive,
    save_wallpaper,
    wallpaper_directory,
    wallpaper_for_monitor,
)


class WallpaperStateTest(unittest.TestCase):
    """Saved wallpapers survive restarts, per monitor or for all monitors."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.state_file = os.path.join(self._tmpdir.name, "wallpaper_picker.json")
        patcher = mock.patch.object(
            wallpaper_module, "WALLPAPER_STATE_FILE", self.state_file
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.first = os.path.join(self._tmpdir.name, "first.png")
        self.second = os.path.join(self._tmpdir.name, "second.png")
        for path in (self.first, self.second):
            with open(path, "w") as handle:
                handle.write("")

    def test_default_wallpaper_is_remembered(self):
        save_wallpaper(self.first)

        self.assertEqual(get_last_wallpaper(), self.first)
        self.assertEqual(wallpaper_for_monitor("DP-1"), self.first)

    def test_monitor_wallpaper_overrides_the_default(self):
        save_wallpaper(self.first)
        save_wallpaper(self.second, ["DP-2"])

        self.assertEqual(wallpaper_for_monitor("DP-2"), self.second)
        self.assertEqual(wallpaper_for_monitor("DP-1"), self.first)

    def test_a_missing_file_is_ignored(self):
        save_wallpaper(self.first)
        os.unlink(self.first)

        self.assertIsNone(get_last_wallpaper())
        self.assertIsNone(wallpaper_for_monitor("DP-1"))

    def test_setting_all_monitors_drops_previous_overrides(self):
        save_wallpaper(self.first, ["DP-2"])
        save_wallpaper(self.second)

        self.assertEqual(wallpaper_for_monitor("DP-2"), self.second)


class ListWallpapersTest(unittest.TestCase):
    """Only images count as wallpapers."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        patcher = mock.patch.object(
            wallpaper_module, "wallpaper_directory", return_value=self._tmpdir.name
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_only_images_are_listed_newest_first(self):
        for index, name in enumerate(("old.png", "notes.txt", "new.jpg")):
            path = os.path.join(self._tmpdir.name, name)
            with open(path, "w") as handle:
                handle.write("")
            os.utime(path, (index + 1, index + 1))

        self.assertEqual(list_wallpapers(), ["new.jpg", "old.png"])

    def test_names_can_be_sorted_alphabetically(self):
        for name in ("b.png", "a.png", "c.png"):
            path = os.path.join(self._tmpdir.name, name)
            with open(path, "w") as handle:
                handle.write("")

        with mock.patch.object(wallpaper_module, "wallpaper_sort", return_value="name"):
            self.assertEqual(list_wallpapers(), ["a.png", "b.png", "c.png"])

    def test_a_missing_directory_lists_nothing(self):
        with mock.patch.object(
            wallpaper_module,
            "wallpaper_directory",
            return_value=os.path.join(self._tmpdir.name, "missing"),
        ):
            self.assertEqual(list_wallpapers(), [])


class WallpaperDirectoryTest(unittest.TestCase):
    """The wallpaper folder comes from [modules.wallpaper]."""

    def test_configured_directory_is_expanded(self):
        with mock.patch.object(
            wallpaper_module,
            "_module_config",
            return_value={"directory": "~/Pictures/Walls"},
        ):
            self.assertEqual(
                wallpaper_directory(),
                os.path.join(os.path.expanduser("~"), "Pictures/Walls"),
            )

    def test_unset_directory_falls_back_to_the_default(self):
        with mock.patch.object(wallpaper_module, "_module_config", return_value={}):
            self.assertEqual(wallpaper_directory(), wallpaper_module.WALLPAPER_DIR)


class ParseListActiveTest(unittest.TestCase):
    """hyprpaper's listactive output names a path per monitor."""

    def test_monitor_paths_are_parsed(self):
        output = "DP-1: /home/user/wall one.png\nHDMI-A-1: /home/user/two.png\n"

        self.assertEqual(
            parse_listactive(output),
            {
                "DP-1": "/home/user/wall one.png",
                "HDMI-A-1": "/home/user/two.png",
            },
        )

    def test_lines_without_a_path_are_skipped(self):
        output = "DP-1: /home/user/one.png\nempty:\nno separator\n"

        self.assertEqual(parse_listactive(output), {"DP-1": "/home/user/one.png"})


class ParseAwwwQueryTest(unittest.TestCase):
    """awww query names the image each monitor is showing."""

    def test_monitor_paths_are_parsed(self):
        output = (
            ": DP-1: 1920x1080, scale: 1, "
            "currently displaying: image: /home/user/a.png\n"
            ": HDMI-A-1: 2560x1440, scale: 1.5, "
            "currently displaying: image: /home/user/b.png\n"
        )

        self.assertEqual(
            parse_awww_query(output),
            {"DP-1": "/home/user/a.png", "HDMI-A-1": "/home/user/b.png"},
        )

    def test_a_namespaced_daemon_prefix_is_ignored(self):
        output = (
            "awww-daemon: DP-1: 1920x1080, scale: 1, "
            "currently displaying: image: /home/user/a.png"
        )

        self.assertEqual(parse_awww_query(output), {"DP-1": "/home/user/a.png"})

    def test_colors_and_empty_outputs_are_skipped(self):
        output = (
            ": DP-1: 1920x1080, scale: 1, currently displaying: color: 000000\n"
            ": HDMI-A-1: 2560x1440, scale: 1, currently displaying: image: \n"
        )

        self.assertEqual(parse_awww_query(output), {})


class ApplyWallpaperBackendTest(unittest.TestCase):
    """The configured backend decides which command applies a wallpaper."""

    def test_awww_sets_only_the_requested_monitors(self):
        calls = []
        with (
            mock.patch.object(
                wallpaper_module, "wallpaper_backend", return_value="awww"
            ),
            mock.patch.object(
                wallpaper_module,
                "_run_async",
                side_effect=lambda argv, _callback: calls.append(argv),
            ),
        ):
            apply_wallpaper("/tmp/a.png", ["DP-1", "HDMI-A-1"])

        self.assertEqual(calls, [["awww", "img", "-o", "DP-1,HDMI-A-1", "/tmp/a.png"]])

    def test_hyprpaper_sets_each_monitor(self):
        calls = []
        with (
            mock.patch.object(
                wallpaper_module, "wallpaper_backend", return_value="hyprpaper"
            ),
            mock.patch.object(
                wallpaper_module,
                "_run_async",
                side_effect=lambda argv, _callback: calls.append(argv),
            ),
        ):
            apply_wallpaper("/tmp/a.png", ["DP-1", "HDMI-A-1"])

        self.assertEqual(
            calls,
            [
                ["hyprctl", "hyprpaper", "wallpaper", "DP-1,/tmp/a.png"],
                ["hyprctl", "hyprpaper", "wallpaper", "HDMI-A-1,/tmp/a.png"],
            ],
        )


if __name__ == "__main__":
    unittest.main()
