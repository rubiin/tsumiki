"""Storage for the desktop sticky notes.

One JSON file holds every monitor's notes. Writes are debounced because the
text changes on every keystroke, and each save replaces the file atomically so
a crash mid-write cannot truncate the notes.
"""

import json
import os
import uuid

from fabric.utils import GLib, logger

from utils.constants import DESKTOP_NOTES_FILE, NOTE_COLORS
from utils.functions import write_json_file

SAVE_DELAY_MS = 800


def _source_is_alive(source_id: int) -> bool:
    return GLib.MainContext.default().find_source_by_id(source_id) is not None


def _normalise_note(note: dict) -> dict | None:
    """Return a usable note, or None when an entry is too broken to show."""
    note_id = note.get("id")
    if not isinstance(note_id, str) or not note_id:
        return None

    def coordinate(key: str) -> int:
        value = note.get(key, 0)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    color = note.get("color")
    return {
        "id": note_id,
        "monitor": note.get("monitor") if isinstance(note.get("monitor"), str) else "",
        "x": max(0, coordinate("x")),
        "y": max(0, coordinate("y")),
        "text": note.get("text") if isinstance(note.get("text"), str) else "",
        "color": color if color in NOTE_COLORS else NOTE_COLORS[0],
        "locked": note.get("locked") is True,
    }


class NotesService:
    """All notes, every monitor, in one file."""

    def __init__(
        self, path: str = DESKTOP_NOTES_FILE, save_delay_ms: int = SAVE_DELAY_MS
    ):
        self.path = path
        self.save_delay_ms = save_delay_ms
        self.notes: list[dict] = []
        self._save_id: int | None = None
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            logger.warning(f"[DesktopNotes] Ignoring unreadable notes file: {exc}")
            return

        if not isinstance(data, list):
            return
        for entry in data:
            if not isinstance(entry, dict):
                continue
            note = _normalise_note(entry)
            if note is not None:
                self.notes.append(note)

    def for_monitor(self, monitor: str) -> list[dict]:
        return [note for note in self.notes if note.get("monitor") == monitor]

    def add(self, monitor: str, x: int, y: int) -> dict:
        note = {
            "id": uuid.uuid4().hex,
            "monitor": monitor,
            "x": max(0, int(x)),
            "y": max(0, int(y)),
            "text": "",
            "color": NOTE_COLORS[len(self.notes) % len(NOTE_COLORS)],
            "locked": False,
        }
        self.notes.append(note)
        self.save_soon()
        return note

    def remove(self, note_id: str) -> None:
        self.notes = [note for note in self.notes if note["id"] != note_id]
        self.save_soon()

    def save_soon(self) -> None:
        if self._save_id is not None and _source_is_alive(self._save_id):
            GLib.source_remove(self._save_id)
        self._save_id = GLib.timeout_add(self.save_delay_ms, self._save)

    def flush(self) -> None:
        """Write pending changes now, for teardown and tests."""
        if self._save_id is not None and _source_is_alive(self._save_id):
            GLib.source_remove(self._save_id)
        self._save_id = None
        self._write()

    def _save(self) -> bool:
        self._save_id = None
        self._write()
        return False

    def _write(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            try:
                os.makedirs(directory, exist_ok=True)
            except OSError as exc:
                logger.warning(f"[DesktopNotes] Couldn't create notes folder: {exc}")
                return
        write_json_file(self.path, self.notes, sync=True)
