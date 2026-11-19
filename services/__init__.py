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


def get_dns_switcher_service():
    """Get the DNS switcher service (lazy-loaded)."""
    from .dns_switcher import DnsSwitcherService

    return _get_service("dns_switcher", DnsSwitcherService)


def get_bluetooth_service():
    """Get the bluetooth service (lazy-loaded)."""
    from fabric.bluetooth import BluetoothClient

    return _get_service("bluetooth", BluetoothClient)


def get_power_profiles_service():
    """Get the power profiles service (lazy-loaded)."""
    from fabric.power_profiles import PowerProfiles

    return _get_service("power_profiles", PowerProfiles)


def get_quotes_service():
    """Get the quotes service (lazy-loaded)."""
    from .quotes import QuotesService

    return _get_service("quotes", QuotesService)


def get_network_service():
    """Get the network service (lazy-loaded)."""
    from .network import NetworkService

    return _get_service("network", NetworkService)


def get_cloudflare_warp_service():
    """Get the cloudflare warp service (lazy-loaded)."""
    from .cloudflare_warp import CloudflareWarpService

    return _get_service("cloudflare_warp", CloudflareWarpService)


def get_matugen_service():
    """Get the matugen service (lazy-loaded)."""
    from .matugen import MatugenService

    return _get_service("matugen", MatugenService)


def get_networkspeed_service():
    """Get the network speed service (lazy-loaded)."""
    from services.networkspeed import NetworkSpeed

    # NetworkSpeed is a SingletonMixin, not a fabric.Service, so each call
    # returns the shared singleton. Kept here for import visibility.
    return NetworkSpeed()


def get_style_service():
    """Get the style service (lazy-loaded)."""
    from .style import StyleService

    return _get_service("style", StyleService)


def get_note_service():
    """Get the note service (lazy-loaded)."""
    from .desktop_notes import NotesService

    return _get_service("note", NotesService)


def get_caffeine_service():
    """Get the caffeine service (lazy-loaded)."""
    from .caffeine import Caffeine

    return _get_service("caffeine", Caffeine)


def get_cava_service():
    """Get the cava service (lazy-loaded)."""
    from .cava import CavaService

    return _get_service("cava", CavaService)


def get_keyboard_service():
    """Get the keyboard service (lazy-loaded)."""
    from .keyboard import KeyboardService

    return _get_service("keyboard", KeyboardService)


def get_brightness_service():
    """Get the brightness service (lazy-loaded)."""
    from .brightness import BrightnessService

    return _get_service("brightness", BrightnessService)


def get_battery_service():
    """Get the battery service (lazy-loaded)."""
    from .battery import BatteryService

    return _get_service("battery", BatteryService)


def get_recorder_service():
    """Get the recorder service (lazy-loaded)."""
    from .screen_record import ScreenRecorderService

    return _get_service("recorder", ScreenRecorderService)


def get_weather_service():
    """Get the weather service (lazy-loaded)."""
    from .weather import WeatherService

    return _get_service("weather", WeatherService)


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


audio_service = _LazyServiceProxy(get_audio_service)
battery_service = _LazyServiceProxy(get_battery_service)
bluetooth_service = _LazyServiceProxy(get_bluetooth_service)
brightness_service = _LazyServiceProxy(get_brightness_service)
cava_service = _LazyServiceProxy(get_cava_service)
caffeine_service = _LazyServiceProxy(get_caffeine_service)
keyboard_service = _LazyServiceProxy(get_keyboard_service)
note_service = _LazyServiceProxy(get_note_service)
matugen_service = _LazyServiceProxy(get_matugen_service)
notification_service = _LazyServiceProxy(get_notification_service)
power_profile_service = _LazyServiceProxy(get_power_profiles_service)
recorder_service = _LazyServiceProxy(get_recorder_service)
style_service = _LazyServiceProxy(get_style_service)
weather_service = _LazyServiceProxy(get_weather_service)

# Additional services that are not yet exposed as top-level lazy proxies
# (import from the submodule instead; see examples above).
dns_switcher_service = _LazyServiceProxy(get_dns_switcher_service)
quotes_service = _LazyServiceProxy(get_quotes_service)
network_service = _LazyServiceProxy(get_network_service)
cloudflare_warp_service = _LazyServiceProxy(get_cloudflare_warp_service)
networkspeed_service = _LazyServiceProxy(get_networkspeed_service)
