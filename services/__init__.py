"""Lazy-loaded services, initialized on first access (faster startup)."""

import threading

# Internal cache for lazy-loaded services
_services_cache = {}
_services_cache_lock = threading.Lock()


def _get_service(name: str, factory):
    """Lazy-load a service on first access (thread-safe)."""
    with _services_cache_lock:
        if name not in _services_cache:
            _services_cache[name] = factory()
        return _services_cache[name]


def get_audio_service():
    """Get the audio service (lazy-loaded)."""
    from fabric.audio import Audio

    return _get_service("audio", Audio)


def get_notification_service():
    """Get the notification service (lazy-loaded)."""
    from .custom_notification import CustomNotifications

    return _get_service("notification", CustomNotifications)


def get_bluetooth_service():
    """Get the bluetooth service (lazy-loaded)."""
    from fabric.bluetooth import BluetoothClient

    return _get_service("bluetooth", BluetoothClient)


def get_power_profiles_service():
    """Get the power profiles service (lazy-loaded)."""
    from fabric.power_profiles import PowerProfiles

    return _get_service("power_profiles", PowerProfiles)


def get_matugen_service():
    """Get the matugen service (lazy-loaded)."""
    from .matugen import MatugenService

    return _get_service("matugen", MatugenService)


def get_style_service():
    """Get the style service (lazy-loaded)."""
    from .style import StyleService

    return _get_service("style", StyleService)


def get_note_service():
    """Get the note service (lazy-loaded)."""
    from .notes import NotesService

    return _get_service("note", NotesService)

def get_caffeine_service():
    """Get the caffeine service (lazy-loaded)."""
    from .caffeine import Caffeine

    return _get_service("caffeine", Caffeine)

def get_keyboard_service():
    """Get the keyboard service (lazy-loaded)."""
    from .keyboard import KeyboardService

    return _get_service("keyboard", KeyboardService)


# Backward compatibility - these now trigger lazy loading on access
class _LazyServiceProxy:
    """Proxy that lazily loads a service on first attribute access (thread-safe)."""

    def __init__(self, getter):
        object.__setattr__(self, "_getter", getter)
        object.__setattr__(self, "_service", None)
        object.__setattr__(self, "_lock", threading.Lock())

    def _ensure_loaded(self):
        lock = object.__getattribute__(self, "_lock")
        with lock:
            if object.__getattribute__(self, "_service") is None:
                getter = object.__getattribute__(self, "_getter")
                object.__setattr__(self, "_service", getter())
        return object.__getattribute__(self, "_service")

    def __getattr__(self, name):
        return getattr(self._ensure_loaded(), name)

    def __setattr__(self, name, value):
        setattr(self._ensure_loaded(), name, value)


# Backward-compatible lazy proxies
audio_service = _LazyServiceProxy(get_audio_service)
notification_service = _LazyServiceProxy(get_notification_service)
bluetooth_service = _LazyServiceProxy(get_bluetooth_service)
power_profile_service = _LazyServiceProxy(get_power_profiles_service)
note_service = _LazyServiceProxy(get_note_service)
matugen_service = _LazyServiceProxy(get_matugen_service)
style_service = _LazyServiceProxy(get_style_service)
caffeine_service = _LazyServiceProxy(get_caffeine_service)
keyboard_service = _LazyServiceProxy(get_keyboard_service)
