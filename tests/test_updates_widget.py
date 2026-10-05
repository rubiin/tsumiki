"""Tests for the ``{total}`` field of the updates widget's ``label_format``.

The label_format refactor dropped the count from the panel label and reduced
the field set to ``{icon}``, so the pre-refactor icon-plus-count layout was no
longer expressible.
"""

import json
import unittest
from unittest import mock

from widgets.updates import UpdatesWidget


def make_widget(**config) -> UpdatesWidget:
    """An UpdatesWidget with stubbed GTK calls and no window."""
    widget = UpdatesWidget.__new__(UpdatesWidget)
    widget.config = {"label_format": "{icon} {total}", **config}
    widget.label_format = widget.config["label_format"]
    widget.set_tooltip_if_enabled = mock.Mock()
    widget.set_visible = mock.Mock()
    widget.is_visible = mock.Mock(return_value=True)
    widget.refresh_formatted_label = mock.Mock()
    return widget


class UpdatesTotalFieldTest(unittest.TestCase):
    """The count rides in ``{total}``, zero-padded unless ``pad_zero`` is off."""

    def test_the_count_is_passed_to_the_label(self):
        widget = make_widget()

        widget._update_values(json.dumps({"total": 3}))

        args, kwargs = widget.refresh_formatted_label.call_args
        self.assertEqual(widget.config.get("available_icon", "󰏗"), args[0])
        self.assertEqual("03", kwargs["total"])

    def test_pad_zero_off_renders_a_bare_number(self):
        widget = make_widget(pad_zero=False)

        widget._update_values(json.dumps({"total": 3}))

        self.assertEqual("3", widget.refresh_formatted_label.call_args[1]["total"])

    def test_zero_stays_unpadded(self):
        widget = make_widget()

        widget._update_values(json.dumps({"total": 0}))

        self.assertEqual("0", widget.refresh_formatted_label.call_args[1]["total"])

    def test_two_digit_counts_are_left_alone(self):
        widget = make_widget()

        widget._update_values(json.dumps({"total": 12}))

        self.assertEqual("12", widget.refresh_formatted_label.call_args[1]["total"])

    def test_the_icon_switches_on_updates(self):
        widget = make_widget(available_icon="󰏗", no_updates_icon="󰏖")

        widget._update_values(json.dumps({"total": 0}))
        self.assertEqual("󰏖", widget.refresh_formatted_label.call_args[0][0])

        widget._update_values(json.dumps({"total": 2}))
        self.assertEqual("󰏗", widget.refresh_formatted_label.call_args[0][0])

    def test_a_broken_payload_leaves_the_label_alone(self):
        widget = make_widget()

        widget._update_values("not json")

        widget.refresh_formatted_label.assert_not_called()


if __name__ == "__main__":
    unittest.main()
