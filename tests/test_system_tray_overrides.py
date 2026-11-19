"""``widgets.system_tray.overrides`` maps glob patterns to icons.

Only the matcher is exercised here: resolving the pixbuf needs a live GTK
theme, while the mapping itself is plain configuration logic.
"""

import unittest

from widgets.system_tray import BaseSystemTray


class _Item:
    def __init__(self, title="", item_id="", identifier="", icon_name=""):
        self.title = title
        self.id = item_id
        self.identifier = identifier
        self.icon_name = icon_name

    def get_property(self, name):
        return self.title if name == "title" else None


def _tray(overrides):
    tray = BaseSystemTray()
    tray.config = {"overrides": overrides}
    return tray


class OverrideMatchingTest(unittest.TestCase):
    """Glob patterns select an icon for matching tray items."""

    def test_glob_matches_the_title_case_insensitively(self):
        tray = _tray({"*discord*": "discord"})
        self.assertEqual(tray._override_icon_name(_Item("Discord Canary")), "discord")

    def test_a_pattern_can_match_the_item_id(self):
        tray = _tray({"spotify*": "spotify"})
        item = _Item(item_id="spotify-client")
        self.assertEqual(tray._override_icon_name(item), "spotify")

    def test_a_pattern_can_match_the_icon_name(self):
        tray = _tray({"*telegram*": "telegram"})
        item = _Item(icon_name="telegram-symbolic")
        self.assertEqual(tray._override_icon_name(item), "telegram")

    def test_the_first_matching_pattern_wins(self):
        tray = _tray({"*discord*": "first", "*canary*": "second"})
        self.assertEqual(tray._override_icon_name(_Item("Discord Canary")), "first")

    def test_unmatched_items_keep_their_own_icon(self):
        tray = _tray({"*discord*": "discord"})
        self.assertIsNone(tray._override_icon_name(_Item("Signal")))

    def test_empty_or_invalid_overrides_are_ignored(self):
        self.assertIsNone(_tray({})._override_icon_name(_Item("Signal")))
        self.assertIsNone(_tray([])._override_icon_name(_Item("Signal")))
        self.assertIsNone(_tray({"*": ""})._override_icon_name(_Item("Signal")))


if __name__ == "__main__":
    unittest.main()
