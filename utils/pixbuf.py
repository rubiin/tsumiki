"""The one place that decodes an image file into a pixbuf.

Six call sites each did it differently, and two cached without the file's mtime,
so a replaced image stayed stale until the process restarted.
"""

import os
from functools import lru_cache

from fabric.utils import GdkPixbuf, GLib, logger

#: Decoded pixbufs held at once; a memory ceiling rather than a speed one.
_CACHE_MAXSIZE = 128


def _decode_now(
    path: str, width: int | None, height: int | None
) -> "GdkPixbuf.Pixbuf | None":
    try:
        if width is None and height is None:
            return GdkPixbuf.Pixbuf.new_from_file(path)
        return GdkPixbuf.Pixbuf.new_from_file_at_size(
            path,
            -1 if width is None else width,
            -1 if height is None else height,
        )
    except GLib.Error as e:
        # Undecodable is a normal outcome here; callers decide whether to fall back.
        logger.debug(f"[Pixbuf] Failed to decode {path}: {e}")
        return None


@lru_cache(maxsize=_CACHE_MAXSIZE)
def _decode(
    path: str, width: int | None, height: int | None, mtime_ns: int, size: int
) -> "GdkPixbuf.Pixbuf | None":
    """Decode one exact revision of one file. Cached; see :func:`load_file_pixbuf`."""
    return _decode_now(path, width, height)


def load_file_pixbuf(
    path: str,
    width: int | None = None,
    height: int | None = None,
    *,
    cache: bool = True,
) -> "GdkPixbuf.Pixbuf | None":
    """Decode *path* into a pixbuf, or return None if it cannot be read.

    *width*/*height* decode at a reduced size so GdkPixbuf decompresses only
    the needed resolution; either may be ``-1``. Cached against mtime and size.
    """
    if not path:
        return None
    try:
        stat = os.stat(path)
    except OSError:
        return None

    if not cache:
        return _decode_now(path, width, height)
    return _decode(path, width, height, stat.st_mtime_ns, stat.st_size)
