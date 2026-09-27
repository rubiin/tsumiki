"""Tests for the launcher's selectable row builder and its search scoring.

A command row and a plugin-result row are the same widget tree with different
content, so these assert the parts that still differ: the item name, whether
the title is ellipsized, and what a click does. The scoring tests pin down that
searching works at all: the scorer is TTL-cached, and a cache key that included
the app object made every non-empty query raise. The GTK classes are mocked
because real construction needs a display.
"""

import functools
import sys
import unittest
from itertools import count
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fabric.utils import DesktopApp

from modules import launcher as launcher_module
from modules.launcher import Launcher, _score_app_match
from utils.plugin_manager import PluginResult

# The TTL cache is process-wide and never cleared, so keys must be unique.
_unique = count()


def make_desktop_app(
    name: str = "Firefox",
    display_name: str | None = "Firefox",
    generic_name: str | None = "Web Browser",
) -> DesktopApp:
    """A real DesktopApp without needing a display or a D-Bus session."""
    app = DesktopApp.__new__(DesktopApp)
    app.name = name
    app.display_name = display_name
    app.generic_name = generic_name
    return app


class Recorder:
    """Captures the widget tree a builder produces, without GTK."""

    def __init__(self):
        self.built: list[tuple[str, dict, mock.Mock]] = []

    def __call__(self, cls_name: str, **kwargs):
        # no Mock(name=...): a Box carries its own "name" kwarg
        widget = mock.Mock(**kwargs)
        self.built.append((cls_name, kwargs, widget))
        return widget

    def of(self, cls_name: str) -> list[dict]:
        return [kw for name, kw, _ in self.built if name == cls_name]

    def instance(self, cls_name: str, index: int = 0) -> mock.Mock:
        return [w for n, _, w in self.built if n == cls_name][index]

    def item_name(self) -> str:
        """The item Box is the only one built with a name."""
        return next(kw["name"] for kw in self.of("Box") if "name" in kw)

    def click(self, cls_name: str = "Button", index: int = 0):
        """Fire the handler the widget connected to "clicked"."""
        widget = self.instance(cls_name, index)
        connected = {call[0][0]: call[0][1] for call in widget.connect.call_args_list}
        return connected["clicked"](widget)


def make_launcher(recorder) -> Launcher:
    launcher = Launcher.__new__(Launcher)
    launcher.inserted: list[str] = []
    launcher.executed: list = []
    launcher._insert_command = launcher.inserted.append
    launcher._execute_plugin_result = lambda p, r: launcher.executed.append((p, r))
    launcher._last_icon = None

    def icon_widget(icon):
        launcher._last_icon = icon
        return mock.Mock(name="icon") if icon else None

    launcher._plugin_icon_widget = icon_widget
    return launcher


class SelectableRowTest(unittest.TestCase):
    """What still differs between a command row and a result row."""

    def setUp(self):
        self.recorder = Recorder()
        patches = [
            mock.patch.object(
                launcher_module, cls_name, functools.partial(self.recorder, cls_name)
            )
            for cls_name in ("Box", "Label", "Button")
        ]
        for patcher in patches:
            self.addCleanup(patcher.stop)
            patcher.start()
        self.launcher = make_launcher(self.recorder)
        self.plugin = mock.Mock(name="calc", icon="accessories-calculator-symbolic")
        self.plugin.name = "calc"
        self.plugin.description = "Do sums"

    def test_a_command_row_keeps_its_own_item_name(self):
        self.launcher._create_command_row(self.plugin)

        self.assertEqual("launcher-command-item", self.recorder.item_name())

    def test_a_result_row_keeps_its_own_item_name(self):
        result = PluginResult(title="2 + 2", subtitle="4", icon=None)

        self.launcher._create_plugin_result_row(self.plugin, result)

        self.assertEqual("launcher-plugin-item", self.recorder.item_name())

    def test_a_command_title_is_not_ellipsized(self):
        self.launcher._create_command_row(self.plugin)

        labels = self.recorder.of("Label")
        self.assertEqual("/calc", labels[0]["label"])
        # absent and None both mean Gtk.EllipsizeMode.NONE
        self.assertNotEqual("end", labels[0].get("ellipsization"))

    def test_a_result_title_is_ellipsized(self):
        result = PluginResult(title="a very long song title", subtitle=None, icon=None)

        self.launcher._create_plugin_result_row(self.plugin, result)

        self.assertEqual("end", self.recorder.of("Label")[0]["ellipsization"])

    def test_a_subtitle_adds_a_second_label_in_a_box(self):
        result = PluginResult(title="2 + 2", subtitle="4", icon=None)

        self.launcher._create_plugin_result_row(self.plugin, result)

        labels = self.recorder.of("Label")
        self.assertEqual(["2 + 2", "4"], [kw["label"] for kw in labels])

    def test_no_subtitle_leaves_the_title_unboxed(self):
        result = PluginResult(title="2 + 2", subtitle=None, icon=None)

        self.launcher._create_plugin_result_row(self.plugin, result)

        # Box 0 is the item itself; a title-only row adds no wrapper box.
        self.assertEqual(1, len(self.recorder.of("Box")))

    def test_an_empty_subtitle_is_treated_as_none(self):
        result = PluginResult(title="2 + 2", subtitle="", icon=None)

        self.launcher._create_plugin_result_row(self.plugin, result)

        self.assertEqual(1, len(self.recorder.of("Box")))

    def test_a_command_row_inserts_its_own_name(self):
        self.launcher._create_command_row(self.plugin)

        self.recorder.click()

        self.assertEqual(["calc"], self.launcher.inserted)

    def test_a_result_row_executes_its_own_result(self):
        result = PluginResult(title="2 + 2", subtitle="4", icon=None)

        self.launcher._create_plugin_result_row(self.plugin, result)

        self.recorder.click()

        self.assertEqual([(self.plugin, result)], self.launcher.executed)

    def test_a_result_row_prefers_its_own_icon(self):
        result = PluginResult(title="t", subtitle=None, icon="weather-clear")

        self.launcher._create_plugin_result_row(self.plugin, result)

        # _plugin_icon_widget is stubbed to the icon it was handed
        self.assertEqual("weather-clear", self.launcher._last_icon)

    def test_a_result_row_falls_back_to_the_plugin_icon(self):
        result = PluginResult(title="t", subtitle=None, icon=None)

        self.launcher._create_plugin_result_row(self.plugin, result)

        self.assertEqual("accessories-calculator-symbolic", self.launcher._last_icon)


