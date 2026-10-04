"""Tests for the ``show_icon`` -> ``label_format`` migration.

``show_icon`` was declared in config but never read, so the icon was always
rendered. ``label_format`` replaced it, and the panel content now comes from one
label built by ``format_panel_label``.
"""

import unittest
from unittest import mock

from fabric.widgets.label import Label

from shared.mixins import StatDisplayMixin
from shared.widget_container import ButtonWidget, format_panel_label
from widgets.microphone import MicrophoneIndicatorWidget


class _StatProbe(StatDisplayMixin):
    """StatDisplayMixin without ButtonWidget's GTK construction."""

    _setup_label_mode = StatDisplayMixin._setup_label_mode
    format_shows_icon = ButtonWidget.format_shows_icon

    def __init__(self, *, label_format: str):
        self.config = {"label_format": label_format}
        self._stat_icon = "stat-icon"
        self.level_label = Label()
        self.value_label = Label()
        self.container_box = mock.Mock()


class FormatPanelLabelTest(unittest.TestCase):
    """``{icon}`` is the only field: it takes the widget's glyph."""

    def test_the_icon_field_takes_the_glyph(self):
        self.assertEqual("󰅚 Bluetooth", format_panel_label("{icon} Bluetooth", "󰅚"))

    def test_an_icon_only_format_renders_the_glyph_alone(self):
        self.assertEqual("󰅚", format_panel_label("{icon}", "󰅚"))

    def test_the_default_glyph_is_empty(self):
        self.assertEqual("", format_panel_label("{icon}"))

    def test_whitespace_left_by_a_missing_glyph_is_squeezed(self):
        self.assertEqual("Bluetooth", format_panel_label("{icon} Bluetooth"))

    def test_an_unknown_field_leaves_the_template_alone(self):
        """A bad config must not take the bar down with a KeyError."""
        self.assertEqual("{bogus}", format_panel_label("{bogus}", "X"))


class StatWidgetLabelFormatTest(unittest.TestCase):
    """The stat widgets follow label_format instead of the old show_icon key."""

    def test_label_mode_keeps_both_children_with_an_icon(self):
        container = mock.Mock()
        probe = _StatProbe(label_format="{icon}")

        probe._setup_label_mode(container)

        self.assertEqual(2, len(container.children))

    def test_label_mode_drops_the_icon_child_without_the_field(self):
        container = mock.Mock()
        probe = _StatProbe(label_format="")

        probe._setup_label_mode(container)

        self.assertEqual(1, len(container.children))


def make_microphone(**config) -> MicrophoneIndicatorWidget:
    """A microphone widget with a stubbed audio service and no GTK window."""
    widget = MicrophoneIndicatorWidget.__new__(MicrophoneIndicatorWidget)
    widget.config = config or {"label_format": "{icon} Mic"}
    widget.label_format = widget.config["label_format"]
    widget.mic_on_icon = "mic-on"
    widget.mic_off_icon = "mic-off"
    widget.panel_label = mock.Mock()
    widget.audio_service = mock.Mock()
    widget.set_tooltip_if_enabled = mock.Mock()
    widget.refresh_formatted_label = mock.Mock()
    return widget


class MicrophoneIconFormatTest(unittest.TestCase):
    """The glyph inside the format carries the mute state."""

    def test_the_constructor_no_longer_reads_show_icon(self):
        with open("widgets/microphone.py", encoding="utf-8") as source:
            self.assertNotIn('config.get("show_icon"', source.read())

    def test_a_muted_microphone_renders_the_off_glyph(self):
        widget = make_microphone()
        widget.audio_service.microphone = mock.Mock(muted=True)

        widget._update_status()

        widget.refresh_formatted_label.assert_called_once_with("mic-off")

    def test_an_active_microphone_renders_the_on_glyph(self):
        widget = make_microphone()
        widget.audio_service.microphone = mock.Mock(muted=False)

        widget._update_status()

        widget.refresh_formatted_label.assert_called_once_with("mic-on")

    def test_no_microphone_hides_the_panel_label(self):
        widget = make_microphone()
        widget.audio_service.microphone = None

        widget._update_status()

        widget.panel_label.set_visible.assert_called_once_with(False)

    def test_a_microphone_coming_back_shows_the_label_again(self):
        """The regression: the label stayed hidden after a mic was plugged in."""
        widget = make_microphone()
        widget.audio_service.microphone = mock.Mock(muted=False)

        widget._update_status()

        widget.panel_label.set_visible.assert_called_with(True)


if __name__ == "__main__":
    unittest.main()
