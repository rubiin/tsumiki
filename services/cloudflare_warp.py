from functools import partial

from fabric.core.service import Signal
from fabric.utils import exec_shell_command_async, logger

from utils.decorators import run_worker_with_idle
from utils.functions import run_command

from .base import PollingController, SingletonService

# A toggle whose daemon is wedged must settle; the poller still reports the truth.
_WARP_CLI_TIMEOUT = 30.0


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

    def _warp_cli(self, action: str) -> bool:
        """Worker: ``warp-cli connect`` blocks on the warp-svc daemon for seconds."""
        return run_command(["warp-cli", action], timeout=_WARP_CLI_TIMEOUT) is not None

    def _run_warp_cli(self, action: str, connected: bool) -> None:
        """Dispatch *action* off-thread and publish the outcome on the main loop."""
        # Bind the target state so the idle callback only carries the success flag.
        run_worker_with_idle(
            self._warp_cli,
            partial(self._on_warp_cli_finished, connected=connected),
            action,
        )

    def _on_warp_cli_finished(self, ok: bool, connected: bool) -> None:
        if not ok:
            return  # run_command already logged why; the poller keeps state honest.
        self._connected = connected
        self.emit("changed")
        exec_shell_command_async("warp-cli status", self._on_status_line)

    def connect_warp(self) -> None:
        """Start ``warp-cli connect``; ``changed`` fires once it has actually run."""
        self._run_warp_cli("connect", True)

    def disconnect_warp(self) -> None:
        """Start ``warp-cli disconnect``; ``changed`` fires once it has actually run."""
        self._run_warp_cli("disconnect", False)

    def toggle_warp(self) -> None:
        if self._connected:
            self.disconnect_warp()
        else:
            self.connect_warp()

    # ── Teardown ────────────────────────────────────────────────

    def destroy(self):
        self._stop_polling()
        return super().destroy()


# Singleton instance
cloudflare_warp_service = CloudflareWarpService()
