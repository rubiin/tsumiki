"""Tests for the kanban board's persistence in ``widgets/kanban.py``.

Rebuilding the columns emits "changed" once per destroyed row, so loading
the board used to write the file it had just read, over the saved notes with
an empty board. The file helpers are mocked: these tests assert on the calls,
not on anything on disk.
"""

import unittest
from unittest import mock

from widgets import kanban as kanban_module
from widgets.kanban import Kanban, KanbanNote

TEST_KANBAN_FILE = "/tmp/tsumiki-test-kanban.json"

BOARD_STATE = {
    "columns": [
        {"title": "To Do", "notes": ["write docs", "review PR"]},
        {"title": "In Progress", "notes": ["ship it"]},
        {"title": "Done", "notes": ["setup"]},
    ]
}


def board_state_of(board: Kanban) -> dict:
    """The payload ``save_state`` would write for the board as it stands."""
    return {
        "columns": [
            {"title": col.title, "notes": col.get_notes()} for col in board.columns
        ]
    }


class KanbanPersistenceTest(unittest.TestCase):
    """Loading must never write; user edits must always save."""

    def setUp(self):
        for name in ("write_json_file", "read_json_file"):
            patcher = mock.patch.object(kanban_module, name)
            setattr(self, f"{name}_mock", patcher.start())
            self.addCleanup(patcher.stop)
        path = mock.patch.object(kanban_module, "KANBAN_FILE", TEST_KANBAN_FILE)
        path.start()
        self.addCleanup(path.stop)

        self.write_json_file = self.write_json_file_mock
        self.read_json_file = self.read_json_file_mock

    def make_board(self, saved_state=None) -> Kanban:
        """Build a real board, loading *saved_state* (or starting fresh)."""
        self.read_json_file.return_value = saved_state
        return Kanban()

    def notes_by_title(self, board: Kanban) -> dict[str, list[str]]:
        return {col.title: col.get_notes() for col in board.columns}

    def test_loading_a_saved_board_writes_nothing(self):
        """The regression: the rows destroyed while loading used to each
        emit "changed" and save the now-empty board over the saved one."""
        board = self.make_board(BOARD_STATE)

        self.write_json_file.assert_not_called()
        self.read_json_file.assert_called_once_with(TEST_KANBAN_FILE)
        self.assertEqual(
            {
                "To Do": ["write docs", "review PR"],
                "In Progress": ["ship it"],
                "Done": ["setup"],
            },
            self.notes_by_title(board),
        )

    def test_reloading_a_populated_board_keeps_the_notes(self):
        """Opening the popover again must not truncate what the last save
        wrote, not even for the one-column-at-a-time intermediate states."""
        board = self.make_board()
        self.write_json_file.reset_mock()
        board.columns[0].add_note("keep me")
        saved = board_state_of(board)
        self.assertEqual(1, self.write_json_file.call_count)

        self.write_json_file.reset_mock()
        self.read_json_file.return_value = saved

        board.load_state()

        self.write_json_file.assert_not_called()
        self.assertEqual(["keep me"], board.columns[0].get_notes())

    def test_starting_fresh_without_saved_state_writes_nothing(self):
        board = self.make_board(None)

        self.write_json_file.assert_not_called()
        self.assertEqual(
            {"To Do": [], "In Progress": [], "Done": []},
            self.notes_by_title(board),
        )

    def test_a_malformed_saved_state_writes_nothing(self):
        board = self.make_board({"columns": "not-a-list"})

        self.write_json_file.assert_not_called()
        self.assertEqual(
            {"To Do": [], "In Progress": [], "Done": []},
            self.notes_by_title(board),
        )

    def test_adding_a_note_saves_the_board(self):
        board = self.make_board()
        self.write_json_file.reset_mock()

        board.columns[1].add_note("new task")

        self.write_json_file.assert_called_once()
        path, state = self.write_json_file.call_args.args
        self.assertEqual(TEST_KANBAN_FILE, path)
        self.assertEqual(
            {"title": "In Progress", "notes": ["new task"]}, state["columns"][1]
        )

    def test_a_note_builds_with_the_real_label(self):
        # ``Label`` rejected ``line_wrap=True``, which made every add_note raise.
        note = KanbanNote("a long note that has to wrap across the column width")

        self.assertTrue(note.label.get_line_wrap())
        self.assertEqual(note.text, note.label.get_text())

    def test_a_user_initiated_clear_saves_the_board(self):
        """``clear_notes`` on a user action still has to reach disk."""
        board = self.make_board(BOARD_STATE)
        self.write_json_file.reset_mock()

        board.columns[0].clear_notes(suppress_signal=False)

        self.assertTrue(self.write_json_file.called)
        _, state = self.write_json_file.call_args.args
        self.assertEqual([], state["columns"][0]["notes"])
        # The other columns are untouched by the clear.
        self.assertEqual(["ship it"], state["columns"][1]["notes"])

    def test_deleting_a_note_row_saves_the_board(self):
        board = self.make_board(BOARD_STATE)
        self.write_json_file.reset_mock()

        row = board.columns[0].listbox.get_children()[0]
        row.destroy()

        self.write_json_file.assert_called()
        _, state = self.write_json_file.call_args.args
        self.assertEqual(["review PR"], state["columns"][0]["notes"])

    def test_loading_flag_is_cleared_when_the_load_raises(self):
        """A failed load must not leave saving disabled forever."""
        board = self.make_board()
        self.write_json_file.reset_mock()

        with (
            mock.patch.object(kanban_module.KanbanColumn, "add_note") as add_note,
            mock.patch.object(
                kanban_module, "read_json_file", return_value=BOARD_STATE
            ),
        ):
            add_note.side_effect = ValueError("boom")
            with self.assertRaises(ValueError):
                board.load_state()

        self.assertFalse(board._loading)

        board.save_state()
        self.write_json_file.assert_called_once()

    def test_save_state_is_suppressed_while_loading(self):
        board = self.make_board()
        board._loading = True
        self.addCleanup(setattr, board, "_loading", False)

        board.save_state()

        self.write_json_file.assert_not_called()


if __name__ == "__main__":
    unittest.main()
