"""The cookie clock face redraws its silhouette on every tick.

The outline is a pure function of the radius, so it is built once and cached;
these tests keep the cache honest and the rendered pixels unchanged. The date
bubbles fade in on first map, so the fade ramp is covered without a display.
"""

import math
import unittest
from unittest import mock

import cairo

from modules.desktop_clock import CookieClockFace

_RADIUS = 115.0
_POINTS = 360


class _FaceProbe:
    """The silhouette builders on a plain object; no display, no Gtk init."""

    _cookie_path = CookieClockFace._cookie_path
    _build_cookie_path = CookieClockFace._build_cookie_path
    _draw_cookie_shape = CookieClockFace._draw_cookie_shape
    _draw_dial_marks = CookieClockFace._draw_dial_marks

    def __init__(self, sides=9, dial_style="full", widget_scale=1.0):
        self.sides = sides
        self.dial_style = dial_style
        self.widget_scale = widget_scale
        self._cookie_paths: dict = {}
        self.col_on_background = (1.0, 1.0, 1.0, 1.0)


def _reference_surface(cx, cy, radius, sides=9):
    """The pre-cache construction, as the draw pass used to do it."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 260, 260)
    cr = cairo.Context(surface)
    amplitude = radius / 24
    for index in range(_POINTS + 1):
        angle = (2 * math.pi * index) / _POINTS
        wave = math.sin(angle * sides + math.pi / 2) * amplitude
        point_radius = (radius - amplitude) + wave
        x = cx + point_radius * math.cos(angle)
        y = cy + point_radius * math.sin(angle)
        (cr.move_to if index == 0 else cr.line_to)(x, y)
    cr.close_path()
    cr.set_source_rgba(0.1, 0.2, 0.3, 1.0)
    cr.fill()
    surface.flush()
    return bytes(surface.get_data())


def _cached_surface(probe, cx, cy, radius):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 260, 260)
    cr = cairo.Context(surface)
    probe._draw_cookie_shape(cr, cx, cy, radius)
    cr.set_source_rgba(0.1, 0.2, 0.3, 1.0)
    cr.fill()
    surface.flush()
    return bytes(surface.get_data())


class CookiePathCacheTests(unittest.TestCase):
    """One build per radius, and the same pixels as before."""

    def test_the_silhouette_is_built_once_per_radius(self):
        probe = _FaceProbe()
        with mock.patch.object(
            probe,
            "_build_cookie_path",
            wraps=probe._build_cookie_path,
        ) as build:
            first = probe._cookie_path(_RADIUS)
            second = probe._cookie_path(_RADIUS)

        self.assertEqual(1, build.call_count)
        self.assertIs(first, second)
        self.assertEqual([_RADIUS], list(probe._cookie_paths))

    def test_a_different_radius_gets_its_own_path(self):
        probe = _FaceProbe()

        probe._cookie_path(_RADIUS)
        probe._cookie_path(_RADIUS * 0.5)

        self.assertEqual([_RADIUS, _RADIUS * 0.5], list(probe._cookie_paths))

    def test_the_filled_silhouette_is_unchanged(self):
        """The face, and each of the three shadow offsets, must look the same."""
        probe = _FaceProbe()

        for cx, cy in ((130.0, 130.0), (131.0, 131.0), (132.0, 132.0), (133.0, 133.0)):
            with self.subTest(offset=(cx, cy)):
                self.assertEqual(
                    _reference_surface(cx, cy, _RADIUS),
                    _cached_surface(probe, cx, cy, _RADIUS),
                )

    def test_a_fractional_radius_still_matches(self):
        probe = _FaceProbe()
        radius = 230 * 0.75 / 2

        self.assertEqual(
            _reference_surface(130.0, 130.0, radius),
            _cached_surface(probe, 130.0, 130.0, radius),
        )

    def test_a_scaled_face_still_matches(self):
        probe = _FaceProbe(sides=6, widget_scale=1.5)
        radius = 230 * 1.5 / 2

        self.assertEqual(
            _reference_surface(130.0, 130.0, radius, sides=6),
            _cached_surface(probe, 130.0, 130.0, radius),
        )


class _BadgeProbe:
    """The fade ramp on a plain object; no display, no Gtk init."""

    _draw_badge = CookieClockFace._draw_badge
    _advance_badge_fade = CookieClockFace._advance_badge_fade

    def __init__(self, alpha=1.0):
        self._badge_alpha = alpha
        self._badge_fade_started = 0.0
        self._badge_fading = True
        self.draws = 0

    def queue_draw(self):
        self.draws += 1


class BadgeFadeTests(unittest.TestCase):
    """The bubbles fade in, and the ramp stops at full opacity."""

    def test_bubble_and_glyph_alpha_follow_the_fade(self):
        probe = _BadgeProbe(alpha=0.25)
        cr = mock.Mock()
        cr.text_extents.return_value = mock.Mock(
            width=6.0, height=8.0, x_bearing=0.0, y_bearing=0.0
        )

        probe._draw_badge(cr, 10.0, 10.0, 5.0, (0.2, 0.3, 0.4, 0.8), "7", 12)

        cr.set_source_rgba.assert_any_call(0.2, 0.3, 0.4, 0.2)
        cr.set_source_rgba.assert_any_call(1, 1, 1, 0.25)

    def test_the_ramp_keeps_ticking_halfway(self):
        probe = _BadgeProbe(alpha=0.0)

        with mock.patch("modules.desktop_clock.monotonic", return_value=0.05):
            self.assertTrue(probe._advance_badge_fade())

        self.assertTrue(0.0 < probe._badge_alpha < 1.0)
        self.assertTrue(probe._badge_fading)
        self.assertEqual(1, probe.draws)

    def test_the_ramp_settles_at_full_opacity_and_stops(self):
        probe = _BadgeProbe(alpha=0.0)

        with mock.patch("modules.desktop_clock.monotonic", return_value=1.0):
            self.assertFalse(probe._advance_badge_fade())

        self.assertEqual(1.0, probe._badge_alpha)
        self.assertFalse(probe._badge_fading)
        self.assertEqual(1, probe.draws)


class DialMarkLineCapTests(unittest.TestCase):
    """``set_line_cap`` is a constant, so it is set once per dial, not 60 times."""

    def test_the_line_cap_is_set_outside_the_tick_loop(self):
        probe = _FaceProbe()
        cr = mock.Mock()

        probe._draw_dial_marks(cr, 130.0, 130.0, _RADIUS)

        self.assertEqual(1, cr.set_line_cap.call_count)
        self.assertEqual(60, cr.stroke.call_count)

    def test_the_dot_dial_never_touches_the_line_cap(self):
        probe = _FaceProbe(dial_style="dots")
        cr = mock.Mock()

        probe._draw_dial_marks(cr, 130.0, 130.0, _RADIUS)

        cr.set_line_cap.assert_not_called()
        self.assertEqual(12, cr.fill.call_count)


if __name__ == "__main__":
    unittest.main()
