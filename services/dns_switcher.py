import re
from collections.abc import Callable

from fabric.core.service import Property, Signal
from fabric.utils import GLib, exec_shell_command, exec_shell_command_async, logger

from utils.decorators import run_worker_with_idle

from .base import PollingController, SingletonService

# Matches valid IPv4, IPv6, or hostname — blocks shell metacharacters.
_DNS_VALUE_RE = re.compile(r"^[a-zA-Z0-9.:\[\]-]+$")

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")


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


class DnsSwitcherService(SingletonService):
    """Detect and switch DNS servers via NetworkManager (polls ``nmcli``)."""

    _dns_line_re = None

    @Signal
    def changed(self) -> None:
        """Emitted every poll cycle regardless of change."""

    def _get_dns_line_re(self):
        if self._dns_line_re is None:
            self.__class__._dns_line_re = re.compile(r"IP4\.DNS\[\d+\]:\s*(\S+)")
        return self._dns_line_re

    def __init__(self, poll_interval_ms: int = 3000, **kwargs):
        super().__init__(**kwargs)

        self._poll_interval = poll_interval_ms
        self._current: str | None = None
        self._current_label: str = "Default"

        self._first_line_of_poll = True

        # ``IP4.DNS`` is a device field, not a connection field, so ``con`` fails.
        self._poller = PollingController(
            ["nmcli", "-t", "-f", "IP4.DNS", "dev", "show"],
            poll_interval_ms,
            self._on_dns_line,
            tag="DNS",
            on_start=self._mark_poll_start,
        )
        self._poller.start()

    # ── Properties ──────────────────────────────────────────────

    @Property(str, "readable", default_value="Default")
    def current(self) -> str:
        return self._current or "Default"

    # ── Polling ─────────────────────────────────────────────────

    def pause_polling(self):
        """Stop polling — call when the widget is destroyed."""
        self._poller.stop()

    def resume_polling(self):
        """Restart polling — call when the widget is created."""
        self._poller.start()

    def _mark_poll_start(self) -> None:
        """Reset the per-run state before each nmcli invocation."""
        self._first_line_of_poll = True

    def _on_dns_line(self, line: str):
        # Called once per stdout line; only the first carries the primary DNS.
        if not self._first_line_of_poll:
            return
        self._first_line_of_poll = False

        raw = line.strip()
        if not raw:
            was = self._current
            self._current = None
            self._current_label = "Default"
            if was != self._current:
                self.notify("current")
                self.emit("changed")
            return

        dns_ips: list[str] = [m.group(1) for m in self._get_dns_line_re().finditer(raw)]

        if not dns_ips:
            return

        primary = dns_ips[0]
        if primary == self._current:
            return

        was = self._current
        self._current = primary

        for prov in DEFAULT_PROVIDERS:
            if prov["primary"] == primary:
                self._current_label = prov["label"]
                break
        else:
            self._current_label = primary

        if was != self._current:
            self.notify("current")
            self.emit("changed")

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

    # ── Teardown ────────────────────────────────────────────────

    def destroy(self):
        self._stop_polling()
        return super().destroy()


dns_switcher_service = DnsSwitcherService()
