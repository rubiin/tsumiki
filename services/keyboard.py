import glob
import json

from fabric.core.service import Property, Service
from gi.repository import GLib
from loguru import logger

from utils.hyprland import hyprland_service

CAPS_LED_GLOB = "/sys/class/leds/*::capslock/brightness"
POLL_MS = 200
# without LEDs, read Hyprland's devices every this many polls (1 s)
DEVICES_POLL_EVERY = 5
# look for keyboards plugged in (or out) every this many LED polls
RESCAN_EVERY = 25


class Keyboard(Service):
    """Service for managing keyboard layout and Caps Lock state."""

    def __init__(self, **kwargs):
        self._layouts: list[str] = []
        self._layout_index = 0
        self._layout_name = ""
        self._caps_lock = False
        self._leds = glob.glob(CAPS_LED_GLOB)
        self._polls = 0
        super().__init__(**kwargs)

        self._connection = hyprland_service
        self._connection.connect("event::activelayout", lambda *_: self.refresh())
        # keyboards come and go (and Hyprland reloads its config)
        self._connection.connect("event::configreloaded", lambda *_: self.refresh())
        self.refresh()
        GLib.timeout_add(POLL_MS, self._poll_caps_lock)

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
        if not self._leds:
            self._set_caps_lock(bool(keyboard.get("capsLock")))

    def _poll_caps_lock(self) -> bool:
        self._polls += 1
        if self._polls % RESCAN_EVERY == 0:
            self._leds = glob.glob(CAPS_LED_GLOB)
        if not self._leds:
            # no LEDs to read: ask Hyprland, less often
            if self._polls % DEVICES_POLL_EVERY == 0:
                keyboard = self._main_keyboard()
                if keyboard is not None:
                    self._set_caps_lock(bool(keyboard.get("capsLock")))
            return True
        on = False
        for path in self._leds:
            try:
                with open(path) as f:
                    on = on or f.read().strip() not in ("", "0")
            except OSError:
                pass  # unplugged; dropped at the next rescan
        self._set_caps_lock(on)
        return True

    def _set_caps_lock(self, on: bool):
        if on != self._caps_lock:
            self._caps_lock = on
            self.notify("caps-lock")
