"""Launcher slash command: /kill — search and kill running processes.

SIGTERM by default, SIGKILL with the ``-9`` flag; a numeric query kills
the process listening on that port.
"""

import os
import re
import signal
from collections.abc import Callable
from typing import ClassVar

from fabric.utils import logger

from utils.functions import find_executable
from utils.plugin_manager import (
    LauncherPlugin,
    PluginResult,
    SubprocessTimeoutError,
    run_subprocess,
)

_MAX_RESULTS = 24
# Never offer to kill PID 1 (init) or our own bar process.
_SELF_PID = os.getpid()
_FORCE_FLAGS = {"-9", "--force"}
_PORT_TIMEOUT_SECONDS = 5
_PID_RE = re.compile(r"pid=(\d+)")
_SS_HEADER_RE = re.compile(r"^\s*Netid\b")


def parse_kill_args(args: str) -> tuple[bool, str]:
    """Split a leading -9/--force flag from the process query."""
    tokens = args.strip().split(maxsplit=1)
    if not tokens:
        return False, ""
    flag, rest = tokens[0], tokens[1] if len(tokens) > 1 else ""
    if flag in _FORCE_FLAGS:
        return True, rest.strip()
    return False, args.strip()


def list_processes(
    query: str,
    limit: int = _MAX_RESULTS,
    proc_dir: str = "/proc",
    cancelled: Callable[[], bool] | None = None,
) -> list[tuple[int, str, str]]:
    """Return (pid, comm, cmdline) rows matching *query* against name or cmdline.

    *proc_dir* is injectable so tests need not scan the real ``/proc``. Pass
    *cancelled* to abandon a scan whose rows the launcher would discard anyway.
    """
    query = query.casefold().strip()
    if not query:
        return []
    matches: list[tuple[int, str, str]] = []
    for entry in sorted(os.listdir(proc_dir)):
        # Checked per PID: one check saves the next comm + cmdline read pair.
        if cancelled is not None and cancelled():
            break
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid <= 1 or pid == _SELF_PID:
            continue
        comm = read_comm(pid, proc_dir)
        if not comm:
            continue
        cmdline = _read_cmdline(pid, proc_dir)
        if query in comm.casefold() or query in cmdline.casefold():
            matches.append((pid, comm, cmdline))
        if len(matches) >= limit:
            break
    return matches


def read_comm(pid: int, proc_dir: str = "/proc") -> str:
    """Return the process name of *pid*, or '' if unreadable."""
    try:
        with open(f"{proc_dir}/{pid}/comm", "r", encoding="utf-8") as file:
            return file.read().strip()
    except OSError:
        return ""


def parse_ss_output(output: str, port: int) -> list[int]:
    """Extract listening PIDs for *port* from ``ss -tulpn`` output."""
    pids: set[int] = set()
    for line in output.splitlines():
        if _SS_HEADER_RE.match(line) or not line.strip():
            continue
        match = _PID_RE.search(line)
        if match is None:
            continue
        fields = line.split()
        if len(fields) < 5:
            continue
        # Local Address:Port is the 5th column (Netid State Recv-Q Send-Q Local).
        if fields[4].rsplit(":", 1)[-1] != str(port):
            continue
        pids.add(int(match.group(1)))
    return sorted(pids)


