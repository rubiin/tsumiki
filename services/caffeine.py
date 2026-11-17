"""
Caffeine: keeps the screen from idling (dimming, locking, sleeping).

While on, it holds a logind "idle" inhibitor lock, which hypridle honours. The
lock is a file descriptor: closing it releases the lock, and so does fabric
exiting or crashing, so the screen can never be left awake by accident.
"""

import os

from fabric.core.service import Property, Service
from gi.repository import Gio, GLib
from loguru import logger


class Caffeine(Service):
    """Service to keep the screen awake by holding a logind idle inhibitor lock."""

    def __init__(self, **kwargs):
        self._fd: int | None = None
        super().__init__(**kwargs)

    @Property(bool, "read-write", default_value=False)
    def active(self) -> bool:
        return self._fd is not None

    @active.setter
    def active(self, value: bool):
        if value == self.active:
            return
        if value:
            self._fd = _take_idle_lock()
        else:
            os.close(self._fd)  # type: ignore[arg-type]
            self._fd = None
        self.notify("active")


def _take_idle_lock() -> int | None:
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        reply, fd_list = bus.call_with_unix_fd_list_sync(
            "org.freedesktop.login1",
            "/org/freedesktop/login1",
            "org.freedesktop.login1.Manager",
            "Inhibit",
            GLib.Variant("(ssss)", ("idle", "Fabric", "Caffeine is on", "block")),
            GLib.VariantType("(h)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None,
        )
    except GLib.Error as e:
        logger.error(f"[Caffeine] Couldn't take the idle lock: {e.message}")
        return None
    # steal the fds so the list doesn't close the lock when it's freed
    fds = fd_list.steal_fds()
    index = reply.unpack()[0]
    for i, fd in enumerate(fds):
        if i != index:
            os.close(fd)
    return fds[index]
