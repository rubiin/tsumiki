"""Shared cairo path building and pointer-to-value mapping, extracted to kill
duplication across three widgets and two sliders."""

import math

from fabric.utils import cairo


def rounded_rect_path(
    cr: cairo.Context,
    x: float,
    y: float,
    w: float,
    h: float,
    r: float,
) -> None:
    """Append a rounded rectangle to the current cairo path.

    *r* is clamped to half the shorter side: cairo draws a malformed path when
    corner radii overlap. The path stays open for the caller to fill.
    """
    r = min(r, w / 2, h / 2)
    if r <= 0:
        cr.rectangle(x, y, w, h)
        return

    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def fraction_from_position(position: float, extent: float, inset: float) -> float:
    """Map a pointer coordinate along a track to 0..1, clamped at both ends.

    *inset* holds the track in from each end so the handle travels the full length;
    the usable length is floored at 1 so a collapsed widget still divides.
    """
    usable = max(1.0, extent - 2 * inset)
    return max(0.0, min(1.0, (position - inset) / usable))


def value_from_fraction(fraction: float, minimum: float, maximum: float) -> float:
    """Scale a 0..1 fraction onto a value range. Works for inverted ranges too."""
    return minimum + fraction * (maximum - minimum)
