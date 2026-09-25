from fabric.core.service import Signal
from fabric.utils import exec_shell_command_async, logger

from utils.functions import run_command

from .base import PollingController, SingletonService


class CloudflareWarpService(SingletonService):
    """Manage Cloudflare WARP connection status (polls ``warp-cli status``)."""

    @Signal
    def changed(self) -> None:
        """Emitted when connection state changes."""

    def __init__(self, poll_interval_ms: int = 5000, **kwargs):
        super().__init__(**kwargs)

        self._poll_interval = poll_interval_ms
        self._connected = False

        self._poller = PollingController(
            ["warp-cli", "status"],
            poll_interval_ms,
            self._on_status_line,
            tag="CloudflareWARP",
        )
        self._poller.start()

    # ── Properties ──────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        return self._connected

    # ── Polling ─────────────────────────────────────────────────

    def pause_polling(self):
        """Pause the polling loop. Safe to call when already paused."""
        self._poller.stop()

    def resume_polling(self):
        """Resume the polling loop. Safe to call when already running."""
        self._poller.start()

    def _on_status_line(self, line: str):
        raw = line.strip()
        if not raw:
            return

        was = self._connected

        if "Connected" in raw:
            self._connected = True
        elif "Disconnected" in raw:
            self._connected = False
        else:
            return  # Unknown line, keep current state

        if was != self._connected:
            logger.info(
                f"[CloudflareWARP] {'Connected' if self._connected else 'Disconnected'}"
            )
            self.emit("changed")

    # ── Actions ─────────────────────────────────────────────────

    def _run_warp_cli(self, action: str) -> bool:
        """Run a warp-cli command synchronously. Returns success."""
        return run_command(["warp-cli", action]) is not None

    def connect_warp(self) -> bool:
        ok = self._run_warp_cli("connect")
        if ok:
            self._connected = True
            self.emit("changed")
            exec_shell_command_async("warp-cli status", self._on_status_line)
        return ok

    def disconnect_warp(self) -> bool:
        ok = self._run_warp_cli("disconnect")
        if ok:
            self._connected = False
            self.emit("changed")
            exec_shell_command_async("warp-cli status", self._on_status_line)
        return ok

    def toggle_warp(self) -> bool:
        return self.disconnect_warp() if self._connected else self.connect_warp()

    # ── Teardown ────────────────────────────────────────────────

    def destroy(self):
        self._stop_polling()
        return super().destroy()


# Singleton instance
cloudflare_warp_service = CloudflareWarpService()
