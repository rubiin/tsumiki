"""Regression tests for bar widget button colours in every bundled theme.

Commit 0355938f stored each widget fill as a mostly-background mixture, which
made buttons look faint and left the text unreadable. Fills must stay close to
the theme palette, every widget must receive a fill, and text must meet WCAG AA
(4.5:1) in every state.

Sass treats underscores in variable names as hyphens, which used to make the
`system_tray`/`window_title`/`date_time` lookups miss their theme colours.
"""

import glob
import json
import os
import re
import shutil
import subprocess
import tomllib
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
THEMES_DIR = os.path.join(ROOT, "themes")
SCHEMA_PATH = os.path.join(ROOT, "tsumiki.schema.json")
WIDGETS_SCSS = os.path.join(ROOT, "styles", "common", "_widgets.scss")
MAIN_SCSS = os.path.join(ROOT, "styles", "main.scss")
MODES = ("dark", "light")
STATES = ("normal", "hover", "active")
MIN_FILL_DISTANCE = 40.0
MIN_CONTRAST = 4.5
# Deliberately dark buttons; identity comes from icon/text colour.
SKIPPED_WIDGETS = {"battery", "weather"}


def _rgb(value):
    return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))


def _is_hex(value):
    # Accept #RRGGBB and #RRGGBBAA; alpha is ignored by the contrast maths.
    return (
        isinstance(value, str)
        and value.startswith("#")
        and len(value) in (7, 9)
    )


def _luminance(value):
    channels = []
    for channel in _rgb(value):
        channel /= 255
        channels.append(
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
        )
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(first, second):
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _distance(first, second):
    return sum((a - b) ** 2 for a, b in zip(_rgb(first), _rgb(second))) ** 0.5


def _themes():
    for path in sorted(glob.glob(os.path.join(THEMES_DIR, "*.toml"))):
        with open(path, "rb") as handle:
            yield os.path.basename(path), tomllib.load(handle)


def _theme_modes():
    for theme, data in _themes():
        for mode in MODES:
            yield theme, mode, data.get(mode, {})


def _widget_cases(states):
    for theme, mode, section in _theme_modes():
        background = section.get("background", {}).get("main")
        if not _is_hex(background):
            continue
        for name, config in section.get("widgets", {}).items():
            if not isinstance(config, dict):
                continue
            for state in states:
                state_config = config if state == "normal" else config.get(state, {})
                if not isinstance(state_config, dict):
                    continue
                fill = state_config.get("background")
                if _is_hex(fill):
                    yield (
                        theme,
                        mode,
                        name,
                        state,
                        background,
                        fill,
                        state_config.get("foreground"),
                    )


def _schema_widget_names():
    with open(SCHEMA_PATH, encoding="utf-8") as handle:
        schema = json.load(handle)
    return set(schema["properties"]["widgets"]["properties"])


def _scss_widget_types():
    with open(WIDGETS_SCSS, encoding="utf-8") as handle:
        source = handle.read()
    block = source.split("$widget-color-types:")[1].split(");")[0]
    return set(re.findall(r'"([a-z0-9_]+)"', block))


class ThemeWidgetColorTest(unittest.TestCase):
    """Every widget must be vivid when idle and readable in every state."""

    def test_widget_fills_are_not_washed_out(self):
        cases = [
            case
            for case in _widget_cases(("normal",))
            if case[2] not in SKIPPED_WIDGETS
        ]
        self.assertTrue(cases, "no widget colours found")

        faint = [
            f"{theme} {mode} {name}: {fill} is {_distance(fill, background):.0f} "
            f"from background {background}"
            for theme, mode, name, _, background, fill, _ in cases
            if _distance(fill, background) < MIN_FILL_DISTANCE
        ]
        self.assertEqual(faint, [], "widget fills blend into the bar background")

    def test_widget_text_is_readable_on_its_fill(self):
        cases = [
            case
            for case in _widget_cases(STATES)
            if _is_hex(case[6])
        ]
        self.assertTrue(cases, "no widget colours found")

        unreadable = [
            f"{theme} {mode} {name}.{state}: {foreground} on {fill} is "
            f"{_contrast(fill, foreground):.2f}:1"
            for theme, mode, name, state, _, fill, foreground in cases
            if _contrast(fill, foreground) < MIN_CONTRAST
        ]
        self.assertEqual(unreadable, [], "widget text fails WCAG AA on its fill")

    def test_every_widget_has_theme_colours(self):
        expected = _schema_widget_names()
        missing = []
        for theme, mode, section in _theme_modes():
            widgets = section.get("widgets", {})
            for name in sorted(expected):
                config = widgets.get(name)
                if not isinstance(config, dict):
                    missing.append(f"{theme} {mode} {name}: no section")
                    continue
                if not _is_hex(config.get("background")):
                    missing.append(f"{theme} {mode} {name}: no background")
                if not _is_hex(config.get("foreground")):
                    missing.append(f"{theme} {mode} {name}: no foreground")
        self.assertEqual(missing, [], "widgets without theme colours")

    def test_scss_styles_every_schema_widget(self):
        missing = _schema_widget_names() - _scss_widget_types()
        self.assertEqual(
            missing, set(), "widget types missing from $widget-color-types"
        )

    def test_compiled_css_gives_every_widget_a_background(self):
        if shutil.which("sass") is None:
            self.skipTest("sass binary not available")

        result = subprocess.run(
            ["sass", MAIN_SCSS, "--no-source-map"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        css = result.stdout

        backgrounds = [
            selector
            for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
            if "background-color" in body
        ]
        missing = [
            name
            for name in sorted(_scss_widget_types())
            if not any(
                re.search(rf"#{re.escape(name)}(?![\w-])", selector)
                for selector in backgrounds
            )
        ]
        self.assertEqual(missing, [], "widgets without a background rule")


if __name__ == "__main__":
    unittest.main()
