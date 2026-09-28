from functools import partial

from fabric.core.service import Signal
from fabric.utils import exec_shell_command_async, logger

from utils.decorators import run_worker_with_idle
from utils.functions import run_command

from .base import IGNORED, PolledCommandService

# A toggle whose daemon is wedged must settle; the poller still reports the truth.
_WARP_CLI_TIMEOUT = 30.0

# WARP status only changes when someone connects or disconnects, and each poll
# is a round-trip to warp-svc: at 5 s it was 17,280 spawns a day for a button.
_STATUS_INTERVAL_MS = 30_000


class CloudflareWarpService(PolledCommandService):
    """Manage Cloudflare WARP connection status (polls ``warp-cli status``)."""

    @Signal
    def changed(self) -> None:
        """Emitted when connection state changes."""

    def __init__(self, poll_interval_ms: int = _STATUS_INTERVAL_MS, **kwargs):
        super().__init__(
            ["warp-cli", "status"],
            poll_interval_ms,
            "_on_status_line",
            tag="CloudflareWARP",
            state=False,
            **kwargs,
        )

    # ── Properties ──────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        return bool(self._state)

    # ── Parsing ─────────────────────────────────────────────────

    def _on_status_line(self, line: str):
        raw = line.strip()
        if not raw:
            return IGNORED
        if "Connected" in raw:
            return True
        if "Disconnected" in raw:
            return False
        return IGNORED  # Unknown line, keep current state

    def _on_state_changed(self, value) -> None:
        logger.info(f"[CloudflareWARP] {'Connected' if value else 'Disconnected'}")

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
        self._set_state(connected)
        exec_shell_command_async("warp-cli status", self._on_line)

    def connect_warp(self) -> None:
        """Start ``warp-cli connect``; ``changed`` fires once it has actually run."""
        self._run_warp_cli("connect", True)

    def disconnect_warp(self) -> None:
        """Start ``warp-cli disconnect``; ``changed`` fires once it has actually run."""
        self._run_warp_cli("disconnect", False)

    def toggle_warp(self) -> None:
        if self.connected:
            self.disconnect_warp()
        else:
            self.connect_warp()


# Singleton instance
cloudflare_warp_service = CloudflareWarpService()