class AppScoringTest(unittest.TestCase):
    """Scoring an app against a query, which is what renders the result list."""

    def test_the_app_itself_is_unhashable(self):
        # DesktopApp is a dataclass, so __eq__ makes __hash__ None.
        self.assertIsNone(DesktopApp.__hash__)
        with self.assertRaises(TypeError):
            hash(make_desktop_app())

    def test_scoring_a_real_desktop_app_does_not_raise(self):
        app = make_desktop_app()

        score = self.launcher_score(app, "fire")

        self.assertGreater(score, 0)

    def test_filtering_a_non_empty_query_keeps_the_matching_app(self):
        # This raised for every app, so the result list never rendered.
        launcher = Launcher.__new__(Launcher)
        firefox = make_desktop_app()
        gimp = make_desktop_app(
            name="GIMP", display_name="GIMP", generic_name="Image Editor"
        )
        launcher._all_apps = [firefox, gimp]
        launcher._first_app = None

        matched, should_resize = launcher._filter_applications("fire")

        self.assertEqual([firefox], list(matched))
        self.assertFalse(should_resize)

    def test_a_substring_match_beats_a_fuzzy_one(self):
        app = make_desktop_app()

        # "fire" is a prefix of "Firefox"; "ffx" only survives the fuzzy pass.
        self.assertGreater(
            self.launcher_score(app, "fire"), self.launcher_score(app, "ffx")
        )
        self.assertGreater(self.launcher_score(app, "ffx"), 0)

    def test_an_empty_query_scores_nothing(self):
        self.assertEqual(0.0, _score_app_match("", "Firefox", "Firefox", "Web Browser"))
        self.assertEqual(0.0, self.launcher_score(make_desktop_app(), ""))

    def test_an_unrelated_query_scores_nothing(self):
        self.assertEqual(0.0, self.launcher_score(make_desktop_app(), "xyz"))

    def test_apps_sharing_a_name_are_scored_on_their_own_fields(self):
        # A name-only key would collide; the fields are what separate them.
        browser = make_desktop_app(
            name="Claws", display_name="Claws", generic_name="Mail"
        )
        editor = make_desktop_app(
            name="Claws", display_name="Claws", generic_name="Text Editor"
        )

        self.assertGreater(self.launcher_score(editor, "text"), 0)
        self.assertEqual(0.0, self.launcher_score(browser, "text"))

    def test_repeated_scoring_is_served_from_the_cache(self):
        # A unique key so an earlier test cannot have populated the entry.
        query = f"q{next(_unique)}"
        fields = (query, "Firefox", "firefox", "Web Browser")

        with mock.patch.object(
            launcher_module, "SequenceMatcher", wraps=launcher_module.SequenceMatcher
        ) as matcher:
            first = _score_app_match(*fields)
            calls_after_first = matcher.call_count
            second = _score_app_match(*fields)

        self.assertEqual(first, second)
        # "q<unique>" is not a substring, so the first call took the fuzzy path.
        self.assertGreater(calls_after_first, 0)
        self.assertEqual(calls_after_first, matcher.call_count)

    def launcher_score(self, app, query: str) -> float:
        return Launcher._match_score(app, query)


if __name__ == "__main__":
    unittest.main()
