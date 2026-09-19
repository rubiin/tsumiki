import unittest

try:
    import gi

    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf

    from shared.media import (
        _LIGHT_ART_LUMINANCE_THRESHOLD,
        _average_luminance,
    )

    HAS_GDKPIXBUF = True
except (ImportError, ValueError):
    HAS_GDKPIXBUF = False


@unittest.skipUnless(HAS_GDKPIXBUF, "GdkPixbuf bindings unavailable")
class AverageLuminanceTest(unittest.TestCase):
    """Artwork luminance classification for text contrast."""

    def _solid_pixbuf(self, rgba: int) -> GdkPixbuf.Pixbuf:
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 4, 4)
        pixbuf.fill(rgba)
        return pixbuf

    def test_white_image_is_max_luminance(self):
        lum = _average_luminance(self._solid_pixbuf(0xFFFFFFFF))
        self.assertAlmostEqual(lum, 1.0, places=2)
        self.assertGreater(lum, _LIGHT_ART_LUMINANCE_THRESHOLD)

    def test_black_image_is_zero_luminance(self):
        lum = _average_luminance(self._solid_pixbuf(0x00000000))
        self.assertAlmostEqual(lum, 0.0, places=2)
        self.assertLess(lum, _LIGHT_ART_LUMINANCE_THRESHOLD)

    def test_luminance_is_normalized(self):
        lum = _average_luminance(self._solid_pixbuf(0xFFFFFFFF))
        self.assertTrue(0.0 <= lum <= 1.0)

    def test_grayscale_channels_weighted(self):
        # Green channel dominates perceptual luminance (weight 0.7152).
        green = _average_luminance(self._solid_pixbuf(0x00FF00FF))
        blue = _average_luminance(self._solid_pixbuf(0x0000FFFF))
        self.assertGreater(green, blue)

    def test_alpha_only_pixbuf_returns_none(self):
        # Fewer than 3 channels cannot be classified.
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 4, 4)
        pixbuf.fill(0xFFFFFFFF)

        # Simulate a 1-channel buffer by asserting None from a stub.
        class _Stub:
            def get_n_channels(self):
                return 1

        self.assertIsNone(_average_luminance(_Stub()))


if __name__ == "__main__":
    unittest.main()
