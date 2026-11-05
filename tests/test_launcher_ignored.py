"""``modules.launcher.ignored`` keeps configured apps out of the app list.

The key was declared in the schema for a long time, then dropped as inert
because nothing ever read it. This pins the contract it was restored for: an
entry hides an app by desktop file id, name or window class, and the filter
runs where both search and autocomplete read the list (``_all_apps``).
"""

import unittest
from types import SimpleNamespace

from modules.launcher import Launcher, LauncherConfig, _app_ignore_keys


def make_app(
    name: str,
    display_name: str | None = None,
    window_class: str | None = None,
    desktop_id: str | None = "app.desktop",
):
    """A DesktopApp-shaped object; no display or D-Bus session needed."""
    return SimpleNamespace(
        name=name,
        display_name=display_name,
        generic_name=None,
        window_class=window_class,
        _app=SimpleNamespace(get_id=lambda: desktop_id),
    )


class _Probe:
    """``Launcher._load_apps`` without constructing the popup."""

    _load_apps = Launcher._load_apps

    def __init__(self, apps: list, ignored: set[str]):
        self.app_util = SimpleNamespace(all_applications=apps)
        self.config = SimpleNamespace(ignored=ignored)


class LauncherConfigIgnoredTest(unittest.TestCase):
    """``ignored`` is parsed once, up front, and tolerates bad input."""

    def test_entries_are_casefolded(self):
        config = LauncherConfig(
            {"modules": {"launcher": {"ignored": ["Firefox.desktop"]}}}
        )

        self.assertEqual({"firefox.desktop"}, config.ignored)

    def test_a_non_list_value_yields_nothing(self):
        config = LauncherConfig({"modules": {"launcher": {"ignored": "firefox"}}})

        self.assertEqual(set(), config.ignored)

    def test_the_default_is_an_empty_set(self):
        self.assertEqual(set(), LauncherConfig({}).ignored)


class AppIgnoreKeysTest(unittest.TestCase):
    """Every identifier a config may name an app by."""

    def test_the_desktop_id_matches_with_and_without_its_suffix(self):
        keys = _app_ignore_keys(make_app("Firefox", desktop_id="firefox.desktop"))

        self.assertIn("firefox.desktop", keys)
        self.assertIn("firefox", keys)

    def test_name_display_name_and_wm_class_all_count(self):
        app = make_app(
            "KTorrent",
            display_name="KTorrent",
            window_class="org.kde.ktorrent",
            desktop_id=None,
        )

        self.assertEqual({"ktorrent", "org.kde.ktorrent"}, _app_ignore_keys(app))

    def test_an_app_without_a_desktop_id_still_matches_by_name(self):
        self.assertIn("firefox", _app_ignore_keys(make_app("Firefox", desktop_id=None)))

    def test_a_missing_id_object_is_tolerated(self):
        app = SimpleNamespace(name="Firefox", display_name=None, window_class=None)

        self.assertEqual({"firefox"}, _app_ignore_keys(app))


class LoadAppsTest(unittest.TestCase):
    """The filter runs where the list is loaded, so search inherits it."""

    def test_an_ignored_app_is_dropped(self):
        firefox = make_app("Firefox", desktop_id="firefox.desktop")
        ktorrent = make_app("KTorrent", desktop_id="org.kde.ktorrent.desktop")

        apps = _Probe([firefox, ktorrent], {"firefox.desktop"})._load_apps()

        self.assertEqual([ktorrent], apps)

    def test_an_empty_ignore_list_keeps_the_source_list(self):
        firefox = make_app("Firefox", desktop_id="firefox.desktop")
        source = [firefox]

        self.assertIs(source, _Probe(source, set())._load_apps())

    def test_search_and_autocomplete_never_see_an_ignored_app(self):
        firefox = make_app(
            "Firefox", display_name="Firefox", desktop_id="firefox.desktop"
        )
        ktorrent = make_app("KTorrent", display_name="KTorrent")
        launcher = Launcher.__new__(Launcher)
        apps = [firefox, ktorrent]
        launcher._all_apps = _Probe(apps, {"firefox.desktop"})._load_apps()

        self.assertEqual([ktorrent], list(launcher._filter_applications("")))
        self.assertEqual([], list(launcher._filter_applications("fire")))


if __name__ == "__main__":
    unittest.main()
