"""Tests for :func:`utils.pixbuf.load_file_pixbuf`.

The behaviour that matters is the cache key: two loads of an untouched file
decode once, and a rewritten file decodes again. GdkPixbuf and ``os`` are
replaced on the module, so these run without an image on disk.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import pixbuf as pixbuf_module
from utils.pixbuf import load_file_pixbuf


def glib_error(message: str):
    """The exception type _decode_now catches."""
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import GLib

    return GLib.Error(message)


class FakeStat:
    """Just enough os.stat_result for the loader."""

    def __init__(self, mtime_ns: int, size: int):
        self.st_mtime_ns = mtime_ns
        self.st_mtime = mtime_ns / 1e9
        self.st_size = size


class FakeOs:
    """A stand-in for the os module, so nothing else sees the patch."""

    def __init__(self, stat_result=None, missing: bool = False):
        self.stat_result = stat_result or FakeStat(1000, 500)
        self.missing = missing

    def stat(self, _path):
        if self.missing:
            raise OSError("gone")
        return self.stat_result


class LoadFilePixbufTest(unittest.TestCase):
    """Caching, sizing, and what makes a stale entry a miss."""

    def setUp(self):
        pixbuf_module._decode.cache_clear()
        self.addCleanup(pixbuf_module._decode.cache_clear)

        patcher = mock.patch.object(pixbuf_module, "_decode_now")
        self.addCleanup(patcher.stop)
        self.decode = patcher.start()
        self.decode.return_value = mock.Mock(name="pixbuf")

        self.os_stub = FakeOs()
        os_patcher = mock.patch.object(pixbuf_module, "os", self.os_stub)
        self.addCleanup(os_patcher.stop)
        os_patcher.start()

    def rewrite(self, mtime_ns: int, size: int) -> None:
        self.os_stub.stat_result = FakeStat(mtime_ns, size)

    def test_a_missing_file_is_none_and_never_decoded(self):
        self.os_stub.missing = True

        self.assertIsNone(load_file_pixbuf("/nope.png"))
        self.decode.assert_not_called()

    def test_an_empty_path_is_none(self):
        self.assertIsNone(load_file_pixbuf(""))
        self.decode.assert_not_called()

    def test_no_size_decodes_at_full_resolution(self):
        load_file_pixbuf("/a.png")
        self.decode.assert_called_once_with("/a.png", None, None)

    def test_a_size_decodes_at_that_size(self):
        load_file_pixbuf("/a.png", 16, 16)
        self.decode.assert_called_once_with("/a.png", 16, 16)

    def test_one_axis_scales_to_fit_the_other(self):
        """-1 is new_from_file_at_size's own "preserve this axis"."""
        load_file_pixbuf("/a.png", -1, 32)
        self.decode.assert_called_once_with("/a.png", -1, 32)

    def test_an_untouched_file_is_decoded_once(self):
        load_file_pixbuf("/a.png", 16, 16)
        load_file_pixbuf("/a.png", 16, 16)
        self.decode.assert_called_once_with("/a.png", 16, 16)

    def test_a_rewritten_file_is_decoded_again(self):
        """The bug this replaced: the old cache was keyed on the path alone, so
        a replaced image stayed stale for the life of the process."""
        load_file_pixbuf("/a.png", 16, 16)
        self.rewrite(2000, 500)

        load_file_pixbuf("/a.png", 16, 16)

        self.assertEqual(2, self.decode.call_count)

    def test_a_rewrite_within_the_same_mtime_tick_is_caught_by_size(self):
        load_file_pixbuf("/a.png", 16, 16)
        self.rewrite(1000, 900)

        load_file_pixbuf("/a.png", 16, 16)

        self.assertEqual(2, self.decode.call_count)

    def test_a_different_size_is_a_different_entry(self):
        load_file_pixbuf("/a.png", 16, 16)
        load_file_pixbuf("/a.png", 32, 32)
        self.assertEqual(2, self.decode.call_count)

    def test_cache_false_always_decodes(self):
        load_file_pixbuf("/a.png", 16, 16)
        load_file_pixbuf("/a.png", 16, 16, cache=False)
        load_file_pixbuf("/a.png", 16, 16, cache=False)
        self.assertEqual(3, self.decode.call_count)

    def test_the_cache_is_bounded(self):
        for i in range(pixbuf_module._CACHE_MAXSIZE + 20):
            load_file_pixbuf(f"/a{i}.png", 16, 16)

        info = pixbuf_module._decode.cache_info()
        self.assertLessEqual(info.currsize, pixbuf_module._CACHE_MAXSIZE)


class DecodeFailureTest(unittest.TestCase):
    """An undecodable file is a normal condition, not an exception."""

    def setUp(self):
        self.addCleanup(pixbuf_module._decode.cache_clear)
        pixbuf_module._decode.cache_clear()

        patcher = mock.patch.object(pixbuf_module, "GdkPixbuf")
        self.addCleanup(patcher.stop)
        self.gdk = patcher.start()
        self.gdk.Pixbuf.new_from_file_at_size.side_effect = glib_error("bad data")

        os_patcher = mock.patch.object(pixbuf_module, "os", FakeOs())
        self.addCleanup(os_patcher.stop)
        os_patcher.start()

    def test_a_decode_error_is_reported_as_none(self):
        self.assertIsNone(load_file_pixbuf("/a.png", 16, 16))

    def test_a_failed_decode_is_cached_too(self):
        """Otherwise a broken icon is re-decoded on every repaint."""
        load_file_pixbuf("/a.png", 16, 16)
        load_file_pixbuf("/a.png", 16, 16)

        self.assertEqual(1, self.gdk.Pixbuf.new_from_file_at_size.call_count)


if __name__ == "__main__":
    unittest.main()