def find_pids_on_port(port: int, runner=None) -> list[int]:
    """Return PIDs listening on *port*; *runner* overrides subprocess running."""
    run = runner or run_subprocess
    ss = find_executable("ss")
    if ss is not None:
        try:
            proc = run(
                [ss, "-tulpn"],
                capture_output=True,
                text=True,
                timeout=_PORT_TIMEOUT_SECONDS,
            )
            if proc.returncode == 0:
                pids = parse_ss_output(proc.stdout, port)
                if pids:
                    return pids
        except (OSError, SubprocessTimeoutError, ValueError):
            pass

    lsof = find_executable("lsof")
    if lsof is not None:
        try:
            proc = run(
                [lsof, f"-tiTCP:{port}", "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
                timeout=_PORT_TIMEOUT_SECONDS,
            )
            if proc.returncode == 0:
                return sorted(
                    {int(pid) for pid in proc.stdout.split() if pid.isdigit()}
                )
        except (OSError, SubprocessTimeoutError, ValueError):
            pass
    return []


def list_port_processes(
    port: int, proc_dir: str = "/proc", runner=None
) -> list[tuple[int, str]]:
    """Return (pid, comm) pairs for the processes listening on *port*."""
    rows = []
    for pid in find_pids_on_port(port, runner=runner):
        comm = read_comm(pid, proc_dir) or f"pid {pid}"
        rows.append((pid, comm))
    return rows


def _read_cmdline(pid: int, proc_dir: str) -> str:
    """Return the command line of *pid* (space-joined), or '' if unreadable."""
    try:
        with open(f"{proc_dir}/{pid}/cmdline", "rb") as file:
            raw = file.read().replace(b"\x00", b" ").decode("utf-8", "replace")
        return raw.strip()
    except OSError:
        return ""


def kill_process(pid: int, force: bool = False) -> str | None:
    """Send SIGTERM (or SIGKILL when *force*); None on success, else an error."""
    try:
        os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
        return None
    except ProcessLookupError:
        return "process already exited"
    except PermissionError:
        return "permission denied (try --force, or run the bar as root)"
    except OSError as exc:
        return str(exc)


class KillPlugin(LauncherPlugin):
    """Slash command: /kill — search running processes and kill one."""

    name = "kill"
    description = "Search and kill a running process"
    icon = "process-stop-symbolic"
    aliases: ClassVar[list[str]] = ["k", "pkill"]
    # A /proc walk is ~2 file reads per process; 150 ms lets every keystroke run one.
    debounce_ms = 400

    def handle(self, args: str) -> list[PluginResult]:
        if not args.strip():
            return [
                PluginResult(
                    "Usage: /kill <process|port>",
                    subtitle=(
                        "e.g. /kill firefox  ·  /kill 3000 (kill the port "
                        "listener)  ·  /kill -9 spotify (SIGKILL)"
                    ),
                    icon=self.icon,
                )
            ]
        if self.is_cancelled():
            return []  # superseded before we started scanning
        force, query = parse_kill_args(args)
        if query.isdigit():
            return self._handle_port(force, query)
        matches = list_processes(query, cancelled=self.is_cancelled)
        if not matches:
            return [
                PluginResult(
                    f"No process matches '{query}'",
                    icon="dialog-warning-symbolic",
                )
            ]
        signal_hint = "SIGKILL" if force else "SIGTERM"
        rows = []
        for pid, comm, cmdline in matches:
            detail = (cmdline or comm)[:100]
            rows.append(
                PluginResult(
                    f"{pid}  {comm}",
                    subtitle=f"{detail} · Enter to send {signal_hint}",
                    icon=self.icon,
                    data=(pid, force),
                )
            )
        return rows

    def _handle_port(self, force: bool, query: str) -> list[PluginResult]:
        """Handle a numeric query: kill the process(es) listening on a port."""
        port = int(query)
        matches = list_port_processes(port, runner=self.run_subprocess)
        if not matches:
            return [
                PluginResult(
                    f"Nothing is listening on port {port}",
                    subtitle="No TCP/UDP listener found",
                    icon="dialog-info-symbolic",
                )
            ]
        signal_hint = "SIGKILL" if force else "SIGTERM"
        rows = []
        for pid, comm in matches:
            rows.append(
                PluginResult(
                    f"Port {port} → {comm} (pid {pid})",
                    subtitle=f"Enter to send {signal_hint}",
                    icon=self.icon,
                    data=(pid, force),
                )
            )
        return rows

    def execute(self, result: PluginResult | None = None) -> bool:
        if result is not None and result.data:
            pid, force = result.data
            error = kill_process(pid, force)
            if error is not None:
                logger.warning(f"[Launcher] /kill {pid} failed: {error}")
        return False  # close the launcher after killing
