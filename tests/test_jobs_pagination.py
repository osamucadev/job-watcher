from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

import app.database as db
import app.main as main_module
from app.database import connection, initialize_database
from app.config import PAGE_SIZE


async def _noop_start() -> None:
    return None


def _noop_stop() -> None:
    return None


class JobsPaginationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "test.db"
        self._original_db_path = db.DATABASE_PATH
        db.DATABASE_PATH = self.path
        initialize_database(self.path)

        self._original_start = main_module.start_scheduler
        self._original_stop = main_module.stop_scheduler
        main_module.start_scheduler = _noop_start
        main_module.stop_scheduler = _noop_stop

        with connection(self.path) as database:
            self.company_id = database.execute(
                "SELECT id FROM companies ORDER BY id LIMIT 1"
            ).fetchone()[0]

        self.client = TestClient(main_module.app)
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        main_module.start_scheduler = self._original_start
        main_module.stop_scheduler = self._original_stop
        db.DATABASE_PATH = self._original_db_path
        self.directory.cleanup()

    def _seed_jobs(self, count: int, *, status: str = "active", highlighted: bool = False) -> None:
        base = datetime(2026, 1, 1, tzinfo=UTC)
        rows = []
        for index in range(count):
            seen_at = (base + timedelta(minutes=index)).isoformat()
            rows.append(
                (
                    self.company_id,
                    f"job-{status}-{index}",
                    f"Role {index:04d}",
                    f"https://example.test/vagas/{status}-{index}",
                    1 if highlighted else 0,
                    status,
                    seen_at,
                    seen_at,
                    seen_at if status == "archived" else None,
                )
            )
        with connection(self.path) as database:
            database.executemany(
                """
                INSERT INTO jobs(
                    company_id, external_id, title, url, is_highlighted, status,
                    first_seen_at, last_seen_at, archived_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def _job_row_count(self, html: str) -> int:
        return html.count('class="job-row')

    def test_zero_results_shows_empty_state_without_pagination(self) -> None:
        response = self.client.get("/jobs")
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn("Nothing here yet", body)
        self.assertNotIn('class="pagination"', body)
        self.assertIn(">0<", body)

    def test_exactly_page_size_results_fit_on_one_page(self) -> None:
        self._seed_jobs(PAGE_SIZE)
        response = self.client.get("/jobs")
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertEqual(self._job_row_count(body), PAGE_SIZE)
        self.assertNotIn('class="pagination"', body)

    def test_one_more_than_page_size_creates_a_second_page(self) -> None:
        self._seed_jobs(PAGE_SIZE + 1)

        first_page = self.client.get("/jobs")
        self.assertEqual(self._job_row_count(first_page.text), PAGE_SIZE)
        self.assertIn('class="pagination"', first_page.text)

        second_page = self.client.get("/jobs?page=2")
        self.assertEqual(self._job_row_count(second_page.text), 1)

    def test_limit_offset_matches_requested_page(self) -> None:
        self._seed_jobs(45)  # 3 pages: 20, 20, 5

        page_two = self.client.get("/jobs?page=2")
        self.assertEqual(self._job_row_count(page_two.text), PAGE_SIZE)

        page_three = self.client.get("/jobs?page=3")
        self.assertEqual(self._job_row_count(page_three.text), 5)

        # Ordering is first_seen_at DESC, so the newest (highest index) jobs
        # come first: page 1 = indices 44..25, page 2 = 24..5, page 3 = 4..0.
        page_two_body = page_two.text
        self.assertIn("Role 0024", page_two_body)
        self.assertIn("Role 0005", page_two_body)
        self.assertNotIn("Role 0025", page_two_body)  # belongs to page 1
        self.assertNotIn("Role 0004", page_two_body)  # belongs to page 3

    def test_invalid_page_param_normalizes_to_first_page(self) -> None:
        self._seed_jobs(25)  # 2 pages
        first_page = self.client.get("/jobs").text

        for value in ("abc", "0", "-5", ""):
            response = self.client.get(f"/jobs?page={value}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self._job_row_count(response.text), PAGE_SIZE)
            self.assertEqual(response.text, first_page)

    def test_page_beyond_total_normalizes_to_last_page(self) -> None:
        self._seed_jobs(25)  # 2 pages: 20 + 5
        response = self.client.get("/jobs?page=999")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._job_row_count(response.text), 5)
        self.assertIn('aria-current="page">2<', response.text)

    def test_total_count_is_preserved_across_pages(self) -> None:
        self._seed_jobs(25)
        first_page = self.client.get("/jobs").text
        second_page = self.client.get("/jobs?page=2").text
        self.assertIn(">25<", first_page)
        self.assertIn(">25<", second_page)

    def test_pagination_absent_for_a_single_page(self) -> None:
        self._seed_jobs(5)
        response = self.client.get("/jobs")
        self.assertNotIn('class="pagination"', response.text)

    def test_pagination_shows_all_numbers_up_to_eight_pages(self) -> None:
        self._seed_jobs(PAGE_SIZE * 8)  # exactly 8 pages
        response = self.client.get("/jobs")
        body = response.text
        for page_number in range(1, 9):
            self.assertIn(f">{page_number}<", body)
        self.assertNotIn("…", body)

    def test_pagination_uses_ellipsis_beyond_eight_pages(self) -> None:
        self._seed_jobs(PAGE_SIZE * 20)  # 20 pages
        response = self.client.get("/jobs")
        self.assertIn("…", response.text)

    def test_highlighted_listing_is_paginated(self) -> None:
        self._seed_jobs(PAGE_SIZE + 3, highlighted=True)
        first_page = self.client.get("/jobs/highlighted")
        self.assertEqual(self._job_row_count(first_page.text), PAGE_SIZE)
        second_page = self.client.get("/jobs/highlighted?page=2")
        self.assertEqual(self._job_row_count(second_page.text), 3)

    def test_archived_listing_is_paginated(self) -> None:
        self._seed_jobs(PAGE_SIZE + 3, status="archived")
        first_page = self.client.get("/jobs/archived")
        self.assertEqual(self._job_row_count(first_page.text), PAGE_SIZE)
        second_page = self.client.get("/jobs/archived?page=2")
        self.assertEqual(self._job_row_count(second_page.text), 3)

    def test_dashboard_recent_jobs_are_not_paginated(self) -> None:
        self._seed_jobs(PAGE_SIZE * 3)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('class="pagination"', response.text)


if __name__ == "__main__":
    unittest.main()
