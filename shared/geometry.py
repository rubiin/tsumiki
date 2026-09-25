"""Shared cairo path building and pointer-to-value mapping.

Both started as duplication: three widgets each spelled out the same four-arc
rounded rectangle, and two sliders each spelled out the same clamp-and-scale
arithmetic for turning a pointer coordinate into a value.
"""

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

    *r* is clamped to half the shorter side, because cairo draws a malformed
    path when the corner radii overlap rather than a rounded one. A radius of
    zero or less gives a plain rectangle.

    The path is left open; the caller decides between ``fill()``,
    ``stroke()`` or ``clip()``.
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

    *extent* is the widget's length along the track and *inset* how far the
    track is held in from each end, so the handle centre can travel the full
    length without leaving the widget. The usable length is floored at 1 so a
    collapsed widget divides by something.
    """
    usable = max(1.0, extent - 2 * inset)
    return max(0.0, min(1.0, (position - inset) / usable))


def value_from_fraction(fraction: float, minimum: float, maximum: float) -> float:
    """Scale a 0..1 fraction onto a value range. Works for inverted ranges too."""
    return minimum + fraction * (maximum - minimum)
