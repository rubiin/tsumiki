"""Keymap cheatsheet section normalisation and column planning.

The parsing helpers are pure, so they are tested directly; building the GTK
tree needs a display.
"""

import unittest

from modules.cheatsheet import (
    normalize_keys,
    normalize_row,
    normalize_sections,
    paginate,
    plan_columns,
    section_weight,
)

SECTION = {
    "title": "Window Management",
    "rows": [
        {"keys": ["Super", "F"], "description": "Fullscreen"},
        {"keys": "Super Shift F", "description": "Fullscreen (pure)"},
    ],
}


class NormalizeKeysTest(unittest.TestCase):
    """Key badges may be a list or a spaced string."""

    def test_list_is_kept_in_order(self):
        self.assertEqual(
            ["Super", "Shift", "F"], normalize_keys(["Super", "Shift", "F"])
        )

    def test_string_is_split_on_whitespace_and_plus(self):
        self.assertEqual(["Super", "Shift", "F"], normalize_keys("Super + Shift + F"))

    def test_empty_tokens_are_dropped(self):
        self.assertEqual(["Super", "F"], normalize_keys("  Super   F  "))

    def test_non_string_values_yield_no_keys(self):
        self.assertEqual([], normalize_keys(None))
        self.assertEqual([], normalize_keys(3))

    def test_non_string_entries_are_coerced(self):
        self.assertEqual(["Super", "1"], normalize_keys(["Super", 1]))


class NormalizeRowTest(unittest.TestCase):
    """Rows without any renderable content are dropped."""

    def test_row_is_normalized(self):
        self.assertEqual(
            {"keys": ["Super", "F"], "description": "Fullscreen"},
            normalize_row({"keys": ["Super", "F"], "description": "Fullscreen"}),
        )

    def test_description_is_trimmed(self):
        row = normalize_row({"keys": "F", "description": "  Fullscreen  "})
        self.assertEqual("Fullscreen", row["description"])

    def test_keyless_row_with_description_is_kept(self):
        row = normalize_row({"description": "Note"})
        self.assertEqual({"keys": [], "description": "Note"}, row)

    def test_empty_row_is_dropped(self):
        self.assertIsNone(normalize_row({"keys": [], "description": ""}))

    def test_non_dict_row_is_dropped(self):
        self.assertIsNone(normalize_row("Super F"))


class NormalizeSectionsTest(unittest.TestCase):
    """Sections are kept in config order and empty ones are dropped."""

    def test_section_is_normalized(self):
        self.assertEqual(
            [
                {
                    "title": "Window Management",
                    "rows": [
                        {"keys": ["Super", "F"], "description": "Fullscreen"},
                        {
                            "keys": ["Super", "Shift", "F"],
                            "description": "Fullscreen (pure)",
                        },
                    ],
                }
            ],
            normalize_sections([SECTION]),
        )

    def test_section_without_rows_is_dropped(self):
        self.assertEqual([], normalize_sections([{"title": "Empty", "rows": []}]))

    def test_non_array_input_yields_no_sections(self):
        self.assertEqual([], normalize_sections({"title": "Window Management"}))

    def test_weight_counts_rows_and_the_title(self):
        self.assertEqual(3, section_weight(normalize_sections([SECTION])[0]))


class PlanColumnsTest(unittest.TestCase):
    """Sections are packed into the shortest column first."""

    def test_every_section_lands_in_exactly_one_column(self):
        sections = normalize_sections(
            [
                {"title": "A", "rows": [{"description": "a"}]},
                {"title": "B", "rows": [{"description": "b"}]},
                {"title": "C", "rows": [{"description": "c"}]},
            ]
        )

        columns = plan_columns(sections, 2)

        self.assertEqual(3, sum(len(column) for column in columns))
        # Ties go to the lowest index, so C fills the first column after A.
        self.assertEqual([sections[0], sections[2]], columns[0])
        self.assertEqual([sections[1]], columns[1])

    def test_longest_section_goes_first(self):
        tall = normalize_sections(
            [{"title": "Tall", "rows": [{"description": str(i)} for i in range(9)]}]
        )[0]
        short = normalize_sections(
            [{"title": "Short", "rows": [{"description": "s"}]}]
        )[0]

        columns = plan_columns([tall, short], 2)

        self.assertEqual([tall], columns[0])
        self.assertEqual([short], columns[1])

    def test_column_count_is_always_respected(self):
        sections = normalize_sections(
            [{"title": f"S{i}", "rows": [{"description": "x"}]} for i in range(7)]
        )

        self.assertEqual(4, len(plan_columns(sections, 4)))

    def test_zero_columns_is_clamped_to_one(self):
        sections = normalize_sections([{"title": "A", "rows": [{"description": "a"}]}])

        columns = plan_columns(sections, 0)

        self.assertEqual(1, len(columns))
        self.assertEqual(sections, columns[0])

    def test_no_sections_yields_empty_columns(self):
        columns = plan_columns([], 3)

        self.assertEqual([[], [], []], columns)


class PaginateTest(unittest.TestCase):
    """Sections are split into pages of at most ``groups_per_page`` entries."""

    @staticmethod
    def _sections(count: int) -> list[dict]:
        return normalize_sections(
            [
                {"title": f"S{index}", "rows": [{"description": "x"}]}
                for index in range(count)
            ]
        )

    def test_every_section_lands_on_exactly_one_page(self):
        sections = self._sections(7)

        pages = paginate(sections, 3)

        self.assertEqual([3, 3, 1], [len(page) for page in pages])
        self.assertEqual(sections, [section for page in pages for section in page])

    def test_sections_fitting_one_page_yield_one_page(self):
        self.assertEqual(1, len(paginate(self._sections(8), 8)))

    def test_zero_groups_per_page_is_clamped_to_one(self):
        pages = paginate(self._sections(3), 0)

        self.assertEqual(3, len(pages))
        self.assertEqual(1, len(pages[0]))

    def test_no_sections_yields_no_pages(self):
        self.assertEqual([], paginate([], 4))


if __name__ == "__main__":
    unittest.main()
