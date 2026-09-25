"""Launcher slash command: /emoji — search the bundled emoji database."""

from functools import lru_cache
from typing import ClassVar

from utils.constants import ASSETS_DIR
from utils.functions import read_json_file
from utils.plugin_manager import LauncherPlugin, PluginResult, copy_to_clipboard

_MAX_RESULTS = 24


@lru_cache(maxsize=1)
def load_emojis() -> dict:
    """Return the bundled emoji database as {emoji_char: info} (cached)."""
    data = read_json_file(f"{ASSETS_DIR}/emoji.json")
    return data if isinstance(data, dict) else {}


def search_emojis(query: str, limit: int = _MAX_RESULTS) -> list[tuple[str, dict]]:
    """Return up to *limit* (emoji_char, info) rows matching *query*."""
    query = query.casefold().strip()
    if not query:
        return []
    matches = []
    for emoji_char, info in load_emojis().items():
        haystack = (
            f"{info.get('name', '')} {info.get('slug', '')} {info.get('group', '')}"
        ).casefold()
        if query in haystack:
            matches.append((emoji_char, info))
        if len(matches) >= limit:
            break
    return matches


class EmojiPlugin(LauncherPlugin):
    """Slash command: /emoji — search the emoji database and copy a match."""

    name = "emoji"
    description = "Search and copy an emoji"
    aliases: ClassVar[list[str]] = ["emo"]

    def handle(self, args: str) -> list[PluginResult]:
        query = args.strip()
        if not query:
            return [
                PluginResult(
                    "Usage: /emoji <search>",
                    subtitle="e.g. /emoji heart  or  /emoji rocket",
                    icon=self.icon,
                )
            ]
        matches = search_emojis(query)
        if not matches:
            return [
                PluginResult(
                    f"No emoji matches '{query}'",
                    icon="dialog-warning-symbolic",
                )
            ]
        return [
            PluginResult(
                emoji_char,
                subtitle=info.get("name", ""),
                data=emoji_char,
            )
            for emoji_char, info in matches
        ]

    def execute(self, result: PluginResult | None = None) -> bool:
        if result is not None and result.data:
            copy_to_clipboard(str(result.data))
        return False  # close the launcher after copying
