import contextlib

from fabric.utils import GdkPixbuf, GLib, Gtk, logger, os, re

from utils.functions import read_json_file, ttl_lru_cache, write_json_file

from .constants import ICON_CACHE_FILE
from .icons import symbolic_icons

# Debounce delay for batching icon cache writes (ms)
_CACHE_WRITE_DELAY_MS = 2000


class IconResolver:
    """A class to resolve icons for applications."""

    __slots__ = ("_cache_dirty", "_flush_timer_id", "_icon_dict", "_write_pending")

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if IconResolver._initialized:
            return
        IconResolver._initialized = True

        # Defer icon cache loading until first access
        self._icon_dict = None
        self._cache_dirty = False
        self._write_pending = False
        self._flush_timer_id = None

    def get_icon_theme_icon(self, icon_name: str, icon_size: int = 16):
        return (
            Gtk.IconTheme()
            .get_default()
            .load_icon(
                icon_name,
                icon_size,
                Gtk.IconLookupFlags.FORCE_SIZE,
            )
        )

    def _ensure_cache_loaded(self):
        """Lazily load the icon cache on first access."""
        if self._icon_dict is None:
            if os.path.exists(ICON_CACHE_FILE):
                self._icon_dict = read_json_file(ICON_CACHE_FILE) or {}
            else:
                self._icon_dict = {}

    def get_icon_name(self, app_id: str):
        """Return the cached icon name for app_id, resolving on miss."""
        self._ensure_cache_loaded()
        if app_id in self._icon_dict:
            return self._icon_dict[app_id]
        new_icon = self._compositor_find_icon(app_id)
        logger.info(
            f"[ICONS] found new icon: '{new_icon}' for app id: '{app_id}', storing."
        )
        self._store_new_icon(app_id, new_icon)
        return new_icon

    def resolve_icon(self, pixmap, icon_name: str, app_id: str, icon_size: int = 16):
        """Build a pixbuf from a tray pixmap, falling back to the theme."""

        try:
            if icon_name:
                return self.get_icon_theme_icon(icon_name, icon_size)

            if pixmap is None:
                return self.get_icon_pixbuf(app_id, icon_size)
                return pixmap.as_pixbuf(icon_size, GdkPixbuf.InterpType.HYPER)
        except GLib.GError:
            return self.get_icon_pixbuf(app_id, icon_size)

    @ttl_lru_cache(seconds_to_live=3600, maxsize=256)
    def get_icon_pixbuf(self, app_id: str, size: int = 16):
        """Load the app icon as a pixbuf, falling back to image-missing."""
        icon_name = self.get_icon_name(app_id)
        try:
            return self.get_icon_theme_icon(icon_name, size)
        except GLib.GError:
            return self.get_icon_theme_icon("image-missing", size)

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
        if self._flush_timer_id is not None:
            GLib.source_remove(self._flush_timer_id)
        self._flush_timer_id = GLib.timeout_add(
            _CACHE_WRITE_DELAY_MS, self._flush_cache
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

    def _get_icon_from_desktop_file(self, desktop_file_path: str):
        """Extract the Icon= value from a .desktop file."""
        with open(desktop_file_path, "r") as f:
            for line in f.readlines():
                stripped = line.strip()
                if stripped.startswith("Icon="):
                    return "".join(stripped[5:].split())
            return symbolic_icons["fallback"]["executable"]

    _app_id_split_re = None

    def _get_desktop_file(self, app_id: str) -> str | None:
        """Find the first .desktop file loosely matching app_id."""
        if self._app_id_split_re is None:
            self.__class__._app_id_split_re = re.compile(r"-|\.|_|\s")

        data_dirs = GLib.get_system_data_dirs()
        for data_dir in data_dirs:
            data_dir = data_dir + "/applications/"
            if os.path.exists(data_dir):
                # Do name resolving here
                files = os.listdir(data_dir)
                matching = [
                    s for s in files if "".join(app_id.lower().split()) in s.lower()
                ]
                if matching:
                    return data_dir + matching[0]

                for word in list(
                    filter(None, self.__class__._app_id_split_re.split(app_id))
                ):
                    matching = [s for s in files if word.lower() in s.lower()]
                    if matching:
                        return data_dir + matching[0]

        return None

    def _compositor_find_icon(self, app_id: str):
        """Resolve an icon name via the theme, then desktop files."""
        if Gtk.IconTheme.get_default().has_icon(app_id):
            return app_id
        if Gtk.IconTheme.get_default().has_icon(app_id + "-desktop"):
            return app_id + "-desktop"
        desktop_file = self._get_desktop_file(app_id)
        return (
            self._get_icon_from_desktop_file(desktop_file)
            if desktop_file
            else symbolic_icons["fallback"]["executable"]
        )

    def _scale_pixbuf_to_size(
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
        desktop_app=None,
    ) -> GdkPixbuf.Pixbuf | None:
        """Resolve an application icon pixbuf.

        Strategy (matching the overview module's proven approach):
        1. If *desktop_app* is given, try its ``get_icon_pixbuf`` directly.
        2. Otherwise look up the app via ``AppUtils.find_app`` (XDG desktop
            app database — most reliable for Hyprland window classes).
        3. Fall back to ``IconResolver`` (GTK icon theme lookup).
        4. Final fallback: ``image-missing``.
        """
        from .app import AppUtils

        pixbuf = None

        # Try DesktopApp first
        if desktop_app is None:
            with contextlib.suppress(Exception):
                desktop_app = AppUtils().find_app(app_id)
        if desktop_app:
            try:
                pixbuf = desktop_app.get_icon_pixbuf(size=size)
            except Exception:
                pixbuf = None

        # Fall back to the resolver's theme lookup
        if not pixbuf:
            pixbuf = self.get_icon_pixbuf(app_id, size)
        if not pixbuf:
            pixbuf = self.get_icon_pixbuf("application-x-executable-symbolic", size)
        if not pixbuf:
            pixbuf = self.get_icon_pixbuf("image-missing", size)

        return self._scale_pixbuf_to_size(pixbuf, size) if pixbuf else None
