"""Tests for the hyprsunset command flags."""

import unittest

from widgets.hyprsunset import _command_args


class HyprSunsetCommandTest(unittest.TestCase):
    """Only non-default values should add flags to the command."""

    def test_temperature_only(self):
        self.assertEqual("-t 2800k", _command_args("2800k", 100))

    def test_gamma_flag_is_added(self):
        self.assertEqual("-t 2800k -g 120", _command_args("2800k", 120))

    def test_zero_gamma_is_passed(self):
        self.assertEqual("-t 6500 -g 0", _command_args("6500", 0))
