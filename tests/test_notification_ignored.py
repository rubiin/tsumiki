"""Regression tests for the notification app-name ignore list."""

import unittest

from modules.notification import NotificationPopup


class IgnoredAppsTest(unittest.TestCase):
    """``ignored`` entries match as case-insensitive regexes."""

    def _ignored(self, patterns: list[str], app_name: str) -> bool:
        popup = NotificationPopup.__new__(NotificationPopup)
        popup.ignored_apps = patterns
        popup._ignored_patterns = popup._compile_ignored_patterns()
        return popup._is_ignored(app_name)

    def test_exact_name_matches(self):
        self.assertTrue(self._ignored(["spotify"], "spotify"))

    def test_match_ignores_case(self):
        self.assertTrue(self._ignored(["Spotify"], "SPOTIFY"))

    def test_regex_matches(self):
        self.assertTrue(self._ignored(["discord.*"], "discord-canary"))

    def test_unrelated_name_is_allowed(self):
        self.assertFalse(self._ignored(["discord.*"], "telegram"))

    def test_invalid_regex_is_matched_literally(self):
        self.assertTrue(self._ignored(["app("], "app("))

    def test_empty_ignore_list_allows_everything(self):
        self.assertFalse(self._ignored([], "spotify"))

    def test_missing_app_name_is_allowed(self):
        self.assertFalse(self._ignored([".*"], ""))
