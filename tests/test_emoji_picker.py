"""Tests for the emoji picker: JSON loading and grid keyboard navigation."""

import unittest
from unittest import mock

from fabric.utils import Gdk

from widgets.emoji_picker import EmojiPickerMenu


class EmojiPickerJsonLoaderTest(unittest.TestCase):
    """The emoji picker uses the shared JSON file reader."""

    def test_load_uses_shared_json_reader(self):
        picker = EmojiPickerMenu.__new__(EmojiPickerMenu)
        picker._emoji_loading = False
        picker._all_emojis = None
        picker._emoji_file_path = "/tmp/emoji.json"
        deferred = []

        with (
            mock.patch(
                "widgets.emoji_picker.read_json_file",
                return_value={"😀": {"name": "grinning face"}},
            ) as read_json,
            mock.patch(
                "widgets.emoji_picker.run_in_thread",
                side_effect=lambda func: func,
            ),
            mock.patch(
                "widgets.emoji_picker.idle_add",
                side_effect=lambda *args: deferred.append(args),
            ),
        ):
            picker._load_emoji_data_async()

        read_json.assert_called_once_with("/tmp/emoji.json")
        self.assertEqual(deferred[0][1], {"😀": {"name": "grinning face"}})


class _FakeStyleContext:
    def __init__(self):
        self.classes: set[str] = set()

    def add_class(self, name):
        self.classes.add(name)

    def remove_class(self, name):
        self.classes.discard(name)


class _FakeButton:
    def __init__(self):
        self.style = _FakeStyleContext()

    def get_style_context(self):
        return self.style


class _FakeNode:
    """The page -> grid -> row -> button chain the picker flattens."""

    def __init__(self, children):
        self._children = children

    def get_children(self):
        return self._children


class _FakeStack:
    def __init__(self, pages):
        self._pages = pages
        self._current = 0

    def get_visible_child(self):
        rows = self._pages[self._current]
        return _FakeNode([_FakeNode([_FakeNode(row) for row in rows])])

    def set_visible_child_name(self, name):
        self._current = int(name.rsplit("-", 1)[1])


def make_picker(per_row: int, per_column: int, emoji_count: int) -> EmojiPickerMenu:
    """An EmojiPickerMenu over a fake stack, with the given grid config."""
    per_page = per_row * per_column
    pages = []
    for start in range(0, emoji_count, per_page):
        page = [_FakeButton() for _ in range(start, min(start + per_page, emoji_count))]
        pages.append([page[i : i + per_row] for i in range(0, len(page), per_row)])

    picker = EmojiPickerMenu.__new__(EmojiPickerMenu)
    picker._per_row = per_row
    picker.emojis_per_page = per_page
    picker.stack = _FakeStack(pages)
    picker.selected_index = -1
    picker.current_page_index = 0
    picker.total_pages = len(pages)
    picker.filtered_emojis = [(str(i), {}) for i in range(emoji_count)]
    picker._page_cache = dict.fromkeys(range(len(pages)), object())
    return picker


class EmojiGridNavigationTest(unittest.TestCase):
    """Arrow keys must follow the configured grid, not a hardcoded 3x9."""

    def test_down_from_the_last_row_opens_the_next_page(self):
        # 4 wide, 2 tall, 8 per page: row 1 is the last one, so Down pages.
        picker = make_picker(per_row=4, per_column=2, emoji_count=20)
        picker.selected_index = 4

        picker._move_selection_2d(Gdk.KEY_Down)

        self.assertEqual(picker.current_page_index, 1)
        self.assertEqual(picker.selected_index, 0)

    def test_down_within_the_page_stays_put(self):
        picker = make_picker(per_row=4, per_column=2, emoji_count=20)
        picker.selected_index = 1

        picker._move_selection_2d(Gdk.KEY_Down)

        self.assertEqual(picker.current_page_index, 0)
        self.assertEqual(picker.selected_index, 5)

    def test_up_from_the_first_row_lands_on_the_previous_last_row(self):
        # The regression: a hardcoded 3 rows picked row 2 of the old page.
        picker = make_picker(per_row=9, per_column=4, emoji_count=40)
        picker.current_page_index = 1
        picker.selected_index = 0

        picker._move_selection_2d(Gdk.KEY_Up)

        self.assertEqual(picker.current_page_index, 0)
        self.assertEqual(picker.selected_index, 27)

    def test_the_shipped_default_grid_is_four_rows_of_nine(self):
        picker = make_picker(per_row=9, per_column=4, emoji_count=36)

        self.assertEqual(picker._grid_shape(), (4, 9))

    def test_a_configured_grid_reports_its_own_shape(self):
        picker = make_picker(per_row=5, per_column=3, emoji_count=15)

        self.assertEqual(picker._grid_shape(), (3, 5))

    def test_a_partial_last_row_counts_as_a_row(self):
        picker = make_picker(per_row=4, per_column=3, emoji_count=10)

        self.assertEqual(picker._grid_shape(), (3, 4))


if __name__ == "__main__":
    unittest.main()
