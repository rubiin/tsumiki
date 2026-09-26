"""Tests for ``NotificationWidget._load_body_image_pixbuf``.

The reported bug was an ``AttributeError`` from ``helpers.set_cursor``, but the
audit next to it turned up a second one (``helpers.load_file_pixbuf``) plus a
blur path: ``new_from_file_at_size`` *enlarges* a source smaller than the target
and stretches a non-square one, so a small attachment arrived pre-blurred.
"""

import os
import tempfile
import unittest
from unittest import mock

from fabric.utils import GdkPixbuf, Gtk

from modules import notification as notification_module
from utils import constants

SIZE = constants.NOTIFICATION_IMAGE_SIZE


def write_image(path: str, size: int) -> str:
    """Write a real PNG of *size* x *size* to *path*."""
    theme = Gtk.IconTheme.get_default()
    pixbuf = theme.load_icon(
        "org.wezfurlong.wezterm", size, Gtk.IconLookupFlags.FORCE_SIZE
    )
    pixbuf.savev(path, "png", [], [])
    return path


class LoadBodyImagePixbufTest(unittest.TestCase):
    """An attached image is shrunk to fit, never enlarged to fill."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.widget = notification_module.NotificationWidget.__new__(
            notification_module.NotificationWidget
        )

    def load(self, path: str):
        return self.widget._load_body_image_pixbuf(path)

    def test_a_small_attachment_is_not_enlarged(self):
        """A 32px source must stay 32px, not be blown up to 78px."""
        path = write_image(os.path.join(self._tmpdir.name, "small.png"), 32)

        pixbuf = self.load(path)

        self.assertIsNotNone(pixbuf)
        self.assertEqual(32, pixbuf.get_width())
        self.assertEqual(32, pixbuf.get_height())

    def test_a_large_attachment_is_downscaled_to_the_target(self):
        path = write_image(os.path.join(self._tmpdir.name, "large.png"), 256)

        pixbuf = self.load(path)

        self.assertEqual(SIZE, pixbuf.get_width())
        self.assertEqual(SIZE, pixbuf.get_height())

    def test_file_url_prefix_is_stripped(self):
        path = write_image(os.path.join(self._tmpdir.name, "u.png"), 32)

        pixbuf = self.load(f"file://{path}")

        self.assertIsNotNone(pixbuf)

    def test_missing_path_returns_none(self):
        self.assertIsNone(self.load(f"{self._tmpdir.name}/nope.png"))
        self.assertIsNone(self.load(""))

    def test_env_vars_are_expanded(self):
        write_image(os.path.join(self._tmpdir.name, "env.png"), 32)
        with mock.patch.dict(os.environ, {"TSUMIKI_TEST_DIR": self._tmpdir.name}):
            pixbuf = self.load("$TSUMIKI_TEST_DIR/env.png")
        self.assertIsNotNone(pixbuf)

    def test_header_probe_does_not_decode_the_image(self):
        """The cheap path must not do a full decode just to learn the size."""
        path = write_image(os.path.join(self._tmpdir.name, "probe.png"), 256)
        with mock.patch.object(
            GdkPixbuf.Pixbuf, "get_file_info", wraps=GdkPixbuf.Pixbuf.get_file_info
        ) as probe:
            self.load(path)
        probe.assert_called_once_with(path)


if __name__ == "__main__":
    unittest.main()
