import re
from collections.abc import Callable

import gi
from fabric.core.service import Property, Signal
from fabric.utils import GLib, exec_shell_command, exec_shell_command_async, logger

from utils.decorators import run_worker_with_idle

from .base import IGNORED, PolledCommandService

try:  # Optional: without the bindings the safety-net poll alone keeps this alive.
    gi.require_version("NM", "1.0")
    from gi.repository import NM
except (ImportError, ValueError):
    NM = None

# Matches valid IPv4, IPv6, or hostname — blocks shell metacharacters.
_DNS_VALUE_RE = re.compile(r"^[a-zA-Z0-9.:\[\]-]+$")

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")

# A safety net only, since NM signals drive the real updates: at 3 s it was
# 28,800 nmcli spawns a day for a label that changes a few times a day.
_POLL_INTERVAL_MS = 30_000


def _is_valid_dns_value(value: str) -> bool:
    """Return True if *value* looks like an IP address or hostname."""
    return bool(_DNS_VALUE_RE.match(value))


# Pre-configured DNS providers with label, primary, secondary
DEFAULT_PROVIDERS = [
    {"label": "Cloudflare", "primary": "1.1.1.1", "secondary": "1.0.0.1"},
    {"label": "Google", "primary": "8.8.8.8", "secondary": "8.8.4.4"},
    {"label": "OpenDNS", "primary": "208.67.222.222", "secondary": "208.67.220.220"},
    {"label": "AdGuard", "primary": "94.140.14.14", "secondary": "94.140.15.15"},
    {"label": "Quad9", "primary": "9.9.9.9", "secondary": "149.112.112.112"},
]


def _label_for(dns: str | None) -> str:
    """Name a known provider, fall back to the address, or report the default."""
    if not dns:
        return "Default"
    for provider in DEFAULT_PROVIDERS:
        if provider["primary"] == dns:
            return provider["label"]
    return dns


