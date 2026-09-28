"""Launcher slash command: /history — search shell history (bash/zsh/fish).

Press Enter to copy a command back to the clipboard — nothing is executed.
"""

import os
import re
from collections.abc import Callable
from typing import ClassVar

from utils.plugin_manager import LauncherPlugin, PluginResult, copy_to_clipboard

_MAX_RESULTS = 24
#: Preview length of a command row in the launcher.
_PREVIEW_LENGTH = 100

#: Extended zsh history prefix: ``: <epoch>:<seconds>;<command>``
_ZSH_EXTENDED_RE = re.compile(r"^:\s*(\d+):\d*;(.*)$")


def default_history_files() -> list[str]:
    """Return the history file paths to scan (bash, zsh, fish, ``$HISTFILE``)."""
    home = os.path.expanduser("~")
    files = [
        os.environ.get("HISTFILE", ""),
        f"{home}/.bash_history",
        f"{home}/.zsh_history",
        f"{home}/.local/share/fish/fish_history",
    ]
    return [path for path in files if path]


def parse_bash_history(content: str) -> list[tuple[int, str]]:
    """Return ``[(line_ordinal, command)]``; later lines rank as more recent."""
    return [
        (index + 1, line.strip())
        for index, line in enumerate(content.splitlines())
        if line.strip() and not line.startswith("#")
    ]


def parse_zsh_history(content: str) -> list[tuple[int, str]]:
    """Return ``[(epoch, command)]``; handles plain and extended zsh formats."""
    entries: list[tuple[int, str]] = []
    for index, line in enumerate(content.splitlines()):
        if not line.strip() or line.startswith("#"):
            continue
        match = _ZSH_EXTENDED_RE.match(line)
        if match:
            entries.append((int(match.group(1)), match.group(2).strip()))
        else:
            entries.append((index + 1, line.strip()))
    return entries


def parse_fish_history(content: str) -> list[tuple[int, str]]:
    """Return ``[(epoch, command)]`` from a fish_history file (YAML-ish)."""
    entries: list[tuple[int, str]] = []
    cmd: str | None = None
    when = 0
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("- cmd:"):
            if cmd is not None and cmd:
                entries.append((when, cmd))
            cmd = stripped[len("- cmd:") :].strip()
            when = 0
        elif cmd is not None and stripped.startswith("when:"):
            try:
                when = int(stripped[len("when:") :].strip())
            except ValueError:
                when = 0
    if cmd:
        entries.append((when, cmd))
    return entries


def match_commands(
    commands: list[str],
    query: str,
    cancelled: Callable[[], bool] | None = None,
) -> list[str]:
    """Return the commands containing *query*, stopping when cancelled.

    The check precedes the per-command ``casefold``, which copies and scans
    every history line — thousands of entries on a busy shell.
    """
    matches: list[str] = []
    for cmd in commands:
        if cancelled is not None and cancelled():
            break
        if query in cmd.casefold():
            matches.append(cmd)
    return matches


def load_history(
    paths: list[str] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> list[str]:
    """Return de-duplicated commands, most recent first, across all files.

    Pass *cancelled* to stop before reading the next history file; a partial
    merge is fine because the launcher drops results from superseded queries.
    """
    merged: list[tuple[int, int, str]] = []
    order = 0
    for path in paths or default_history_files():
        # Checked per file: one check saves a whole read plus parse.
        if cancelled is not None and cancelled():
            break
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as file:
                content = file.read()
        except OSError:
            continue
        if path.endswith("fish_history"):
            entries = parse_fish_history(content)
        elif path.endswith(".zsh_history"):
            entries = parse_zsh_history(content)
        else:
            entries = parse_bash_history(content)
        for recency, cmd in entries:
            if cancelled is not None and cancelled():
                break
            if cmd:
                merged.append((recency, order, cmd))
            order += 1

    # (recency, file order); larger = more recent. Duplicates keep the newest.
    best: dict[str, tuple[int, int]] = {}
    for recency, order, cmd in merged:
        key = (recency, order)
        if cmd not in best or key > best[cmd]:
            best[cmd] = key
    ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)
    return [cmd for cmd, _ in ranked]


class HistoryPlugin(LauncherPlugin):
    """Slash command: /history — search shell history, copy on Enter."""

    name = "history"
    description = "Search your shell command history"
    icon = "utilities-terminal-symbolic"
    aliases: ClassVar[list[str]] = ["h", "hist"]
    # Every keystroke re-reads and re-parses whole history files; let typing settle.
    debounce_ms = 400

    def handle(self, args: str) -> list[PluginResult]:
        query = args.strip().casefold()
        if self.is_cancelled():
            return []  # superseded before we started reading
        commands = load_history(cancelled=self.is_cancelled)
        if not commands:
            return [
                PluginResult(
                    "No shell history found",
                    subtitle="No bash/zsh/fish history file was readable",
                    icon="dialog-info-symbolic",
                )
            ]
        if query:
            commands = match_commands(commands, query, cancelled=self.is_cancelled)
        if not commands:
            return [
                PluginResult(
                    f"No history entry matches '{args.strip()}'",
                    icon="dialog-warning-symbolic",
                )
            ]

        rows = []
        for cmd in commands[:_MAX_RESULTS]:
            preview = " ".join(cmd.split())
            if len(preview) > _PREVIEW_LENGTH:
                preview = preview[: _PREVIEW_LENGTH - 3] + "..."
            rows.append(
                PluginResult(
                    preview,
                    subtitle="Press Enter to copy the command",
                    icon=self.icon,
                    data=cmd,
                )
            )
        return rows

    def execute(self, result: PluginResult | None = None) -> bool:
        if result is not None and result.data:
            copy_to_clipboard(str(result.data))
        return False  # close the launcher after copying
