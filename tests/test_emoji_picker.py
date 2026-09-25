"""Tests for the emoji picker's JSON loading path."""

import unittest
from unittest import mock

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


if __name__ == "__main__":
    unittest.main()
