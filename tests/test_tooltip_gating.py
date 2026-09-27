"""Tests for tooltip gating behind the global ``general.tooltips`` switch.

Widgets that called ``set_tooltip_text`` on every user interaction ignored
``general.tooltips = false`` entirely, so the value readouts (volume, mic,
brightness, colour temperature) still popped tooltips with tooltips switched
off everywhere else.
"""

import unittest
from unittest import mock

from shared.setting_scale import SettingSlider
from shared.widget_container import tooltips_enabled


class _Probe:
    """The smallest BaseWidget-shaped object the helpers can drive."""

    def __init__(self, *, tooltips: bool, config: dict | None = None):
        self.tooltips_enabled = tooltips
        self.config = {} if config is None else config
        self.tooltip_text: str | None = None

    def set_tooltip_text(self, text):
        self.tooltip_text = text


class GlobalTooltipSwitchTest(unittest.TestCase):
    """``tooltips_enabled()`` reads the one switch every tooltip must honour."""

    def _with_config(self, general: dict):
        with mock.patch("utils.config.tsumiki_config", {"general": general}):
            return tooltips_enabled()

    def test_tooltips_are_on_by_default(self):
        self.assertTrue(self._with_config({}))

    def test_switching_them_off_is_visible(self):
        self.assertFalse(self._with_config({"tooltips": False}))


class ScaleTooltipGateTest(unittest.TestCase):
    """``SettingSlider.set_scale_tooltip`` keeps the value readout quiet."""

    def setUp(self):
        self.slider = SettingSlider.__new__(SettingSlider)
        self.slider.scale = mock.Mock()

    def test_the_readout_is_written_when_tooltips_are_enabled(self):
        self.slider.tooltips_enabled = True

        self.slider.set_scale_tooltip("42%")

        self.slider.scale.set_tooltip_text.assert_called_once_with("42%")

    def test_the_readout_is_suppressed_when_tooltips_are_off(self):
        """The regression: the scale tooltip ignored the global switch."""
        self.slider.tooltips_enabled = False

        self.slider.set_scale_tooltip("42%")

        self.slider.scale.set_tooltip_text.assert_not_called()


class BaseWidgetTooltipGateTest(unittest.TestCase):
    """``set_tooltip_if_enabled`` honours both the widget and the global flag."""

    def _set(self, tooltip: _Probe, text: str, default: bool = False) -> None:
        # The helper lives on BaseWidget; bind it to a probe without a widget.
        from shared.widget_container import BaseWidget

        BaseWidget.set_tooltip_if_enabled(tooltip, text, default)

    def test_a_widget_with_tooltips_on_writes_the_text(self):
        probe = _Probe(tooltips=True, config={"tooltip": True})

        self._set(probe, "USB Manager (2)")

        self.assertEqual("USB Manager (2)", probe.tooltip_text)

    def test_the_global_switch_suppresses_the_text(self):
        probe = _Probe(tooltips=False, config={"tooltip": True})

        self._set(probe, "USB Manager (2)")

        self.assertIsNone(probe.tooltip_text)

    def test_the_widget_flag_wins_when_tooltips_are_globally_on(self):
        probe = _Probe(tooltips=True, config={"tooltip": False})

        self._set(probe, "USB Manager (2)")

        self.assertIsNone(probe.tooltip_text)

    def test_the_default_argument_covers_an_absent_widget_flag(self):
        probe = _Probe(tooltips=True, config={})

        self._set(probe, "USB Manager", default=True)

        self.assertEqual("USB Manager", probe.tooltip_text)


if __name__ == "__main__":
    unittest.main()
