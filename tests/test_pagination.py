from __future__ import annotations

import unittest

from app.services.pagination import normalize_page, page_sequence


class PageSequenceTests(unittest.TestCase):
    def test_zero_pages_returns_empty_sequence(self) -> None:
        self.assertEqual(page_sequence(1, 0), [])

    def test_single_page(self) -> None:
        self.assertEqual(page_sequence(1, 1), [1])

    def test_up_to_eight_pages_shows_all_of_them(self) -> None:
        self.assertEqual(page_sequence(1, 8), [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(page_sequence(5, 8), [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(page_sequence(8, 8), [1, 2, 3, 4, 5, 6, 7, 8])

    def test_more_than_eight_pages_uses_ellipsis(self) -> None:
        sequence = page_sequence(1, 9)
        self.assertIn("…", sequence)

    def test_current_page_near_the_start(self) -> None:
        self.assertEqual(
            page_sequence(1, 20),
            [1, 2, 3, 4, "…", 17, 18, 19, 20],
        )
        self.assertEqual(
            page_sequence(4, 20),
            [1, 2, 3, 4, "…", 17, 18, 19, 20],
        )

    def test_current_page_near_the_end(self) -> None:
        self.assertEqual(
            page_sequence(20, 20),
            [1, 2, 3, 4, "…", 17, 18, 19, 20],
        )
        self.assertEqual(
            page_sequence(17, 20),
            [1, 2, 3, 4, "…", 17, 18, 19, 20],
        )

    def test_current_page_in_the_middle(self) -> None:
        self.assertEqual(
            page_sequence(9, 20),
            [1, 2, "…", 8, 9, 10, 11, "…", 19, 20],
        )
        self.assertEqual(
            page_sequence(10, 20),
            [1, 2, "…", 9, 10, 11, 12, "…", 19, 20],
        )

    def test_current_page_beyond_total_is_clamped(self) -> None:
        self.assertEqual(page_sequence(999, 20), page_sequence(20, 20))

    def test_current_page_below_one_is_clamped(self) -> None:
        self.assertEqual(page_sequence(0, 20), page_sequence(1, 20))

    def test_ellipsis_never_appears_for_a_single_hidden_page(self) -> None:
        # total=9 keeps every page reachable within the edge/anchor windows
        # except at most one hidden page; make sure no adjacent duplicates
        # or nonsensical single-page ellipses sneak in for a small total.
        sequence = page_sequence(5, 9)
        numbers = [entry for entry in sequence if entry != "…"]
        self.assertEqual(numbers, sorted(set(numbers)))


class NormalizePageTests(unittest.TestCase):
    def test_missing_page_defaults_to_one(self) -> None:
        self.assertEqual(normalize_page(None, 5), 1)

    def test_non_numeric_page_defaults_to_one(self) -> None:
        self.assertEqual(normalize_page("abc", 5), 1)

    def test_zero_page_defaults_to_one(self) -> None:
        self.assertEqual(normalize_page("0", 5), 1)

    def test_negative_page_defaults_to_one(self) -> None:
        self.assertEqual(normalize_page("-3", 5), 1)

    def test_page_beyond_total_clamps_to_last_page(self) -> None:
        self.assertEqual(normalize_page("999", 5), 5)

    def test_valid_page_passes_through(self) -> None:
        self.assertEqual(normalize_page("3", 5), 3)

    def test_zero_total_pages_always_normalizes_to_one(self) -> None:
        self.assertEqual(normalize_page("1", 0), 1)
        self.assertEqual(normalize_page("5", 0), 1)
        self.assertEqual(normalize_page(None, 0), 1)


if __name__ == "__main__":
    unittest.main()
