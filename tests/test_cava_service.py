import unittest
from unittest import mock

from services.cava import CavaService
from utils.constants import BAR_GLYPHS
from widgets.cava import bars_to_glyphs

BARS = 64


def _make_service() -> CavaService:
    # Bypass __init__: it probes PATH and would otherwise be a singleton.
    service = CavaService.__new__(CavaService)
    service._wanted_by = set()
    service._process = None
    service._config = {}
    service._bar_count = BARS
    service.start = mock.Mock()
    service.stop = mock.Mock()
    return service


class BarsToGlyphsTest(unittest.TestCase):
    """Levels map onto the block-character ramp without going out of range."""

    def test_zero_renders_the_lowest_glyph(self):
        self.assertEqual(bars_to_glyphs([0.0] * 3), BAR_GLYPHS[0] * 3)

    def test_full_level_renders_the_highest_glyph(self):
        self.assertEqual(bars_to_glyphs([1.0]), BAR_GLYPHS[-1])

    def test_out_of_range_values_clamp(self):
        self.assertEqual(bars_to_glyphs([2.0]), BAR_GLYPHS[-1])

    def test_each_value_maps_to_its_own_glyph(self):
        rendered = bars_to_glyphs([0.0, 0.5, 1.0])
        self.assertEqual(len(rendered), 3)
        self.assertLess(BAR_GLYPHS.index(rendered[0]), BAR_GLYPHS.index(rendered[2]))


class SetWantedTest(unittest.TestCase):
    """cava runs only while at least one consumer wants levels."""

    def test_first_owner_starts_cava(self):
        service = _make_service()

        service.set_wanted("widget", True)

        service.start.assert_called_once()
        service.stop.assert_not_called()

    def test_the_first_owner_config_is_passed_to_cava(self):
        service = _make_service()
        config = {"bars": 10, "framerate": 60}

        service.set_wanted("widget", True, config)

        service.start.assert_called_once_with(config)

    def test_a_second_owner_does_not_start_a_second_process(self):
        service = _make_service()
        service._process = mock.Mock()  # already running

        service.set_wanted("other", True)

        service.start.assert_not_called()

    def test_cava_stops_only_after_the_last_owner_leaves(self):
        service = _make_service()
        service._process = mock.Mock()
        service._wanted_by = {"one", "two"}

        service.set_wanted("one", False)
        service.stop.assert_not_called()

        service.set_wanted("two", False)
        service.stop.assert_called_once()


class MakeConfigTest(unittest.TestCase):
    """The generated file must use the names cava actually reads."""

    def test_defaults_produce_a_parseable_config(self):
        service = _make_service()

        text = service.make_config(
            bars=10,
            framerate=60,
            noise_reduction=77,
            bar_width=2,
            bar_gap=1,
            high_cutoff=10000,
            low_cutoff=50,
            source="auto",
            input="pipewire",
            monstercat=0,
        )

        self.assertIn("bars = 10", text)
        self.assertIn("framerate = 60", text)
        self.assertIn("bar_spacing = 1", text)
        self.assertIn("lower_cutoff_freq = 50", text)
        self.assertIn("higher_cutoff_freq = 10000", text)
        self.assertIn("source = auto", text)
        self.assertIn("method = pipewire", text)
        self.assertIn("noise_reduction = 77", text)
        self.assertIn("monstercat = 0", text)


class ParseLineTest(unittest.TestCase):
    """Raw frames are normalised to one 0.0-1.0 float per bar."""

    def test_line_is_normalised_to_zero_one(self):
        service = _make_service()
        line = ";".join(["0"] + ["500"] * (BARS - 2) + ["1000"])

        bars = service._parse_line(line)

        self.assertEqual(len(bars), BARS)
        self.assertEqual(bars[0], 0.0)
        self.assertEqual(bars[1], 0.5)
        self.assertEqual(bars[-1], 1.0)

    def test_short_line_is_ignored(self):
        service = _make_service()

        self.assertIsNone(service._parse_line("0;1;2"))

    def test_non_numeric_line_is_ignored(self):
        service = _make_service()

        self.assertIsNone(service._parse_line("x;" * BARS))


if __name__ == "__main__":
    unittest.main()
