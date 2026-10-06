"""Tests for the ``show_icon`` -> ``label_format`` migration.

``show_icon`` was declared in config but never read, so the icon was always
rendered. ``label_format`` replaced it, and the panel content now comes from one
label built by ``format_panel_label``.
"""

import re
import unittest
from pathlib import Path
from unittest import mock

from fabric.widgets.label import Label

from shared.mixins import StatDisplayMixin
from shared.widget_container import format_panel_label
from widgets.microphone import MicrophoneIndicatorWidget


class _StatProbe(StatDisplayMixin):
    """StatDisplayMixin without ButtonWidget's GTK construction."""

    _setup_label_mode = StatDisplayMixin._setup_label_mode

    def __init__(self, *, label_format: str):
        self.config = {"label_format": label_format}
        self._stat_icon = "stat-icon"
        self.level_label = Label()
        self.value_label = Label()
        self.container_box = mock.Mock()


class FormatPanelLabelTest(unittest.TestCase):
    """The glyph leads the label; a fixed icon lives in the format string."""

    def test_the_glyph_leads_the_formatted_text(self):
        self.assertEqual("󰅚 Bluetooth", format_panel_label("Bluetooth", "󰅚"))

    def test_an_empty_format_renders_the_glyph_alone(self):
        self.assertEqual("󰅚", format_panel_label("", "󰅚"))

    def test_the_default_glyph_is_empty(self):
        self.assertEqual("", format_panel_label(""))

    def test_whitespace_left_by_a_missing_glyph_is_squeezed(self):
        self.assertEqual("Bluetooth", format_panel_label("Bluetooth"))

    def test_an_unknown_field_leaves_the_template_alone(self):
        """A bad config must not take the bar down with a KeyError."""
        self.assertEqual("{bogus}", format_panel_label("{bogus}"))
        self.assertEqual("X {bogus}", format_panel_label("{bogus}", "X"))

    def test_the_icon_field_is_gone(self):
        """A fixed icon is written into the format; nothing substitutes ``{icon}``."""
        self.assertEqual("{icon} Bluetooth", format_panel_label("{icon} Bluetooth"))


class StatWidgetLabelFormatTest(unittest.TestCase):
    """A stat widget's ``label_format`` is the glyph: there is no other field."""

    def test_label_mode_keeps_both_children_with_a_glyph(self):
        container = mock.Mock()
        probe = _StatProbe(label_format="stat-glyph")

        probe._setup_label_mode(container)

        self.assertEqual(2, len(container.children))

    def test_label_mode_drops_the_glyph_child_when_the_format_is_empty(self):
        container = mock.Mock()
        probe = _StatProbe(label_format="")

        probe._setup_label_mode(container)

        self.assertEqual(1, len(container.children))


def make_microphone(**config) -> MicrophoneIndicatorWidget:
    """A microphone widget with a stubbed audio service and no GTK window."""
    widget = MicrophoneIndicatorWidget.__new__(MicrophoneIndicatorWidget)
    widget.config = config or {"label_format": "Mic"}
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

        widget.refresh_formatted_label.assert_called_once_with(
            "mic-off", state="muted"
        )

    def test_an_active_microphone_renders_the_on_glyph(self):
        widget = make_microphone()
        widget.audio_service.microphone = mock.Mock(muted=False)

        widget._update_status()

        widget.refresh_formatted_label.assert_called_once_with("mic-on", state="on")

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


# ``add_formatted_label``'s own definition, and github_tray re-parenting the
# formatted label into a box so its badge can overlap it.
_LABEL_FORMAT_EXEMPT = {
    "shared/widget_container.py",
    "widgets/github_tray/widget.py",
}

# The widgets that used to append a sibling text label next to the formatted one.
_SIBLING_LABEL_WIDGETS = {
    "shared/button_toggle.py": ("label_text", "{state}"),
    "widgets/keyboard_layout.py": ("kb_label", "{layout}"),
    "widgets/submap.py": ("submap_label", "{submap}"),
    "widgets/language.py": ("self.container_box.add", "{language}"),
}


def _widget_sources() -> list[Path]:
    root = Path(__file__).resolve().parents[1]
    return sorted(root.glob("widgets/**/*.py")) + sorted(root.glob("shared/**/*.py"))


class SinglePanelLabelTest(unittest.TestCase):
    """``add_formatted_label`` owns the panel label; no widget adds a sibling.

    A second label means two children in the bar button, and the text escapes
    ``label_format``, so it cannot be restyled or hidden through config.
    """

    def _offenders(self) -> list[str]:
        root = Path(__file__).resolve().parents[1]
        offenders = []
        for path in _widget_sources():
            # Split per class: a popover row class may add its own label.
            for chunk in re.split(r"(?m)^class ", path.read_text(encoding="utf-8")):
                if "add_formatted_label(" not in chunk:
                    continue
                if "container_box.add(" not in chunk:
                    continue
                name = f"{path.relative_to(root)}: {chunk.splitlines()[0]}"
                if name.split(":")[0] not in _LABEL_FORMAT_EXEMPT:
                    offenders.append(name)
        return offenders

    def test_no_widget_adds_a_label_next_to_the_formatted_one(self):
        self.assertEqual([], self._offenders())

    def test_each_refactored_widget_feeds_its_text_back_through_the_format(self):
        root = Path(__file__).resolve().parents[1]
        for name, (gone, field) in _SIBLING_LABEL_WIDGETS.items():
            with self.subTest(widget=name):
                source = (root / name).read_text(encoding="utf-8")
                self.assertNotIn(gone, source)
                self.assertIn(field, source)


if __name__ == "__main__":
    unittest.main()
