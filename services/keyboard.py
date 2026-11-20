import glob
import json

from fabric.core.service import Property, Service
from gi.repository import GLib
from loguru import logger

from utils.hyprland import hyprland_service

CAPS_LED_GLOB = "/sys/class/leds/*::capslock/brightness"
NUM_LED_GLOB = "/sys/class/leds/*::numlock/brightness"
POLL_MS = 200
# without LEDs, read Hyprland's devices every this many polls (1 s)
DEVICES_POLL_EVERY = 5
# look for lock LEDs appearing (or disappearing) every this many polls
RESCAN_EVERY = 25


def _led_state(paths: list[str]) -> bool:
    """True if any of *paths* reads as lit; unreadable LEDs are ignored."""
    on = False
    for path in paths:
        try:
            with open(path) as f:
                on = on or f.read().strip() not in ("", "0")
        except OSError:
            pass  # unplugged; dropped at the next rescan
    return on


class KeyboardService(Service):
    """Service for managing keyboard layout and lock-key state."""

    def __init__(self, **kwargs):
        self._layouts: list[str] = []
        self._layout_index = 0
        self._layout_name = ""
        self._caps_lock = False
        self._num_lock = False
        self._caps_leds = glob.glob(CAPS_LED_GLOB)
        self._num_leds = glob.glob(NUM_LED_GLOB)
        self._polls = 0
        super().__init__(**kwargs)

        self._connection = hyprland_service
        self._connection.connect("event::activelayout", lambda *_: self.refresh())
        # keyboards come and go (and Hyprland reloads its config)
        self._connection.connect("event::configreloaded", lambda *_: self.refresh())
        self._connection.on_ready(self.refresh)
        GLib.timeout_add(POLL_MS, self._poll_locks)

    @Property(list, "readable")
    def layouts(self) -> list[str]:
        """Layout codes of the main keyboard, e.g. ["us", "ara"]."""
        return self._layouts

    @Property(int, "readable", default_value=0)
    def layout_index(self) -> int:
        return self._layout_index

    @Property(str, "readable")
    def layout_name(self) -> str:
        """The active layout's name, e.g. "English (US)"."""
        return self._layout_name

    @property
    def layout_code(self) -> str:
        if 0 <= self._layout_index < len(self._layouts):
            return self._layouts[self._layout_index].upper()
        return ""

    @Property(bool, "readable", default_value=False)
    def caps_lock(self) -> bool:
        return self._caps_lock

    @Property(bool, "readable", default_value=False)
    def num_lock(self) -> bool:
        return self._num_lock

    def next_layout(self):
        self._connection.send_command("switchxkblayout current next")

    def _main_keyboard(self) -> dict | None:
        try:
            keyboards = json.loads(self._connection.send_command("j/devices").reply)[
                "keyboards"
            ]
        except Exception as e:
            logger.error(f"[Keyboard] Couldn't read devices: {e}")
            return None
        return next((k for k in keyboards if k.get("main")), None) or (
            keyboards[0] if keyboards else None
        )

    def refresh(self):
        keyboard = self._main_keyboard()
        if keyboard is None:
            return
        layouts = [code for code in keyboard.get("layout", "").split(",") if code]
        index = keyboard.get("active_layout_index", 0)
        name = keyboard.get("active_keymap", "")
        if layouts != self._layouts:
            self._layouts = layouts
            self.notify("layouts")
        if index != self._layout_index:
            self._layout_index = index
            self.notify("layout-index")
        if name != self._layout_name:
            self._layout_name = name
            self.notify("layout-name")
        self._sync_locks(keyboard)

    def _sync_locks(self, keyboard: dict) -> None:
        """Take lock state from the LEDs when present, else from Hyprland."""
        caps = (
            _led_state(self._caps_leds)
            if self._caps_leds
            else bool(keyboard.get("capsLock"))
        )
        num = (
            _led_state(self._num_leds)
            if self._num_leds
            else bool(keyboard.get("numLock"))
        )
        self._set_locks(caps, num)

    def _poll_locks(self) -> bool:
        self._polls += 1
        if self._polls % RESCAN_EVERY == 0:
            self._caps_leds = glob.glob(CAPS_LED_GLOB)
            self._num_leds = glob.glob(NUM_LED_GLOB)

        needs_devices = not self._caps_leds or not self._num_leds
        if needs_devices and self._polls % DEVICES_POLL_EVERY == 0:
            keyboard = self._main_keyboard()
            if keyboard is not None:
                self._sync_locks(keyboard)
            return True

        caps = _led_state(self._caps_leds) if self._caps_leds else self._caps_lock
        num = _led_state(self._num_leds) if self._num_leds else self._num_lock
        self._set_locks(caps, num)
        return True

    def _set_locks(self, caps: bool, num: bool):
        if caps != self._caps_lock:
            self._caps_lock = caps
            self.notify("caps-lock")
        if num != self._num_lock:
            self._num_lock = num
            self.notify("num-lock")
