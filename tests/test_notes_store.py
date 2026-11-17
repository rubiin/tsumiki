import json
import os
import tempfile
import unittest

from services.desktop_notes import NotesService
from utils.constants import NOTE_COLORS


class NotesServiceTest(unittest.TestCase):
    """Load, add, remove and persist desktop sticky notes."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.path = os.path.join(self._tmpdir.name, "desktop_notes.json")

    def make_store(self, delay: int = 800) -> NotesService:
        return NotesService(path=self.path, save_delay_ms=delay)

    def test_missing_file_starts_empty(self):
        self.assertEqual([], self.make_store().notes)

    def test_add_assigns_defaults_and_persists(self):
        store = self.make_store()
        note = store.add("DP-1", 40, 60)
        store.flush()

        self.assertEqual("DP-1", note["monitor"])
        self.assertEqual((40, 60), (note["x"], note["y"]))
        self.assertEqual("", note["text"])
        self.assertEqual(NOTE_COLORS[0], note["color"])

        reloaded = self.make_store()
        self.assertEqual(1, len(reloaded.notes))
        self.assertEqual(note, reloaded.notes[0])

    def test_notes_are_scoped_to_their_monitor(self):
        store = self.make_store()
        first = store.add("DP-1", 0, 0)
        second = store.add("HDMI-A-1", 10, 10)

        self.assertEqual([first], store.for_monitor("DP-1"))
        self.assertEqual([second], store.for_monitor("HDMI-A-1"))
        self.assertEqual([], store.for_monitor("eDP-1"))

    def test_colors_cycle_through_the_palette(self):
        store = self.make_store()
        colors = [store.add("DP-1", 0, 0)["color"] for _ in range(len(NOTE_COLORS))]

        self.assertEqual(list(NOTE_COLORS), colors)

    def test_remove_persists(self):
        store = self.make_store()
        note = store.add("DP-1", 0, 0)
        store.remove(note["id"])
        store.flush()

        self.assertEqual([], store.notes)
        self.assertEqual([], self.make_store().notes)

    def test_text_changes_are_saved_from_the_note_dict(self):
        store = self.make_store()
        note = store.add("DP-1", 0, 0)
        note["text"] = "buy milk"
        store.flush()

        self.assertEqual("buy milk", self.make_store().notes[0]["text"])

    def test_malformed_json_is_ignored(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("{not json")

        self.assertEqual([], self.make_store().notes)

    def test_invalid_entries_are_dropped_and_valid_ones_normalised(self):
        data = [
            "nope",
            {"text": "no id"},
            {"id": "a", "monitor": "DP-1", "x": -5, "y": "bad", "text": 3},
            {
                "id": "b",
                "monitor": "DP-1",
                "x": 1,
                "y": 2,
                "text": "keep",
                "color": "chartreuse",
            },
        ]
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)

        notes = self.make_store().notes
        self.assertEqual(["a", "b"], [note["id"] for note in notes])
        self.assertEqual(
            {"x": 0, "y": 0, "text": ""},
            {key: notes[0][key] for key in ("x", "y", "text")},
        )
        self.assertEqual("keep", notes[1]["text"])
        self.assertEqual(NOTE_COLORS[0], notes[1]["color"])
        self.assertFalse(notes[1]["locked"])

    def test_lock_state_round_trips(self):
        store = self.make_store()
        note = store.add("DP-1", 0, 0)
        self.assertFalse(note["locked"])

        note["locked"] = True
        store.flush()

        self.assertTrue(self.make_store().notes[0]["locked"])

    def test_save_soon_defers_until_flush(self):
        store = self.make_store(delay=60_000)
        store.add("DP-1", 0, 0)

        self.assertFalse(os.path.exists(self.path))
        store.flush()
        self.assertTrue(os.path.exists(self.path))


if __name__ == "__main__":
    unittest.main()
