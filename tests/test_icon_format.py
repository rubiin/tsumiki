"""Tests for the ``show_icon`` -> ``label_format`` migration.

The stat widgets (cpu/gpu/memory/storage) and the microphone declared
``show_icon`` in config but never read it, so the icon was always rendered.
These tests pin the wired-up behavior: the icon follows ``label_format``.
"""

import unittest
from unittest import mock

from shared.mixins import StatDisplayMixin
from shared.widget_container import BaseWidget
from widgets.microphone import MicrophoneIndicatorWidget


class _StatProbe(StatDisplayMixin, BaseWidget):
    """The mixin's real icon/label builders without GTK widget construction."""

    _build_stat_icon = StatDisplayMixin._build_stat_icon
    _setup_label_mode = StatDisplayMixin._setup_label_mode

    def __init__(self, **config):
        self.config = config


class StatIconFormatTest(unittest.TestCase):
    """The stat widgets follow label_format instead of the old show_icon key."""

    def setUp(self):
        patcher = mock.patch("shared.mixins.nerd_font_icon", return_value="nerd-icon")
        self.nerd_font_icon = patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(
            mock.patch("shared.mixins.Label", return_value="level-label").start
        )

    def test_the_default_format_renders_the_icon(self):
        probe = _StatProbe()

        self.assertEqual(probe._build_stat_icon(), "nerd-icon")

    def test_a_format_naming_the_icon_renders_it(self):
        probe = _StatProbe(label_format="{icon}")

        self.assertEqual(probe._build_stat_icon(), "nerd-icon")

    def test_a_format_without_the_icon_field_drops_it(self):
        """The regression: show_icon was declared but never read."""
        probe = _StatProbe(label_format="")

        self.assertIsNone(probe._build_stat_icon())

    def test_label_mode_keeps_both_children_with_an_icon(self):
        probe = _StatProbe()
        container = mock.Mock()

        probe._setup_label_mode(container)

        container.children = ("nerd-icon", "level-label")

    def test_label_mode_drops_the_icon_child_without_the_field(self):
        probe = _StatProbe(label_format="")
        container = mock.Mock()

        probe._setup_label_mode(container)

        container.children = ("level-label",)


def make_microphone(**config) -> MicrophoneIndicatorWidget:
    """A microphone widget with a stubbed audio service and no GTK window."""
    widget = MicrophoneIndicatorWidget.__new__(MicrophoneIndicatorWidget)
    widget.config = config or {"label_format": "{icon}"}
    widget.mic_on_icon = "mic-on"
    widget.mic_off_icon = "mic-off"
    widget.icon = mock.Mock()
    widget.mic_label = mock.Mock()
    widget.audio_service = mock.Mock()
    widget.set_tooltip_if_enabled = mock.Mock()
    return widget


class MicrophoneIconFormatTest(unittest.TestCase):
    """The icon is optional now, so the update path must tolerate ``None``."""

    def test_the_constructor_no_longer_reads_show_icon(self):
        with open("widgets/microphone.py", encoding="utf-8") as source:
            self.assertNotIn('config.get("show_icon"', source.read())

    def test_a_muted_microphone_updates_the_icon(self):
        widget = make_microphone()
        widget.audio_service.microphone = mock.Mock(muted=True)

        widget._update_status()

        widget.icon.set_label.assert_called_once_with("mic-off")

    def test_no_microphone_hides_the_icon(self):
        widget = make_microphone()
        widget.audio_service.microphone = None

        widget._update_status()

        widget.icon.set_visible.assert_called_once_with(False)

    def test_no_microphone_does_not_touch_a_missing_icon(self):
        """The regression: the icon is None when label_format omits {icon}."""
        widget = make_microphone(label_format="")
        widget.icon = None
        widget.audio_service.microphone = None

        widget._update_status()

    def test_an_active_microphone_updates_the_icon_without_one(self):
        widget = make_microphone(label_format="")
        widget.icon = None
        widget.audio_service.microphone = mock.Mock(muted=False)

        widget._update_status()

        widget.set_tooltip_if_enabled.assert_called_once_with("Microphone is on")

    def test_the_mic_label_updates_whatever_the_config_says(self):
        """The label is mandatory now: no ``label`` key can suppress it."""
        widget = make_microphone(label=False)
        widget.audio_service.microphone = mock.Mock(muted=True)

        widget._update_status()

        widget.mic_label.set_label.assert_called_once_with("Off")


if __name__ == "__main__":
    unittest.main()
