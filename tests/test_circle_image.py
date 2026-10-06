"""Tests for ``CircularImage.on_draw`` placement.

A notification image is rarely square, and the widget is often handed a slot
larger than its size request, so the geometry has to follow the allocation and
cover the circle. Deriving it from ``size`` instead left the artwork pinned to
the top-left of its slot, which is what pushed it off-centre and cropped it.
"""

import unittest
from unittest import mock


def _load_circle_image():
    """Import the widget, skipping when GTK/fabric are unavailable."""
    try:
        from shared.circle_image import CircularImage, circle_geometry

        return CircularImage, circle_geometry
    except (ImportError, ValueError):
        return None, None


CircularImage, circle_geometry = _load_circle_image()


class RecordingContext:
    """A cairo context stand-in that records the geometry it is given."""

    def __init__(self):
        self.translations = []
        self.scales = []
        self.arcs = []
        self.clips = 0
        self.paints = 0
        self.sources = 0

    def save(self):
        pass

    def restore(self):
        pass

    def arc(self, x, y, radius, start, end):
        self.arcs.append((x, y, radius))

    def clip(self):
        self.clips += 1

    def paint(self):
        self.paints += 1

    def rotate(self, radians):
        pass

    def translate(self, x, y):
        self.translations.append((x, y))

    def scale(self, x, y):
        self.scales.append((x, y))

    def set_source_pixbuf(self, pixbuf, x, y):
        self.sources += 1


def make_widget(
    width: int, height: int, alloc=(78, 78), size: int = 78, angle: int = 0
):
    """Build a CircularImage holding a *width* x *height* pixbuf, uninitialised.

    GTK construction needs a display, so the instance is built by hand; only
    ``on_draw`` reads these fields.
    """
    widget = CircularImage.__new__(CircularImage)
    widget.size = size
    widget._angle = angle
    widget._image = mock.Mock()
    widget._image.get_width.return_value = width
    widget._image.get_height.return_value = height
    widget.get_allocated_width = mock.Mock(return_value=alloc[0])
    widget.get_allocated_height = mock.Mock(return_value=alloc[1])
    return widget


@unittest.skipUnless(CircularImage, "circle image unavailable")
class CircularImagePlacementTest(unittest.TestCase):
    """The pixbuf is centred on the circle, scaled to cover, and clipped once."""

    def draw(self, width, height, alloc=(78, 78), size=78, angle=0):
        widget = make_widget(width, height, alloc, size, angle)
        ctx = RecordingContext()
        with mock.patch(
            "shared.circle_image.Gdk.cairo_set_source_pixbuf",
            side_effect=lambda c, *_: c.set_source_pixbuf(None, 0, 0),
        ):
            widget.on_draw(widget, ctx)
        return ctx

    def test_the_circle_follows_the_allocation_not_the_size_request(self):
        """A slot wider than the request must not pin the artwork top-left."""
        ctx = self.draw(78, 78, alloc=(194, 78), size=78)

        self.assertEqual([(97.0, 39.0, 39.0)], ctx.arcs)

    def test_the_circle_follows_a_taller_allocation(self):
        ctx = self.draw(78, 78, alloc=(78, 400), size=78)

        self.assertEqual([(39.0, 200.0, 39.0)], ctx.arcs)

    def test_the_circle_is_inscribed_in_the_smaller_dimension(self):
        ctx = self.draw(78, 78, alloc=(194, 300), size=78)

        self.assertEqual([(97.0, 150.0, 97.0)], ctx.arcs)

    def test_a_square_image_is_not_upscaled(self):
        ctx = self.draw(78, 78, alloc=(78, 78))

        self.assertEqual([(1.0, 1.0)], ctx.scales)

    def test_a_wide_image_is_scaled_to_cover_the_circle(self):
        """Cover, not contain: a 120x30 source must fill the height, cropping evenly."""
        ctx = self.draw(120, 30, alloc=(78, 78))

        self.assertEqual([(78 / 30, 78 / 30)], ctx.scales)

    def test_a_tall_image_is_scaled_to_cover_the_circle(self):
        ctx = self.draw(30, 120, alloc=(78, 78))

        self.assertEqual([(78 / 30, 78 / 30)], ctx.scales)

    def test_the_pixbuf_is_centred_on_the_circle_before_scaling(self):
        """Centring must use the pixbuf's own extents, not the slot's."""
        ctx = self.draw(120, 30, alloc=(78, 78))

        self.assertEqual([(39.0, 39.0), (-60.0, -15.0)], ctx.translations)

    def test_a_tall_image_is_centred_vertically(self):
        ctx = self.draw(30, 120, alloc=(78, 78))

        self.assertEqual([(39.0, 39.0), (-15.0, -60.0)], ctx.translations)

    def test_the_clip_is_applied_before_the_pixbuf_is_painted(self):
        """Clipping after set_source would still work, but order is asserted
        so a future refactor cannot paint an unclipped square."""
        widget = make_widget(120, 40)
        ctx = mock.Mock()
        order = []
        ctx.translate.side_effect = lambda *a: order.append("translate")
        ctx.clip.side_effect = lambda: order.append("clip")
        ctx.paint.side_effect = lambda: order.append("paint")
        with mock.patch(
            "shared.circle_image.Gdk.cairo_set_source_pixbuf",
            side_effect=lambda *a: order.append("source"),
        ):
            widget.on_draw(widget, ctx)

        self.assertLess(order.index("clip"), order.index("paint"))

    def test_a_missing_pixbuf_draws_nothing(self):
        widget = make_widget(78, 78)
        widget._image = None
        ctx = mock.Mock()

        widget.on_draw(widget, ctx)

        ctx.paint.assert_not_called()

    def test_an_unallocated_widget_draws_nothing(self):
        """A zero-sized slot is degenerate and must not emit a zero-radius arc."""
        ctx = self.draw(78, 78, alloc=(0, 0))

        self.assertEqual([], ctx.arcs)
        self.assertEqual(0, ctx.paints)

    def test_rotation_is_applied_around_the_centre(self):
        """Rotating the scan icon must not move the clip or the image."""
        ctx = self.draw(78, 78, alloc=(78, 78), angle=90)

        self.assertEqual([(39.0, 39.0, 39.0)], ctx.arcs)
        self.assertEqual([(39.0, 39.0), (-39.0, -39.0)], ctx.translations)
        self.assertEqual([(1.0, 1.0)], ctx.scales)


@unittest.skipUnless(circle_geometry, "circle image unavailable")
class CircleGeometryTest(unittest.TestCase):
    """The pure helper the draw handler delegates to."""

    def test_returns_the_allocation_centre(self):
        self.assertEqual(
            (97.0, 150.0, 97.0, 2.0), circle_geometry(194, 300, 97, 97)
        )

    def test_a_source_filling_the_slot_needs_no_scaling(self):
        self.assertEqual(1.0, circle_geometry(194, 300, 194, 194)[3])

    def test_covers_with_the_larger_relative_axis(self):
        self.assertEqual(4.0, circle_geometry(100, 100, 25, 100)[3])
        self.assertEqual(4.0, circle_geometry(100, 100, 100, 25)[3])

    def test_a_degenerate_side_yields_no_circle(self):
        for args in ((0, 10, 5, 5), (10, 0, 5, 5), (10, 10, 0, 5)):
            self.assertEqual((0.0, 0.0, 0.0, 1.0), circle_geometry(*args))


if __name__ == "__main__":
    unittest.main()
