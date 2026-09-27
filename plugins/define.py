"""Launcher slash command: /define — word definitions from dict.org.

Queries the DICT protocol (RFC 2229) directly over TCP — no API key.
WordNet is the default database; ``-d <database>`` picks another.
"""

import re
import socket
from typing import ClassVar

from utils.plugin_manager import (
    LauncherPlugin,
    PluginCancelledError,
    PluginResult,
    cached_handle,
    copy_to_clipboard,
)

_DICT_HOST = "dict.org"
_DICT_PORT = 2628
_DEFAULT_DATABASE = "wn"
_TIMEOUT_SECONDS = 8
_MAX_SENSES = 5
#: Title preview length of a sense row in the launcher.
_PREVIEW_LENGTH = 110
_DATABASE_FLAGS = {"-d", "--database"}

#: Numbered sense line inside a WordNet definition body, e.g. ``    adj 1: ...``.
_SENSE_RE = re.compile(r"^[ \t]*(?:(?:n|v|adj|adv|sat|prep)\s+)?\d+:", re.MULTILINE)
#: ``151 "<word>" <database> "<description>" - text follows``
_151_RE = re.compile(r'^151\s+(?:"([^"]*)"|(\S+))\s+(\S+)\s+"([^"]*)"')


def _parse_151(line: str) -> dict:
    """Parse a ``151`` status line into a definition block header."""
    match = _151_RE.match(line)
    if not match:
        return {"word": "", "database": "", "description": "", "body": []}
    return {
        "word": match.group(1) or match.group(2),
        "database": match.group(3),
        "description": match.group(4),
        "body": [],
    }


def parse_dict_response(text: str) -> list[dict]:
    """Parse a DICT transcript into one dict per ``151`` block; empty on ``552``."""
    blocks: list[dict] = []
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if line.startswith("151 "):
            current = _parse_151(line)
        elif line == ".":
            if current is not None:
                blocks.append(current)
                current = None
        elif line.startswith(("150 ", "250 ", "552 ", "221 ", "220 ")):
            continue
        elif current is not None:
            current["body"].append(line)
    return blocks


def split_senses(block: dict) -> list[str]:
    """Split a definition body into senses; falls back to the collapsed body."""
    body = "\n".join(block["body"])
    matches = list(_SENSE_RE.finditer(body))
    if not matches:
        collapsed = " ".join(body.split())
        return [collapsed] if collapsed else []
    senses = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        text = " ".join(body[start:end].split())
        if text:
            senses.append(text)
    return senses


def query_dict(
    word: str,
    database: str = _DEFAULT_DATABASE,
    host: str = _DICT_HOST,
    port: int = _DICT_PORT,
    timeout: float = _TIMEOUT_SECONDS,
    cancelled=None,
) -> list[dict]:
    """Return definition blocks for *word*; *cancelled* raises PluginCancelledError."""
    word = word.strip()
    if not word or "\r" in word or "\n" in word:
        raise ValueError("invalid word")
    if cancelled is not None and cancelled():
        raise PluginCancelledError()
    blocks: list[dict] = []
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            stream = sock.makefile("r", encoding="utf-8", errors="replace")
            greeting = stream.readline()
            if not greeting.startswith("220"):
                raise OSError("not a DICT server (no 220 greeting)")
            sock.sendall(b"CLIENT tsumiki/1.0\r\n")
            if not stream.readline().startswith("250"):
                raise OSError("DICT server rejected CLIENT handshake")
            sock.sendall(f"DEFINE {database} {word}\r\n".encode())
            current: dict | None = None
            for raw in stream:
                if cancelled is not None and cancelled():
                    raise PluginCancelledError()
                line = raw.rstrip("\r\n")
                if line.startswith("151 "):
                    current = _parse_151(line)
                elif line == ".":
                    if current is not None:
                        blocks.append(current)
                        current = None
                elif line.startswith("552"):
                    return []
                elif line.startswith("250 "):
                    break
                elif current is not None:
                    current["body"].append(line)
            sock.sendall(b"QUIT\r\n")
            stream.readline()  # 221 bye
    except socket.timeout as exc:
        raise TimeoutError("dict.org did not respond in time") from exc
    except OSError as exc:
        raise OSError(f"cannot reach dict.org: {exc}") from exc
    return blocks


def parse_define_args(args: str) -> tuple[str, str]:
    """Split *args* into (database, word)."""
    text = args.strip()
    tokens = text.split(maxsplit=2)
    if len(tokens) >= 2 and tokens[0] in _DATABASE_FLAGS:
        return tokens[1], tokens[2].strip() if len(tokens) > 2 else ""
    return _DEFAULT_DATABASE, text


class DefinePlugin(LauncherPlugin):
    """Slash command: /define — definitions from dict.org (WordNet)."""

    name = "define"
    description = "Define a word (dict.org WordNet)"
    icon = "accessories-dictionary-symbolic"
    aliases: ClassVar[list[str]] = ["def", "dict"]
    # Each query opens a TCP connection; debounce so it isn't per keystroke.
    debounce_ms = 500
    #: Session cache TTL — definitions rarely change.
    cache_ttl_seconds = 3600

    @cached_handle()
    def handle(self, args: str) -> list[PluginResult]:
        database, word = parse_define_args(args)
        if not word:
            return [
                PluginResult(
                    "Usage: /define <word>",
                    subtitle=(
                        "e.g. /define serendipity  ·  "
                        "/define -d foldoc monad (pick a database)"
                    ),
                    icon=self.icon,
                )
            ]
        if self.is_cancelled():
            return []  # superseded before the request went out
        try:
            blocks = query_dict(word, database, cancelled=self.is_cancelled)
        except PluginCancelledError:
            return []
        except Exception as exc:
            return [
                PluginResult(
                    "Definition lookup failed",
                    subtitle=f"{exc}",
                    icon="network-error-symbolic",
                )
            ]
        if not blocks:
            return [
                PluginResult(
                    f"No definition for '{word}'",
                    subtitle=(
                        f"Not found in {database} on dict.org — check the spelling"
                    ),
                    icon="dialog-info-symbolic",
                )
            ]

        rows = []
        for block in blocks:
            senses = split_senses(block)
            # The body repeats the headword on line 1; drop it from the copy.
            lines = list(block["body"])
            if lines and lines[0].strip().casefold() == block["word"].casefold():
                lines = lines[1:]
            full = f"{block['word']}\n" + "\n".join(lines)
            source = block["description"] or block["database"]
            for sense in senses[:_MAX_SENSES]:
                if len(sense) > _PREVIEW_LENGTH:
                    title = sense[: _PREVIEW_LENGTH - 3] + "..."
                else:
                    title = sense
                rows.append(
                    PluginResult(
                        title,
                        subtitle=f"{source} · Enter to copy the definition",
                        icon=self.icon,
                        data=full,
                    )
                )
            if len(senses) > _MAX_SENSES:
                rows.append(
                    PluginResult(
                        f"… and {len(senses) - _MAX_SENSES} more senses",
                        subtitle="Enter to copy the full definition",
                        icon="go-down-symbolic",
                        data=full,
                    )
                )
        return rows

    def execute(self, result: PluginResult | None = None) -> bool:
        if result is not None and result.data:
            copy_to_clipboard(str(result.data))
        return False  # close the launcher after copying