class DnsSwitcherService(PolledCommandService):
    """Detect and switch DNS servers via NetworkManager (polls ``nmcli``)."""

    _dns_line_re = None

    @Signal
    def changed(self) -> None:
        """Emitted when the current DNS server changes."""

    def _get_dns_line_re(self):
        if self._dns_line_re is None:
            self.__class__._dns_line_re = re.compile(r"IP4\.DNS\[\d+\]:\s*(\S+)")
        return self._dns_line_re

    def __init__(self, poll_interval_ms: int = _POLL_INTERVAL_MS, **kwargs):
        super().__init__(
            # ``IP4.DNS`` is a device field, not a connection field, so ``con`` fails.
            ["nmcli", "-t", "-f", "IP4.DNS", "dev", "show"],
            poll_interval_ms,
            "_on_dns_line",
            tag="DNS",
            on_start=self._mark_poll_start,
            **kwargs,
        )
        self._current_label = "Default"
        self._first_line_of_poll = True
        self._nm_client = None
        self._nm_handlers: list[tuple] = []
        self._watch_network_manager()

    # ── Properties ──────────────────────────────────────────────

    @Property(str, "readable", default_value="Default")
    def current(self) -> str:
        return self._state or "Default"

    # ── NetworkManager signals ──────────────────────────────────

    def _watch_network_manager(self) -> None:
        """Follow the active connection so a DNS change does not wait on a poll.

        NM exposes no ``dns`` property, so a new IP config on the connection or
        on one of its devices is the signal that the servers have moved.
        """
        if NM is None:
            logger.info("[DNS] NM bindings unavailable; falling back to polling")
            return
        NM.Client.new_async(cancellable=None, callback=self._on_nm_client)

    def _on_nm_client(self, client, _task, *_args) -> None:
        if client is None:
            # No NM daemon to talk to; the safety-net poll carries the service.
            return
        self._nm_client = client
        client.connect("notify::primary-connection", self._on_primary_connection)
        self._on_primary_connection()

    def _on_primary_connection(self, *_args) -> None:
        self._disconnect_nm()
        connection = self._nm_client.get_primary_connection()
        if connection is not None:
            self._connect_nm(connection, "notify::ip4-config")
            for device in connection.get_devices():
                self._connect_nm(device, "notify::ip4-config")
        self._on_nm_dns_changed()

    def _connect_nm(self, target, signal: str) -> None:
        handler = target.connect(signal, self._on_nm_dns_changed)
        self._nm_handlers.append((target, handler))

    def _disconnect_nm(self) -> None:
        for target, handler in self._nm_handlers:
            target.disconnect(handler)
        self._nm_handlers.clear()

    def _on_nm_dns_changed(self, *_args) -> None:
        # Re-read through nmcli rather than parsing NM: one parser, one truth.
        self._poller.poll_now()

    def destroy(self) -> None:
        """Drop the NM handlers, then stop the poller the base owns."""
        self._disconnect_nm()
        super().destroy()

    # ── Parsing ─────────────────────────────────────────────────

    def _mark_poll_start(self) -> None:
        """Reset the per-run state before each nmcli invocation."""
        self._first_line_of_poll = True

    def _on_dns_line(self, line: str):
        # Called once per stdout line; only the first carries the primary DNS.
        if not self._first_line_of_poll:
            return IGNORED
        self._first_line_of_poll = False

        raw = line.strip()
        if not raw:
            return None  # nmcli printed no DNS field, so the device has none

        match = self._get_dns_line_re().search(raw)
        return match.group(1) if match else IGNORED

    def _on_state_changed(self, value) -> None:
        self._current_label = _label_for(value)
        self.notify("current")

    # ── Actions ─────────────────────────────────────────────────

    def _query_active_connection(self) -> str:
        """Worker: ``nmcli con show`` blocks the caller for ~100ms."""
        output = exec_shell_command("nmcli -t -f UUID con show --active") or ""
        # nmcli returns the error text on a non-zero exit, so only a real UUID counts.
        for line in output.splitlines():
            candidate = line.strip()
            if _UUID_RE.match(candidate):
                return candidate
        return ""

    def _with_active_connection(self, on_found: Callable[[str], None]) -> None:
        """Resolve the UUID off-thread, then continue *on_found* on the main loop."""

        def apply(uuid: str) -> None:
            if not uuid:
                logger.warning("[DNS] No active NetworkManager connection found")
                return
            on_found(uuid)

        run_worker_with_idle(self._query_active_connection, apply)

    def _run_commands(
        self, commands: list[list[str]], on_finished: Callable[[bool], None]
    ) -> None:
        """Run *commands* one after another, then report whether all succeeded.

        A list, not a ``&&`` chain: ``exec_shell_command_async`` uses no shell, so
        ``&&`` would arrive as a literal argument and drop every later step.
        """

        def step(index: int):
            if index >= len(commands):
                on_finished(True)
                return

            argv = commands[index]
            try:
                process, _ = exec_shell_command_async(argv)
            except GLib.Error as e:
                logger.warning(f"[DNS] {' '.join(argv)} failed to start: {e.message}")
                on_finished(False)
                return

            def finished(proc, res, index=index):
                try:
                    status = proc.wait_finish(res)
                except GLib.Error:
                    status = -1
                if status != 0:
                    logger.warning(
                        f"[DNS] {' '.join(commands[index])} failed (status {status})"
                    )
                    on_finished(False)
                    return
                step(index + 1)

            process.wait_async(None, finished)

        step(0)

    def _on_switch_finished(self, ok: bool):
        """Publish a switch only once its commands have actually run."""
        if not ok:
            # Nothing was applied. The poller keeps ``current`` honest.
            return
        self.emit("changed")

    def set_dns(self, primary: str, secondary: str = ""):
        """Switch to the given DNS servers via pkexec nmcli."""
        if not _is_valid_dns_value(primary) or (
            secondary and not _is_valid_dns_value(secondary)
        ):
            logger.warning(
                f"[DNS] Rejected invalid DNS value: "
                f"primary={primary!r} secondary={secondary!r}"
            )
            return

        servers = primary
        if secondary:
            servers = f"{primary} {secondary}"

        # Validated up front so a bad value never pays for the nmcli lookup.
        self._with_active_connection(
            lambda uuid: self._run_commands(
                self._switch_commands(uuid, servers, "yes"),
                self._on_switch_finished,
            )
        )

    @staticmethod
    def _switch_commands(uuid: str, servers: str, ignore_auto: str) -> list[list[str]]:
        """The nmcli steps that set the servers and bounce the connection."""
        return [
            ["pkexec", "nmcli", "con", "mod", uuid, "ipv4.dns", servers],
            [
                "pkexec",
                "nmcli",
                "con",
                "mod",
                uuid,
                "ipv4.ignore-auto-dns",
                ignore_auto,
            ],
            ["nmcli", "con", "down", uuid],
            ["nmcli", "con", "up", uuid],
        ]

    def switch_provider(self, index: int):
        """Switch to a pre-configured provider by index."""
        if 0 <= index < len(DEFAULT_PROVIDERS):
            prov = DEFAULT_PROVIDERS[index]
            self.set_dns(prov["primary"], prov["secondary"])

    def reset_to_default(self):
        """Reset DNS to ISP default (auto)."""
        # An empty value clears the list, which is what the shell form '' meant.
        self._with_active_connection(
            lambda uuid: self._run_commands(
                self._switch_commands(uuid, "", "no"),
                self._on_switch_finished,
            )
        )


dns_switcher_service = DnsSwitcherService()
