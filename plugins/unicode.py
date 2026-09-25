"""Launcher slash command: /unicode -- search the bundled Unicode database."""

from functools import lru_cache
from typing import ClassVar

from utils.constants import ASSETS_DIR
from utils.functions import read_json_file
from utils.plugin_manager import LauncherPlugin, PluginResult, copy_to_clipboard

_MAX_RESULTS = 24


@lru_cache(maxsize=1)
def load_unicode_chars() -> dict:
    """Return the bundled Unicode database as {char: info} (cached)."""
    data = read_json_file(f"{ASSETS_DIR}/unicode.json")
    return data if isinstance(data, dict) else {}


def search_unicode(query: str, limit: int = _MAX_RESULTS) -> list[tuple[str, dict]]:
    """Return up to *limit* (char, info) rows matching *query*."""
    query = query.casefold().strip()
    if not query:
        return []
    matches = []
    for char, info in load_unicode_chars().items():
        haystack = " ".join(
            [
                info.get("name", ""),
                *info.get("aliases", []),
                info.get("codepoint", ""),
                info.get("category", ""),
            ]
        ).casefold()
        if query in haystack:
            matches.append((char, info))
        if len(matches) >= limit:
            break
    return matches


class UnicodePlugin(LauncherPlugin):
    """Slash command: /unicode -- search Unicode characters and copy one."""

    name = "unicode"
    description = "Search and copy a Unicode character"
    aliases: ClassVar[list[str]] = ["uni", "char"]

    def handle(self, args: str) -> list[PluginResult]:
        query = args.strip()
        if not query:
            return [
                PluginResult(
                    "Usage: /unicode <search>",
                    subtitle="e.g. /unicode arrow  or  /unicode copyright",
                    icon=self.icon,
                )
            ]
        matches = search_unicode(query)
        if not matches:
            return [
                PluginResult(
                    f"No Unicode matches '{query}'",
                    icon="dialog-warning-symbolic",
                )
            ]
        return [
            PluginResult(
                f"{char}  {info.get('codepoint', '')}",
                subtitle=info.get("name", ""),
                data=char,
            )
            for char, info in matches
        ]

    def execute(self, result: PluginResult | None = None) -> bool:
        if result is not None and result.data:
            copy_to_clipboard(str(result.data))
        return False  # close the launcher after copying
