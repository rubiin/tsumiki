"""Tests for ``widgets/custom_widget.py`` output formatting.

Command output is untrusted text: a percentage icon table arrives in whatever
order the user wrote it, and a tooltip may hold anything the command printed.
"""

import json
import unittest
from unittest import mock

from widgets.custom_widget import CustomWidgetPresenter


def make_presenter(
    *,
    format_icons: dict | None = None,
    tooltip: bool = True,
    tooltip_format: str | None = None,
) -> CustomWidgetPresenter:
    label, icon, host = mock.Mock(), mock.Mock(), mock.Mock()
    module_config: dict = {"label_format": "{}", "tooltip": tooltip}
    if format_icons is not None:
        module_config["format_icons"] = format_icons
    if tooltip_format is not None:
        module_config["tooltip_format"] = tooltip_format
    return CustomWidgetPresenter(
        module_config, label, icon, host
    ), host


class FormatIconThresholdTest(unittest.TestCase):
    """The highest matching threshold wins, not the first one in dict order."""

    def _icon_for(self, format_icons, percentage, alt=None):
        presenter, _ = make_presenter(format_icons=format_icons)
        presenter._update_icon(alt, percentage)
        return presenter._icon.set_label.call_args[0][0] if (
            presenter._icon.set_label.called
        ) else None

    def test_the_highest_matching_threshold_wins(self):
        icons = {"75": "A", "50": "B"}
        self.assertEqual("A", self._icon_for(icons, 80))

    def test_the_matching_threshold_wins_regardless_of_write_order(self):
        icons = {"50": "B", "75": "A"}
        self.assertEqual("A", self._icon_for(icons, 80))

    def test_a_lower_percentage_falls_to_the_lower_threshold(self):
        self.assertEqual("B", self._icon_for({"75": "A", "50": "B"}, 60))

    def test_a_percentage_below_every_threshold_sets_no_icon(self):
        self.assertIsNone(self._icon_for({"75": "A", "50": "B"}, 10))

    def test_an_exact_threshold_matches(self):
        self.assertEqual("A", self._icon_for({"75": "A", "50": "B"}, 75))

    def test_a_named_alt_beats_the_thresholds(self):
        icons = {"75": "A", "50": "B", "muted": "M"}
        self.assertEqual("M", self._icon_for(icons, 80, alt="muted"))

    def test_non_numeric_keys_are_not_thresholds(self):
        icons = {"default": "D", "50": "B"}
        self.assertEqual("B", self._icon_for(icons, 80))

    def test_no_icon_without_a_format_icons_table(self):
        self.assertIsNone(self._icon_for({}, 80))


class TooltipOutputTest(unittest.TestCase):
    """Raw command output is not Pango markup; '&' or '<' empties the tooltip."""

    def test_a_tooltip_is_applied_as_plain_text(self):
        presenter, host = make_presenter()

        presenter._handle_json_output(json.dumps({"text": "80%", "tooltip": "A & B"}))

        host.set_tooltip_text.assert_called_once_with("A & B")
        host.set_tooltip_markup.assert_not_called()

    def test_markup_characters_survive_intact(self):
        presenter, host = make_presenter()

        presenter._handle_json_output(
            json.dumps({"text": "x", "tooltip": "<b>bold</b> & <i>it</i>"})
        )

        host.set_tooltip_text.assert_called_once_with("<b>bold</b> & <i>it</i>")

    def test_the_tooltip_format_still_applies(self):
        presenter, host = make_presenter(tooltip_format="vol: {}")

        presenter._handle_json_output(json.dumps({"text": "x", "tooltip": "50"}))

        host.set_tooltip_text.assert_called_once_with("vol: 50")

    def test_a_disabled_tooltip_sets_nothing(self):
        presenter, host = make_presenter(tooltip=False)

        presenter._handle_json_output(json.dumps({"text": "x", "tooltip": "50"}))

        host.set_tooltip_text.assert_not_called()

    def test_an_absent_tooltip_clears_the_previous_one(self):
        presenter, host = make_presenter()

        presenter._handle_json_output(json.dumps({"text": "x", "tooltip": "50"}))
        presenter._handle_json_output(json.dumps({"text": "y"}))

        host.set_tooltip_text.assert_called_with("")

    def test_plain_output_also_uses_plain_text(self):
        presenter, host = make_presenter()

        presenter._handle_text_output("1 < 2 & 3")

        host.set_tooltip_text.assert_called_once_with("1 < 2 & 3")


if __name__ == "__main__":
    unittest.main()
