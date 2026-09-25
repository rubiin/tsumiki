import re
from collections.abc import Callable

from fabric.core.service import Property, Signal
from fabric.utils import GLib, exec_shell_command_async, logger

from utils.functions import run_command

from .base import SingletonService

# Matches valid IPv4, IPv6, or hostname — blocks shell metacharacters.
_DNS_VALUE_RE = re.compile(r"^[a-zA-Z0-9.:\[\]-]+$")


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

        self._poll_timer_id: int | None = None
        self._poller_running = False
        self._first_line_of_poll = True

        self._start_polling()

    # ── Properties ──────────────────────────────────────────────

    @Property(str, "readable", default_value="Default")
    def current(self) -> str:
        return self._current or "Default"

    # ── Polling ─────────────────────────────────────────────────

    def _start_polling(self):
        if self._poller_running:
            return
        self._poller_running = True
        self._poll()

    def _stop_polling(self):
        self._poller_running = False
        if self._poll_timer_id is not None:
            GLib.source_remove(self._poll_timer_id)
            self._poll_timer_id = None

    def pause_polling(self):
        """Stop polling — call when the widget is destroyed."""
        self._stop_polling()

    def resume_polling(self):
        """Restart polling — call when the widget is created."""
        self._start_polling()

    def _poll(self):
        if not self._poller_running:
            return False

        self._first_line_of_poll = True
        # A list, not a shell string: Fabric runs the argv directly, so a "2>&1"
        # style redirect would arrive as a literal argument.
        exec_shell_command_async(
            ["nmcli", "-t", "-f", "IP4.DNS", "con", "show", "--active"],
            self._on_dns_line,
        )
        self._poll_timer_id = GLib.timeout_add(self._poll_interval, self._poll)
        return False

    def _on_dns_line(self, line: str):
        # exec_shell_command_async calls this once per stdout line.
        # Only use the first line so we capture the primary DNS.
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

        # Parse DNS entries from nmcli output
        dns_ips: list[str] = [m.group(1) for m in self._get_dns_line_re().finditer(raw)]

        if not dns_ips:
            return

        primary = dns_ips[0]
        if primary == self._current:
            return

        was = self._current
        self._current = primary

        # Try to match against known providers
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

    def _get_active_connection(self) -> str:
        """Return the UUID of the active connection, or empty string."""
        output = run_command(
            ["nmcli", "-t", "-f", "UUID", "con", "show", "--active"]
        )
        if output is None:
            return ""
        lines = [line.strip() for line in output.strip().split("\n") if line.strip()]
        return lines[0] if lines else ""

    def _run_commands(
        self, commands: list[list[str]], on_finished: Callable[[bool], None]
    ) -> None:
        """Run *commands* one after another, then report whether all succeeded.

        A list of commands rather than a ``&&`` chain, because Fabric's
        ``exec_shell_command_async`` does not use a shell: it splits the string
        and runs the result directly, so ``&&`` would arrive as a literal
        argument and every step after the first would be silently dropped.
        Sequential because each step depends on the previous one.
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
        uuid = self._get_active_connection()
        if not uuid:
            logger.warning("[DNS] No active NetworkManager connection found")
            return

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

        self._run_commands(
            self._switch_commands(uuid, servers, "yes"),
            self._on_switch_finished,
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
        uuid = self._get_active_connection()
        if not uuid:
            logger.warning("[DNS] No active NetworkManager connection found")
            return

        # An empty value clears the list, which is what the shell form '' meant.
        self._run_commands(
            self._switch_commands(uuid, "", "no"),
            self._on_switch_finished,
        )

    # ── Teardown ────────────────────────────────────────────────

    def destroy(self):
        self._stop_polling()
        return super().destroy()


# Singleton instance
dns_switcher_service = DnsSwitcherService()
