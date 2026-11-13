"""Tests for the matugen SCSS template used for generated colour schemes."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
TEMPLATE = os.path.join(ROOT, "assets", "matugen", "matugen.scss")
SCHEMA = os.path.join(ROOT, "tsumiki.schema.json")
NEUTRAL = {"battery", "weather"}

# Concrete stand-ins for `{{ name }}` values emitted by matugen.
COLOR_STUBS = """
$surface: #1e1e2e;
$surface_container: #181825;
$surface_container_lowest: #11111b;
$surface_container_low: #242323;
$surface_container_high: #313244;
$surface_container_highest: #45475a;
$surface_bright: #585b70;
$on_surface: #cdd6f4;
$on_surface_variant: #bac2de;
$outline: #a6adc8;
$outline_variant: #6c7086;
$primary: #89dceb;
$primary_fixed: #f5e0dc;
$tertiary: #b4befe;
$blue: #89b4fa;
$cyan: #89dceb;
$magenta: #f5c2e7;
$green: #a6e3a1;
$yellow: #f9e2af;
$red: #f38ba8;
$error: #f38ba8;
$shadow: rgba(0, 0, 0, 0.6);
"""


def _template_source():
    with open(TEMPLATE, encoding="utf-8") as handle:
        return handle.read()


def _schema_widget_names():
    with open(SCHEMA, encoding="utf-8") as handle:
        schema = json.load(handle)
    return set(schema["properties"]["widgets"]["properties"])


def _template_widgets():
    pattern = re.compile(r"^\$widgets-([a-z0-9_]+)-background: (.+);$", re.MULTILINE)
    return {name: value for name, value in pattern.findall(_template_source())}


def _rgb(value):
    match = re.match(r"#([0-9a-fA-F]{6})", value.strip())
    if match:
        return tuple(int(match.group(1)[i : i + 2], 16) for i in (0, 2, 4))
    match = re.match(r"rgba?\(([^)]+)\)", value.strip())
    return tuple(float(part) for part in re.split(r"[,\s/]+", match.group(1))[:3])


def _contrast(first, second):
    def luminance(value):
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

    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class MatugenTemplateTest(unittest.TestCase):
    """Generated matugen schemes must give each widget its own readable fill."""
    def test_every_widget_gets_an_accent(self):
        widgets = _template_widgets()
        missing = _schema_widget_names() - set(widgets)
        self.assertEqual(missing, set(), "widgets missing from matugen template")

        neutral = {
            name
            for name, value in widgets.items()
            if name not in NEUTRAL and value.strip() == "$surface-neutral"
        }
        self.assertEqual(neutral, set(), "widgets still sharing the neutral surface")
        self.assertGreater(
            len({value for value in widgets.values()}),
            1,
            "all widgets share a single background",
        )

    def test_generated_colors_are_readable(self):
        if shutil.which("sass") is None:
            self.skipTest("sass binary not available")

        source = re.sub(
            r"<\* for name, value in colors \*>.*?<\* endfor \*>",
            COLOR_STUBS,
            _template_source(),
            flags=re.DOTALL,
        )
        widgets = sorted(_template_widgets())
        probe = "\n".join(
            f".w-{name} {{ background: $widgets-{name}-background; "
            f"color: $widgets-{name}-foreground; }}"
            for name in widgets
        )
        with tempfile.NamedTemporaryFile(
            "w", dir=os.path.join(ROOT, "styles"), suffix=".scss", delete=False
        ) as handle:
            handle.write(source + "\n" + probe + "\n")
            path = handle.name
        try:
            result = subprocess.run(
                ["sass", path, "--no-source-map"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        finally:
            os.unlink(path)

        self.assertEqual(result.returncode, 0, result.stderr)
        rules = {
            name: body
            for name, body in re.findall(r"\.w-([a-z0-9_]+) \{([^}]*)\}", result.stdout)
        }
        self.assertEqual(set(widgets), set(rules))

        unreadable = []
        for name, body in rules.items():
            values = {}
            for line in body.splitlines():
                key, separator, value = line.partition(":")
                if separator:
                    values[key.strip()] = value
            background = values["background"].strip().rstrip(";")
            foreground = values["color"].strip().rstrip(";")
            if _contrast(background, foreground) < 4.5:
                unreadable.append(f"{name}: {foreground} on {background}")
        self.assertEqual(unreadable, [])


if __name__ == "__main__":
    unittest.main()
