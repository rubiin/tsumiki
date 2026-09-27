"""Launcher slash command: /clipboard-history — search clipboard history."""

from typing import ClassVar

from utils.functions import find_executable
from utils.plugin_manager import (
    LauncherPlugin,
    PluginResult,
    copy_to_clipboard,
    run_subprocess,
)

_MAX_RESULTS = 100
_TIMEOUT_SECONDS = 5
# Null/replacement chars usually mean binary content — show a marker.
_BINARY_MARKERS = ("\x00", "\ufffd")


def parse_list(output: str) -> list[tuple[str, str]]:
    """Return [(item_id, content)] from ``cliphist list`` output."""
    items = []
    for line in output.strip().splitlines():
        if not line or "<meta http-equiv" in line:
            continue
        parts = line.split("\t", 1)
        if len(parts) == 2:
            items.append((parts[0], parts[1].strip()))
    return items


def is_binary(content: str) -> bool:
    """Heuristic: True for image/binary clipboard items."""
    return any(marker in content for marker in _BINARY_MARKERS)


class ClipboardHistoryPlugin(LauncherPlugin):
    """Slash command: /clipboard-history — search and re-copy history items."""

    name = "clipboard-history"
    description = "Search clipboard history (cliphist)"
    icon = "edit-paste-symbolic"
    aliases: ClassVar[list[str]] = ["clip", "cb"]  # "history" belongs to /history

    def handle(self, args: str) -> list[PluginResult]:
        query = args.strip().casefold()

        if find_executable("cliphist") is None:
            return [
                PluginResult(
                    "/clipboard-history requires cliphist",
                    subtitle="Install cliphist, e.g. sudo pacman -S cliphist",
                    icon="dialog-error-symbolic",
                )
            ]

        try:
            # Slow on large histories; the helper lets a superseding query kill it.
            result = self.run_subprocess(
                ["cliphist", "list"],
                timeout=_TIMEOUT_SECONDS,
            )
            lines = result.stdout
        except Exception as exc:
            return [
                PluginResult(
                    "Failed to read clipboard history",
                    subtitle=f"{exc}",
                    icon="network-error-symbolic",
                )
            ]
        if result.returncode != 0:
            return [
                PluginResult(
                    "Failed to read clipboard history",
                    subtitle=result.stderr.strip()
                    or f"cliphist failed (exit {result.returncode})",
                    icon="network-error-symbolic",
                )
            ]

        items = [
            (item_id, content)
            for item_id, content in parse_list(lines)
            if not query or query in content.casefold()
        ]
        if not items:
            return [
                PluginResult(
                    "No matching clipboard items",
                    subtitle="Copy something first, or try another query",
                    icon="dialog-info-symbolic",
                )
            ]

        total = len(items)
        rows = []
        for item_id, content in items[:_MAX_RESULTS]:
            preview = content.replace("\n", " ").strip()
            if is_binary(content):
                preview = "[Image or binary]"
            elif len(preview) > 80:
                preview = preview[:77] + "..."
            rows.append(
                PluginResult(
                    preview,
                    subtitle="Press Enter to copy",
                    icon=self.icon,
                    data=item_id,
                )
            )
        if total > _MAX_RESULTS:
            # Show the truncation; this row is non-actionable (data=None).
            rows.append(
                PluginResult(
                    f"… and {total - _MAX_RESULTS} more matches",
                    subtitle="Keep typing to narrow the list",
                    icon="go-down-symbolic",
                )
            )
        return rows

    def execute(self, result: PluginResult | None = None) -> bool:
        if result is not None:
            if result.data:
                self._recopy(str(result.data))
                return False  # close the launcher after copying
            return True  # non-actionable row (truncation hint) — stay open
        return False

    @staticmethod
    def _recopy(item_id: str):
        """Decode a history item and copy it back to the clipboard."""
        try:
            decoded = run_subprocess(
                ["cliphist", "decode", item_id],
                timeout=_TIMEOUT_SECONDS,
            )
        except Exception:
            return
        if decoded.returncode != 0 or not decoded.stdout:
            return
        if "\x00" in decoded.stdout:
            # Binary content (images) can't be copied as text — skip it.
            return
        copy_to_clipboard(decoded.stdout)
