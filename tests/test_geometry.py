"""Tests for :mod:`shared.geometry`.

Pure arithmetic plus a handful of cairo calls, so the context is a recorder
rather than a real one. What matters is that the shared path is the same shape
the three widgets each used to build, and that the clamp is applied.
"""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.geometry import (
    fraction_from_position,
    rounded_rect_path,
    value_from_fraction,
)


class FakeContext:
    """Records the path calls a widget would make."""

    def __init__(self):
        self.calls: list[tuple] = []

    def rectangle(self, x, y, w, h):
        self.calls.append(("rectangle", x, y, w, h))

    def new_sub_path(self):
        self.calls.append(("new_sub_path",))

    def arc(self, xc, yc, radius, start, end):
        self.calls.append(("arc", xc, yc, radius, start, end))

    def close_path(self):
        self.calls.append(("close_path",))

    def arcs(self):
        return [c for c in self.calls if c[0] == "arc"]


class RoundedRectPathTests(unittest.TestCase):
    """The path the clipping box and both sliders each used to spell out."""

    def test_a_rounded_rect_is_four_arcs_between_the_corners(self):
        cr = FakeContext()

        rounded_rect_path(cr, 10, 20, 100, 50, 8)

        self.assertEqual(
            ["new_sub_path", "arc", "arc", "arc", "arc", "close_path"],
            [c[0] for c in cr.calls],
        )
        # centres are the four corners inset by the radius
        self.assertEqual(
            [(102, 28), (102, 62), (18, 62), (18, 28)],
            [(a[1], a[2]) for a in cr.arcs()],
        )
        for arc in cr.arcs():
            self.assertEqual(8, arc[3])

    def test_the_arcs_sweep_the_four_corners_in_order(self):
        cr = FakeContext()

        rounded_rect_path(cr, 0, 0, 40, 40, 4)

        # ("arc", xc, yc, radius, start, end) - one quarter turn each
        self.assertEqual(
            [-math.pi / 2, 0, math.pi / 2, math.pi],
            [a[4] for a in cr.arcs()],
        )

    def test_a_zero_radius_is_a_plain_rectangle(self):
        cr = FakeContext()

        rounded_rect_path(cr, 1, 2, 30, 40, 0)

        self.assertEqual([("rectangle", 1, 2, 30, 40)], cr.calls)

    def test_a_negative_radius_is_a_plain_rectangle(self):
        cr = FakeContext()

        rounded_rect_path(cr, 1, 2, 30, 40, -5)

        self.assertEqual([("rectangle", 1, 2, 30, 40)], cr.calls)

    def test_an_oversized_radius_is_clamped_to_the_shorter_side(self):
        """Without the clamp cairo draws a self-intersecting path rather than a
        rounded one - the labelled slider clamped, the sinewave one did not."""
        cr = FakeContext()

        rounded_rect_path(cr, 0, 0, 100, 20, 500)

        for arc in cr.arcs():
            self.assertEqual(10, arc[3])

    def test_the_clamp_uses_half_of_the_shorter_side(self):
        cr = FakeContext()

        rounded_rect_path(cr, 0, 0, 100, 60, 1000)

        self.assertEqual({30}, {a[3] for a in cr.arcs()})

    def test_a_radius_inside_the_clamp_is_left_alone(self):
        cr = FakeContext()

        rounded_rect_path(cr, 0, 0, 100, 60, 12)

        self.assertEqual({12}, {a[3] for a in cr.arcs()})


class FractionFromPositionTests(unittest.TestCase):
    """Clamp-and-scale, shared by both sliders' pointer mapping."""

    def test_the_centre_of_the_track_is_one_half(self):
        self.assertEqual(0.5, fraction_from_position(100, 200, 0))

    def test_the_inset_ends_map_to_zero_and_one(self):
        self.assertEqual(0.0, fraction_from_position(10, 200, 10))
        self.assertEqual(1.0, fraction_from_position(190, 200, 10))

    def test_before_the_track_clamps_to_zero(self):
        self.assertEqual(0.0, fraction_from_position(-40, 200, 10))

    def test_past_the_track_clamps_to_one(self):
        self.assertEqual(1.0, fraction_from_position(9999, 200, 10))

    def test_a_collapsed_widget_does_not_divide_by_zero(self):
        """A zero-width slider must give a usable number, not ZeroDivisionError.
        With no track to travel, any point at or past the origin reads as full."""
        self.assertEqual(1.0, fraction_from_position(5, 0, 0))
        self.assertEqual(0.0, fraction_from_position(-5, 0, 0))

    def test_an_inset_wider_than_the_widget_does_not_divide_by_zero(self):
        self.assertEqual(0.0, fraction_from_position(5, 4, 10))


class ValueFromFractionTests(unittest.TestCase):
    """Scaling a fraction onto a value range."""

    def test_the_ends_of_the_range(self):
        self.assertEqual(0, value_from_fraction(0.0, 0, 100))
        self.assertEqual(100, value_from_fraction(1.0, 0, 100))

    def test_the_middle_of_the_range(self):
        self.assertEqual(5, value_from_fraction(0.5, 0, 10))

    def test_a_negative_range(self):
        self.assertEqual(-5, value_from_fraction(0.5, -10, 0))

    def test_an_inverted_range_descends(self):
        self.assertEqual(75, value_from_fraction(0.25, 100, 0))


if __name__ == "__main__":
    unittest.main()
