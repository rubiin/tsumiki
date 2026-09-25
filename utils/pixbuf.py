"""One place that decodes an image file into a pixbuf.

Six call sites were each doing it slightly differently: some decoded at a
reduced size, some at full size, some cached on the path alone, some caught
``GLib.GError`` and some let it escape. Two of them cached without the file's
mtime, so a replaced image stayed stale until the process restarted.
"""

import os
from functools import lru_cache

from fabric.utils import GdkPixbuf, GLib, logger

#: Decoded pixbufs held at once. Each entry is a decoded bitmap, so this is a
#: memory ceiling rather than a speed one.
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
        # A file that exists but will not decode is a normal condition here:
        # tray icons and notification images both point at paths that may be
        # truncated or the wrong format. Callers decide whether to fall back.
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

    Pass *width*/*height* to decode at a reduced size, which lets GdkPixbuf
    decompress only the resolution it needs for a JPEG. Leave either as None
    for a full-size decode. An explicit ``-1`` scales that axis to fit the
    other, which is what ``new_from_file_at_size`` does natively.

    Results are cached against the file's mtime and size, so a rewritten image
    is re-decoded while an untouched one is not decoded again at all; the
    superseded entry ages out of the cache on its own. Pass ``cache=False`` for
    a one-shot decode, or to keep a large transient image out of the cache.
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
