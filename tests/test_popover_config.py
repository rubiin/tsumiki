"""``[general.popover]`` options: defaults, overrides, and popover wiring."""

import unittest
from unittest import mock
from unittest.mock import patch

from shared import popover


class PopoverOptionsTest(unittest.TestCase):
    """The config section merges over the built-in defaults."""

    def _options(self, general):
        with patch("utils.config.tsumiki_config", {"general": general}):
            return popover.popover_options()

    def test_missing_section_uses_defaults(self):
        self.assertEqual(
            popover.POPOVER_OPTION_DEFAULTS, self._options({"tooltips": True})
        )

    def test_partial_section_keeps_other_defaults(self):
        options = self._options({"popover": {"animation": False, "close_delay": 350}})

        self.assertFalse(options["animation"])
        self.assertEqual(350, options["close_delay"])
        self.assertTrue(options["close_on_escape"])
        self.assertTrue(options["bezel"])

    def test_unknown_keys_are_ignored(self):
        options = self._options({"popover": {"nonsense": 1}})

        self.assertNotIn("nonsense", options)

    def test_non_dict_section_falls_back(self):
        self.assertEqual(popover.POPOVER_OPTION_DEFAULTS, self._options({"popover": 3}))


class ResolveTransitionTest(unittest.TestCase):
    """``auto`` defers to the opening edge; no animation forces ``none``."""

    def test_auto_derives_from_the_edge(self):
        self.assertIsNone(popover.resolve_transition("auto", True))

    def test_unset_derives_from_the_edge(self):
        self.assertIsNone(popover.resolve_transition(None, True))
        self.assertIsNone(popover.resolve_transition("", True))

    def test_explicit_transition_is_kept(self):
        self.assertEqual("slide-up", popover.resolve_transition("slide-up", True))

    def test_disabled_animation_forces_none(self):
        self.assertEqual("none", popover.resolve_transition("slide-up", False))
        self.assertEqual("none", popover.resolve_transition("auto", False))


class CoerceNonNegativeTest(unittest.TestCase):
    """Numeric options (bezel size, close delay) clamp at zero."""

    def test_numbers_pass_through(self):
        self.assertEqual(12, popover.coerce_non_negative(12, 20))
        self.assertEqual(24, popover.coerce_non_negative("24", 20))

    def test_negative_clamps_to_zero(self):
        self.assertEqual(0, popover.coerce_non_negative(-5, 20))

    def test_invalid_falls_back_to_default(self):
        self.assertEqual(20, popover.coerce_non_negative(None, 20))


class PopoverWiringTest(unittest.TestCase):
    """The options must reach the instance, not just the helper."""

    def _make(self, **overrides):
        options = {**popover.POPOVER_OPTION_DEFAULTS, **overrides}
        with patch.object(popover, "popover_options", return_value=options):
            return popover.Popover(point_to=None)

    def test_options_are_read(self):
        instance = self._make(
            animation=False,
            close_on_escape=False,
            close_delay=350,
            bezel=False,
            bezel_size=12,
        )

        self.assertFalse(instance._animate)
        self.assertFalse(instance._close_on_escape)
        self.assertEqual(350, instance._close_delay)
        self.assertFalse(instance._bezel)
        self.assertEqual(12, instance._bezel_size)
        self.assertEqual("none", instance._transition_type)
        self.assertEqual(0, instance._transition_duration)

    def test_focus_out_honours_close_delay(self):
        instance = self._make(close_delay=350)

        with patch.object(popover.GLib, "timeout_add", return_value=7) as timeout:
            instance.on_popover_focus_out(None, None)

        timeout.assert_called_once_with(350, instance._hide_after_focus_out)

    def test_escape_closes_only_when_enabled(self):
        instance = self._make(close_on_escape=False)
        active = mock.Mock()
        instance._manager = mock.Mock(active_popover=active)
        event = mock.Mock(keyval=popover.Gdk.KEY_Escape)

        self.assertFalse(instance.on_key_press(None, event))
        active.hide_popover.assert_not_called()

    def test_escape_closes_when_enabled(self):
        instance = self._make(close_on_escape=True)
        active = mock.Mock()
        instance._manager = mock.Mock(active_popover=active)
        event = mock.Mock(keyval=popover.Gdk.KEY_Escape)

        self.assertTrue(instance.on_key_press(None, event))
        active.hide_popover.assert_called_once_with()

    def test_attachment_is_round_without_bezels(self):
        instance = self._make(bezel=False)
        instance._content_box = mock.Mock()

        instance._set_attachment(opens_upward=False)

        instance._content_box.add_style_class.assert_called_once_with(
            "popover-no-bezel"
        )

    def test_attachment_squares_the_bar_edge_with_bezels(self):
        instance = self._make(bezel=True)
        instance._content_box = mock.Mock()
        instance._corner_left = mock.Mock()
        instance._corner_right = mock.Mock()

        instance._set_attachment(opens_upward=False)

        # Only the attached class is added; the rounded-corner class is not.
        instance._content_box.add_style_class.assert_called_once_with(
            "popover-attached-top"
        )


if __name__ == "__main__":
    unittest.main()
