from fabric.utils import get_desktop_applications

from utils.constants import NORMALIZE_SUFFIXES
from utils.singleton import SingletonMixin


class AppUtils(SingletonMixin):
    """Singleton utility class for managing desktop applications"""

    __slots__ = ("_all_applications", "_app_identifiers")


    def __init__(self):
        if not self._init_once():
            return
        # Defer loading until first access to save memory at startup
        self._all_applications = None
        self._app_identifiers = None

    def _ensure_loaded(self):
        """Lazily load applications on first access."""
        if self._all_applications is None:
            self._all_applications = get_desktop_applications()
            self._app_identifiers = self._build_app_identifiers_map()

    @property
    def all_applications(self):
        """Return all desktop applications (lazy-loaded)."""
        self._ensure_loaded()
        return self._all_applications

    @property
    def app_identifiers(self):
        """Return the mapping of app identifiers to DesktopApp objects."""
        self._ensure_loaded()
        return self._app_identifiers

    def refresh(self):
        """Return all desktop applications, optionally refreshing the list."""
        from fabric.utils import get_desktop_applications

        self._all_applications = get_desktop_applications()
        self._app_identifiers = self._build_app_identifiers_map()
        return True

    def _normalize_window_class(self, class_name: str) -> str:
        """Normalize window class by removing common suffixes and lowercase."""
        if not class_name:
            return ""

        normalized = class_name.lower()

        # Check suffixes using frozenset
        for suffix in NORMALIZE_SUFFIXES:
            if normalized.endswith(suffix):
                return normalized[: -len(suffix)]

        return normalized

    def classes_match(self, class1: str, class2: str) -> bool:
        """Check if two window class names match with stricter comparison."""
        if not class1 or not class2:
            return False

        # Normalize both classes
        norm1 = self._normalize_window_class(class1)
        norm2 = self._normalize_window_class(class2)

        # Direct match after normalization
        return norm1 == norm2

    # -------------------------
    # App Lookup Helpers
    # -------------------------

    def _build_app_identifiers_map(self) -> dict:
        """Create a fast lookup dictionary for app identifiers."""
        identifiers = {}
        for app in self._all_applications:
            # Pre-compute keys to avoid repeated getattr calls
            executable = getattr(app, "executable", None)
            command_line = getattr(app, "command_line", None)

            keys = [
                app.name,
                app.display_name,
                app.window_class,
                executable.split("/")[-1] if executable else None,
                command_line.split()[0].split("/")[-1] if command_line else None,
            ]

            for key in keys:
                if key:
                    identifiers[key.lower()] = app
        return identifiers

    def find_app(self, app_identifier):
        """Find an app by dict or direct identifier."""
        if not app_identifier:
            return None
        # Load before the identifier map is touched: find_app is the entry
        # point callers reach for first, so it cannot assume a property ran.
        self._ensure_loaded()
        if isinstance(app_identifier, dict):
            for key in (
                "window_class",
                "executable",
                "command_line",
                "name",
                "display_name",
            ):
                val = app_identifier.get(key)
                if val:
                    app = self._find_app_by_key(val)
                    if app:
                        return app
            return None
        return self._find_app_by_key(app_identifier)

    def _find_app_by_key(self, key_value):
        """Find app by identifier or partial match."""
        if not key_value:
            return None
        normalized_id = str(key_value).lower()

        # Fast path: direct lookup
        app = self._app_identifiers.get(normalized_id)
        if app:
            return app

        # Fallback partial matching
        return next(
            (
                app
                for app in self._all_applications
                if any(
                    normalized_id in (getattr(app, attr, None) or "").lower()
                    for attr in (
                        "name",
                        "display_name",
                        "window_class",
                        "executable",
                        "command_line",
                    )
                )
            ),
            None,
        )
