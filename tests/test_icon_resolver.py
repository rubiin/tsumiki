"""Tests for the app-id -> icon-name cache in ``utils/icon_resolver.py``.

A fallback glyph must never be persisted as an app's icon: once stored it is a
cache hit, and a hit short-circuits discovery, so the app stays pinned to the
placeholder for as long as the cache file survives.
"""

import json
import os
import tempfile
import unittest
from unittest import mock

from utils import icon_resolver as icon_resolver_module
from utils.icon_resolver import _FALLBACK_MISSING, _PLACEHOLDER_ICONS, IconResolver


class FakeIconTheme:
    """Minimal stand-in for ``Gtk.IconTheme`` (None headless)."""

    def __init__(self, available=()):
        self.available = set(available)

    def has_icon(self, icon_name: str) -> bool:
        return icon_name in self.available

    def load_icon(self, icon_name, size, flags):
        if icon_name in self.available:
            return f"pixbuf:{icon_name}:{size}"
        raise icon_resolver_module.GLib.GError("no such icon")


class IconResolverCacheTest(unittest.TestCase):
    """Only a genuinely resolved icon name may enter the cache."""

    def setUp(self):
        # The resolver is a singleton, so each test needs a clean instance.
        IconResolver.reset_instance()
        self.addCleanup(IconResolver.reset_instance)

        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.cache_file = os.path.join(self._tmpdir.name, "icons.json")

        for patcher in (
            mock.patch.object(
                icon_resolver_module, "ICON_CACHE_FILE", self.cache_file
            ),
            # Never schedule a real GLib timer from a test.
            mock.patch.object(IconResolver, "_schedule_cache_write"),
            mock.patch.object(IconResolver, "_get_desktop_file", return_value=None),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _resolver(self, available=(), *, cache=None):
        """Build a resolver with a fake theme and an optional pre-seeded cache."""
        if cache is not None:
            with open(self.cache_file, "w", encoding="utf-8") as handle:
                json.dump(cache, handle)

        resolver = IconResolver()
        resolver._icon_theme = FakeIconTheme(available)
        return resolver

    def test_resolved_icon_is_cached(self):
        resolver = self._resolver(["firefox"])

        self.assertEqual("firefox", resolver.get_icon_name("firefox"))
        self.assertEqual({"firefox": "firefox"}, resolver._icon_dict)

    def test_placeholder_is_never_cached(self):
        """The reported bug: a failed lookup stored the caller's fallback."""
        resolver = self._resolver()

        self.assertIsNone(resolver.get_icon_name("HyDE Power"))
        self.assertEqual({}, resolver._icon_dict)

    def test_placeholder_entry_from_an_older_run_is_dropped_and_re_resolved(self):
        """Entries written before the fix must not pin an app any more."""
        resolver = self._resolver(
            cache={"HyDE Power": _FALLBACK_MISSING, "firefox": "firefox"}
        )
        resolver._ensure_cache_loaded()
        self.assertNotIn("HyDE Power", resolver._icon_dict)

        with (
            mock.patch.object(
                IconResolver, "_get_desktop_file", return_value="hyde.desktop"
            ),
            mock.patch(
                "builtins.open",
                mock.mock_open(read_data="[Desktop Entry]\nIcon=hyde-power\n"),
            ),
        ):
            self.assertEqual("hyde-power", resolver.get_icon_name("HyDE Power"))

        self.assertEqual(
            {"HyDE Power": "hyde-power", "firefox": "firefox"}, resolver._icon_dict
        )

    def test_every_placeholder_name_is_treated_as_unresolved(self):
        cached = {f"app-{index}": name for index, name in enumerate(_PLACEHOLDER_ICONS)}
        resolver = self._resolver(cache=cached)

        resolver._ensure_cache_loaded()

        self.assertEqual({}, resolver._icon_dict)
        self.assertTrue(
            resolver._cache_dirty, "stale file should be queued for rewrite"
        )

    def test_flushed_cache_carries_no_placeholders(self):
        cached = {"HyDE Power": _FALLBACK_MISSING, "firefox": "firefox"}
        resolver = self._resolver(cache=cached)
        resolver.get_icon_name("firefox")  # triggers the load

        with mock.patch.object(icon_resolver_module, "write_json_file") as write:
            resolver._flush_cache()

        written = write.call_args.args[1]
        self.assertEqual({"firefox": "firefox"}, written)

    def test_desktop_file_without_icon_line_is_unresolved(self):
        resolver = self._resolver()
        with (
            mock.patch.object(
                IconResolver, "_get_desktop_file", return_value="x.desktop"
            ),
            mock.patch("builtins.open", mock.mock_open(read_data="[Desktop Entry]\n")),
        ):
            self.assertIsNone(resolver.get_icon_name("noicon"))

        self.assertEqual({}, resolver._icon_dict)

    def test_desktop_file_icon_is_cached(self):
        resolver = self._resolver()
        with (
            mock.patch.object(
                IconResolver, "_get_desktop_file", return_value="x.desktop"
            ),
            mock.patch(
                "builtins.open", mock.mock_open(read_data="[Desktop Entry]\nIcon=f\n")
            ),
        ):
            self.assertEqual("f", resolver.get_icon_name("myapp"))

        self.assertEqual({"myapp": "f"}, resolver._icon_dict)

    def test_pixbuf_falls_back_when_nothing_resolves(self):
        """A miss must still render, using the caller's fallback glyph."""
        resolver = self._resolver([_FALLBACK_MISSING])

        pixbuf = resolver.get_icon_pixbuf("HyDE Power", 25)

        self.assertEqual(f"pixbuf:{_FALLBACK_MISSING}:25", pixbuf)
        self.assertEqual({}, resolver._icon_dict)

    def test_pixbuf_prefers_the_resolved_icon(self):
        resolver = self._resolver(["nm-signal-75", _FALLBACK_MISSING])

        self.assertEqual(
            "pixbuf:nm-signal-75:25", resolver.get_icon_pixbuf("nm-signal-75", 25)
        )
        self.assertEqual({"nm-signal-75": "nm-signal-75"}, resolver._icon_dict)


if __name__ == "__main__":
    unittest.main()
