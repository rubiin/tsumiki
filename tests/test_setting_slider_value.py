"""Tests for the value readout shown next to quick settings sliders."""

import unittest
from unittest import mock

from shared.setting_scale import SettingSlider


class SettingSliderValueLabelTest(unittest.TestCase):
    """The readout mirrors the scale value, rounded to whole percent."""

    def setUp(self):
        self.slider = SettingSlider.__new__(SettingSlider)
        self.slider.value_label = mock.Mock()

    def test_value_is_rounded_and_shown_as_a_percentage(self):
        self.slider.set_value_label(42.6)

        self.slider.value_label.set_label.assert_called_once_with("43%")

    def test_overamplified_volume_is_kept(self):
        self.slider.set_value_label(150)

        self.slider.value_label.set_label.assert_called_once_with("150%")
