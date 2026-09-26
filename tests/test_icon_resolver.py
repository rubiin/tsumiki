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


class ResolveIconPixbufCacheKeyTest(unittest.TestCase):
    """``resolve_icon_pixbuf`` is TTL-cached, so its key must stay hashable.

    Regression: a ``DesktopApp`` used to be passed in as an argument, and the
    lookup died with ``TypeError: unhashable type: 'DesktopApp'`` - fabric
    declares it ``@dataclass(init=False)``, which generates ``__eq__`` and so
    leaves ``__hash__`` unset. Because the overview button then failed to
    finish constructing, every window fell back to the missing-image glyph.
    The app is looked up from ``app_id`` instead.
    """

    def setUp(self):
        IconResolver.reset_instance()
        self.addCleanup(IconResolver.reset_instance)

        for patcher in (
            # Never schedule a real GLib timer, or touch the real desktop db.
            mock.patch.object(IconResolver, "_schedule_cache_write"),
            mock.patch.object(IconResolver, "_get_desktop_file", return_value=None),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        self._resolver = IconResolver()
        self._resolver._icon_theme = FakeIconTheme()
        self._resolver._icon_dict = {}

    def test_third_argument_is_rejected(self):
        """The key is ``(app_id, size)``; nothing else may reach the cache."""
        with self.assertRaises(TypeError):
            self._resolver.resolve_icon_pixbuf("wezterm", 24, object())

    def test_call_is_cacheable_and_repeated_calls_hit_the_cache(self):
        with mock.patch(
            "utils.app.AppUtils.find_app", return_value=None
        ) as find_app:
            first = self._resolver.resolve_icon_pixbuf("org.wezfurlong.wezterm", 71)
            second = self._resolver.resolve_icon_pixbuf("org.wezfurlong.wezterm", 71)

        self.assertIsNone(first)
        self.assertIs(first, second, "second call should come from the cache")
        find_app.assert_called_once_with("org.wezfurlong.wezterm")

    def test_desktop_app_is_looked_up_internally(self):
        pixbuf = mock.Mock()
        # Already at the requested size, so no scaling is applied.
        pixbuf.get_width.return_value = 24
        pixbuf.get_height.return_value = 24

        with mock.patch(
            "utils.app.AppUtils.find_app",
            return_value=mock.Mock(icon_name="wezterm", get_icon_pixbuf=None),
        ), mock.patch.object(
            IconResolver, "get_icon_pixbuf_by_name", return_value=pixbuf
        ):
            self.assertIs(pixbuf, self._resolver.resolve_icon_pixbuf("wezterm", 24))

    def test_falls_back_to_the_theme_when_lookup_raises(self):
        with mock.patch(
            "utils.app.AppUtils.find_app", side_effect=RuntimeError("dbus down")
        ):
            self.assertIsNone(self._resolver.resolve_icon_pixbuf("wezterm", 24))


class IconSizeTest(unittest.TestCase):
    """Each caller must get a pixbuf rendered at the size it asked for.

    Regression: the icons looked blurry because ``DesktopApp`` caches the first
    size it is asked for on an instance shared for the whole process. A panel
    widget resolved the app at 16px, so the overview's 71px icon was a
    bilinear upscale of that 16px render - roughly 40% of the edge contrast.
    """

    def setUp(self):
        IconResolver.reset_instance()
        self.addCleanup(IconResolver.reset_instance)

        for patcher in (
            mock.patch.object(IconResolver, "_schedule_cache_write"),
            mock.patch.object(IconResolver, "_get_desktop_file", return_value=None),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        self._resolver = IconResolver()
        self._resolver._icon_theme = FakeIconTheme(["wezterm"])
        self._resolver._icon_dict = {}
        # FakeIconTheme hands back marker strings, not real pixbufs, so the
        # measurement in scale_pixbuf_to_size is stubbed out here.
        patcher = mock.patch.object(
            IconResolver, "scale_pixbuf_to_size", side_effect=lambda pixbuf, _: pixbuf
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_each_size_is_rendered_at_that_size(self):
        for size in (16, 24, 32, 71):
            with self.subTest(size=size):
                pixbuf = self._resolver.get_icon_pixbuf_by_name("wezterm", size)
                self.assertEqual(f"pixbuf:wezterm:{size}", pixbuf)

    def test_a_small_request_does_not_degrade_a_later_large_one(self):
        """The panel resolving at 16px must not poison the overview's 71px."""
        self._resolver.get_icon_pixbuf_by_name("wezterm", 16)

        self.assertEqual(
            "pixbuf:wezterm:71", self._resolver.get_icon_pixbuf_by_name("wezterm", 71)
        )

    def test_by_name_returns_none_for_an_empty_name(self):
        self.assertIsNone(self._resolver.get_icon_pixbuf_by_name("", 32))
        self.assertIsNone(self._resolver.get_icon_pixbuf_by_name(None, 32))

    def test_large_request_ignores_a_sticky_small_desktop_app_cache(self):
        """The reported bug, reproduced through the resolver's public API.

        fabric's ``DesktopApp.get_icon_pixbuf`` caches the first size it is
        asked for, so a panel widget resolving the app at 16px leaves every
        later caller upscaling that. Mirrors the real object here: the large
        request must come from the theme, not the cache.
        """

        class StickyDesktopApp:
            """Mimics fabric's first-size-wins ``_pixbuf`` cache."""

            icon_name = "wezterm"

            def __init__(self):
                self._pixbuf = None

            def get_icon_pixbuf(self, size=48, **kwargs):
                if self._pixbuf is None:
                    self._pixbuf = f"sticky:{size}"
                return self._pixbuf

        desktop_app = StickyDesktopApp()
        self.assertEqual("sticky:16", desktop_app.get_icon_pixbuf(16))

        with mock.patch("utils.app.AppUtils.find_app", return_value=desktop_app):
            pixbuf = self._resolver.resolve_icon_pixbuf("org.wezfurlong.wezterm", 71)

        self.assertEqual("pixbuf:wezterm:71", pixbuf)
        self.assertEqual("sticky:16", desktop_app.get_icon_pixbuf(16), "cache unused")

    def test_resolve_uses_the_app_icon_name_rather_than_the_cached_pixbuf(self):
        desktop_app = mock.Mock(icon_name="wezterm")
        # Any use of the shared DesktopApp pixbuf cache is the bug.
        desktop_app.get_icon_pixbuf = mock.Mock(
            side_effect=AssertionError("must not use the shared DesktopApp pixbuf")
        )
        pixbuf = mock.Mock()
        pixbuf.get_width.return_value = 71
        pixbuf.get_height.return_value = 71

        with (
            mock.patch("utils.app.AppUtils.find_app", return_value=desktop_app),
            mock.patch.object(
                IconResolver, "get_icon_pixbuf_by_name", return_value=pixbuf
            ) as by_name,
        ):
            self.assertIs(
                pixbuf, self._resolver.resolve_icon_pixbuf("org.wezfurlong.wezterm", 71)
            )

        by_name.assert_called_once_with("wezterm", 71)
        desktop_app.get_icon_pixbuf.assert_not_called()


class ScalePixbufTest(unittest.TestCase):
    """``scale_pixbuf_to_size`` must never enlarge a pixbuf.

    Bilinearly upscaling a small source softens it - a 32px notification icon
    enlarged to 78px loses ~16% of its edge contrast - and it discards the
    display's real scale factor. Downscaling a larger source is effectively
    lossless, so only that direction is done here.
    """

    def setUp(self):
        IconResolver.reset_instance()
        self.addCleanup(IconResolver.reset_instance)
        self._resolver = IconResolver()

    @staticmethod
    def _pixbuf(width: int, height: int):
        pixbuf = mock.Mock()
        pixbuf.get_width.return_value = width
        pixbuf.get_height.return_value = height
        pixbuf.scale_simple.return_value = "scaled"
        return pixbuf

    def test_exact_size_is_returned_untouched(self):
        pixbuf = self._pixbuf(32, 32)
        self.assertIs(pixbuf, self._resolver.scale_pixbuf_to_size(pixbuf, 32))
        pixbuf.scale_simple.assert_not_called()

    def test_larger_source_is_downscaled(self):
        pixbuf = self._pixbuf(256, 256)
        self.assertEqual("scaled", self._resolver.scale_pixbuf_to_size(pixbuf, 78))
        pixbuf.scale_simple.assert_called_once()

    def test_smaller_source_is_never_enlarged(self):
        pixbuf = self._pixbuf(32, 32)
        self.assertIs(pixbuf, self._resolver.scale_pixbuf_to_size(pixbuf, 78))
        pixbuf.scale_simple.assert_not_called()

    def test_larger_in_one_axis_only_is_still_downscaled(self):
        """200x40 still has to be fitted into the 78px box."""
        pixbuf = self._pixbuf(200, 40)
        self.assertEqual("scaled", self._resolver.scale_pixbuf_to_size(pixbuf, 78))
        pixbuf.scale_simple.assert_called_once()


if __name__ == "__main__":
    unittest.main()
