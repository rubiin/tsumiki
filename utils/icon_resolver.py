import contextlib

from fabric.utils import GdkPixbuf, GLib, Gtk, logger, os, re

from utils.decorators import replace_timeout
from utils.functions import read_json_file, ttl_lru_cache, write_json_file
from utils.singleton import SingletonMixin

from .constants import ICON_CACHE_FILE
from .icons import symbolic_icons

# Debounce delay for batching icon cache writes (ms)
_CACHE_WRITE_DELAY_MS = 2000

# Single source of truth for the fallback glyph, so a missing icon renders the
# same way no matter which resolver path reached it.
_FALLBACK_MISSING = symbolic_icons["missing"]

# A cached value equal to one of these means discovery failed, not that the app
# has that icon. They are never written to the cache, and existing entries are
# dropped on load, so a failure can never pin an app to a placeholder.
_PLACEHOLDER_ICONS = frozenset(
    {symbolic_icons["missing"], *symbolic_icons["fallback"].values()}
)


class IconResolver(SingletonMixin):
    """A class to resolve icons for applications."""

    __slots__ = (
        "_cache_dirty",
        "_flush_timer_id",
        "_icon_dict",
        "_icon_theme",
        "_write_pending",
    )

    _app_id_split_re = re.compile(r"-|\.|_|\s")

    def __init__(self):
        if not self._init_once():
            return
        # Defer icon cache loading until first access
        self._icon_dict = None
        self._cache_dirty = False
        self._write_pending = False
        self._flush_timer_id = None
        self._icon_theme = Gtk.IconTheme.get_default()

    def get_icon_theme_icon(self, icon_name: str, icon_size: int = 16):
        """Load an icon from the default theme, or ``None`` when it has none.

        The single theme-lookup entry point: callers handle ``None`` instead of
        catching ``GLib.GError`` themselves, so a missing icon degrades the same
        way everywhere.
        """
        if not icon_name:
            return None
        try:
            return self._icon_theme.load_icon(
                icon_name,
                icon_size,
                Gtk.IconLookupFlags.FORCE_SIZE,
            )
        except GLib.GError:
            return None

    def _ensure_cache_loaded(self):
        """Lazily load the icon cache on first access.

        Entries that hold a placeholder are dropped rather than trusted: they
        mean a previous lookup gave up, and keeping them would stop the app
        from ever resolving a real icon.
        """
        if self._icon_dict is None:
            if os.path.exists(ICON_CACHE_FILE):
                self._icon_dict = read_json_file(ICON_CACHE_FILE) or {}
            else:
                self._icon_dict = {}

            stale = [
                app_id
                for app_id, icon in self._icon_dict.items()
                if icon in _PLACEHOLDER_ICONS
            ]
            if stale:
                for app_id in stale:
                    del self._icon_dict[app_id]
                logger.info(
                    f"[ICONS] dropped {len(stale)} placeholder icon entries: {stale}"
                )
                # Rewrite the file so the placeholders do not come back.
                self._cache_dirty = True
                self._schedule_cache_write()

    def get_icon_name(self, app_id: str) -> str | None:
        """Return the cached icon name for app_id, resolving on miss.

        Returns ``None`` when no real icon can be found - deciding what to show
        instead is the caller's job, because the answer belongs to the surface
        (panel, notification, tray), not to discovery. Only a resolved name is
        cached, so a caller-supplied fallback can never be persisted as an
        app's icon.
        """
        self._ensure_cache_loaded()
        if app_id in self._icon_dict:
            return self._icon_dict[app_id]

        icon_name = self._compositor_find_icon(app_id)
        if icon_name is None:
            logger.info(f"[ICONS] no icon found for app id: '{app_id}'")
            return None

        logger.info(
            f"[ICONS] found new icon: '{icon_name}' for app id: '{app_id}', storing."
        )
        self._store_new_icon(app_id, icon_name)
        return icon_name

    def resolve_icon(
        self,
        pixmap,
        icon_name: str,
        app_id: str,
        icon_size: int = 16,
        default_icon: str = _FALLBACK_MISSING,
    ):
        """Build a pixbuf from a tray pixmap, falling back to the theme."""
        pixbuf = self.get_icon_theme_icon(icon_name, icon_size)

        if not pixbuf and pixmap:
            try:
                pixbuf = pixmap.as_pixbuf(icon_size, GdkPixbuf.InterpType.HYPER)
            except Exception:
                pixbuf = None

        if not pixbuf:
            pixbuf = self.get_icon_pixbuf(app_id, icon_size, default_icon=default_icon)

        return pixbuf

    @ttl_lru_cache(seconds_to_live=3600, maxsize=256)
    def get_icon_pixbuf(
        self, app_id: str, size: int = 16, default_icon: str = _FALLBACK_MISSING
    ):
        """Load the app icon as a pixbuf, falling back to the missing glyph."""
        icon_name = self.get_icon_name(app_id) or default_icon

        pixbuf = self.get_icon_theme_icon(icon_name, size)
        if not pixbuf:
            pixbuf = self.get_icon_theme_icon(default_icon, size)
        return pixbuf

    @ttl_lru_cache(seconds_to_live=3600, maxsize=512)
    def get_icon_pixbuf_by_name(self, icon_name: str, size: int = 16):
        """Load *icon_name* from the theme at exactly *size*.

        For callers that already hold a ``DesktopApp``. Its own
        ``get_icon_pixbuf`` cannot be used for this: it caches the first size
        it is asked for on the shared instance, so it hands back whatever the
        panel happened to request first.
        """
        if not icon_name:
            return None
        return self.get_icon_theme_icon(icon_name, size)

    def _store_new_icon(self, app_id: str, icon: str):
        """Record an icon in the cache and schedule a debounced write."""
        self._icon_dict[app_id] = icon
        self._cache_dirty = True
        self._schedule_cache_write()

    def _schedule_cache_write(self):
        """Schedule a debounced write to batch multiple icon discoveries."""
        if self._write_pending:
            return  # Already scheduled
        self._write_pending = True
        replace_timeout(
            self, "_flush_timer_id", _CACHE_WRITE_DELAY_MS, self._flush_cache
        )

    def _flush_cache(self):
        """Write cache to disk if dirty."""
        self._write_pending = False
        self._flush_timer_id = None
        if self._cache_dirty:
            write_json_file(ICON_CACHE_FILE, self._icon_dict)
            self._cache_dirty = False
            logger.info("[ICONS] Flushed icon cache to disk")
        return False  # Don't repeat

    def _get_icon_from_desktop_file(self, desktop_file_path: str) -> str | None:
        """Extract the Icon= value from a .desktop file, or None if it has none."""
        with open(desktop_file_path, "r") as f:
            for line in f.readlines():
                stripped = line.strip()
                if stripped.startswith("Icon="):
                    return "".join(stripped[5:].split())
        return None

    _desktop_files_cache: dict[str, tuple[str, ...]] | None = None

    def _get_desktop_file(self, app_id: str) -> str | None:
        """Find the first .desktop file loosely matching app_id."""
        if IconResolver._desktop_files_cache is None:
            IconResolver._desktop_files_cache = {}
            for data_dir in GLib.get_system_data_dirs():
                apps_dir = data_dir + "/applications/"
                try:
                    files = tuple(
                        s for s in os.listdir(apps_dir) if s.endswith(".desktop")
                    )
                except OSError:
                    continue
                IconResolver._desktop_files_cache[apps_dir] = files

        app_id_norm = "".join(app_id.lower().split())
        for apps_dir, files in IconResolver._desktop_files_cache.items():
            matching = [s for s in files if app_id_norm and app_id_norm in s.lower()]
            if matching:
                return apps_dir + matching[0]

            for word in filter(None, self._app_id_split_re.split(app_id)):
                word_lower = word.lower()
                matching = [s for s in files if word_lower in s.lower()]
                if matching:
                    return apps_dir + matching[0]

        return None

    def _compositor_find_icon(self, app_id: str) -> str | None:
        """Resolve an icon name via the theme, then desktop files, else None."""
        if self._icon_theme.has_icon(app_id):
            return app_id
        if self._icon_theme.has_icon(app_id + "-desktop"):
            return app_id + "-desktop"
        desktop_file = self._get_desktop_file(app_id)
        if desktop_file:
            return self._get_icon_from_desktop_file(desktop_file)
        return None

    def scale_pixbuf_to_size(
        self, pixbuf: GdkPixbuf.Pixbuf, size: int
    ) -> GdkPixbuf.Pixbuf | None:
        """Scale ``pixbuf`` to a square ``size`` x ``size`` if not already."""
        if pixbuf.get_width() == size and pixbuf.get_height() == size:
            return pixbuf
        return pixbuf.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)

    @ttl_lru_cache(seconds_to_live=3600, maxsize=256)
    def resolve_icon_pixbuf(
        self,
        app_id: str,
        size: int,
    ) -> GdkPixbuf.Pixbuf | None:
        """Resolve an application icon pixbuf.

        The cache is keyed on *app_id* alone, so nothing unhashable may be
        passed in: a resolved ``DesktopApp`` is looked up here rather than
        accepted as an argument, since fabric declares it ``@dataclass``, which
        generates ``__eq__`` and so leaves ``__hash__`` unset.

        Strategy:
        1. Ask ``AppUtils.find_app`` for the app's icon *name* (the XDG desktop
            database maps Hyprland window classes reliably) and load it from the
            theme at exactly *size*.
        2. Fall back to the GTK icon theme lookup via ``get_icon_pixbuf``,
            whose own fallback is ``symbolic_icons["missing"]``.

        The pixbuf is deliberately not taken from ``DesktopApp.get_icon_pixbuf``:
        that caches the first size it is asked for on the shared, process-wide
        ``DesktopApp``, so whichever panel widget resolved the app first would
        dictate the size everyone else gets. Loading by name here means each
        caller gets a pixbuf rendered at the size it actually wants.
        """
        from .app import AppUtils

        pixbuf = None

        with contextlib.suppress(Exception):
            desktop_app = AppUtils().find_app(app_id)
            if desktop_app and desktop_app.icon_name:
                pixbuf = self.get_icon_pixbuf_by_name(desktop_app.icon_name, size)

        # Fall back to the resolver's theme lookup
        if not pixbuf:
            pixbuf = self.get_icon_pixbuf(app_id, size)

        return self.scale_pixbuf_to_size(pixbuf, size) if pixbuf else None
