from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import app.database as db
import app.main as main_module
from app.database import connection, initialize_database


async def _noop_start() -> None:
    return None


def _noop_stop() -> None:
    return None


class JobsApiTests(unittest.TestCase):
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
            cursor = database.execute(
                """
                INSERT INTO jobs(company_id, external_id, title, url, first_seen_at, last_seen_at)
                VALUES (?, 'job-1', 'Backend Engineer', 'https://example.test/vagas/1', 'now', 'now')
                """,
                (self.company_id,),
            )
            self.job_id = cursor.lastrowid

        self.client = TestClient(main_module.app)
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        main_module.start_scheduler = self._original_start
        main_module.stop_scheduler = self._original_stop
        db.DATABASE_PATH = self._original_db_path
        self.directory.cleanup()

    def _fetch_job(self, job_id: int | None = None):
        with connection(self.path) as database:
            return database.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id or self.job_id,)
            ).fetchone()

    def test_archive_with_applied_reason(self) -> None:
        response = self.client.post(
            f"/jobs/{self.job_id}/archive",
            data={"reason": "applied", "note": "", "return_to": "/jobs"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        job = self._fetch_job()
        self.assertEqual(job["status"], "archived")
        self.assertEqual(job["archive_reason"], "applied")
        self.assertEqual(job["archive_source"], "manual")
        self.assertEqual(job["is_new"], 0)

    def test_archive_returns_json_when_requested(self) -> None:
        response = self.client.post(
            f"/jobs/{self.job_id}/archive",
            data={"reason": "applied", "note": "", "return_to": "/jobs"},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

    def test_archive_rejects_invalid_reason(self) -> None:
        response = self.client.post(
            f"/jobs/{self.job_id}/archive",
            data={"reason": "not-a-real-reason", "note": "", "return_to": "/jobs"},
        )
        self.assertEqual(response.status_code, 422)

    def test_archive_unknown_job_returns_404(self) -> None:
        response = self.client.post(
            "/jobs/999999/archive",
            data={"reason": "applied", "note": "", "return_to": "/jobs"},
        )
        self.assertEqual(response.status_code, 404)

    def test_undo_restore_clears_fields_without_marking_reopened(self) -> None:
        self.client.post(
            f"/jobs/{self.job_id}/archive",
            data={"reason": "applied", "note": "", "return_to": "/jobs"},
        )
        response = self.client.post(
            f"/jobs/{self.job_id}/restore",
            data={"return_to": "/jobs"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        job = self._fetch_job()
        self.assertEqual(job["status"], "active")
        self.assertIsNone(job["archive_reason"])
        self.assertIsNone(job["archive_source"])
        self.assertIsNone(job["archive_note"])
        self.assertIsNone(job["archived_at"])
        self.assertIsNone(job["reopened_at"])

    def test_restore_unknown_job_returns_404(self) -> None:
        response = self.client.post(
            "/jobs/999999/restore", data={"return_to": "/jobs"}
        )
        self.assertEqual(response.status_code, 404)

    def test_visit_marks_job_as_visited(self) -> None:
        response = self.client.post(f"/jobs/{self.job_id}/visit")
        self.assertEqual(response.status_code, 200)
        job = self._fetch_job()
        self.assertIsNotNone(job["first_visited_at"])
        self.assertIsNotNone(job["last_visited_at"])

    def test_revisiting_job_preserves_first_visit_timestamp(self) -> None:
        self.client.post(f"/jobs/{self.job_id}/visit")
        first_visited = self._fetch_job()["first_visited_at"]

        self.client.post(f"/jobs/{self.job_id}/visit")
        job = self._fetch_job()
        self.assertEqual(job["first_visited_at"], first_visited)
        self.assertIsNotNone(job["last_visited_at"])

    def test_visit_unknown_job_returns_404(self) -> None:
        response = self.client.post("/jobs/999999/visit")
        self.assertEqual(response.status_code, 404)

    def test_active_job_listing_renders_quick_actions_and_no_dropdown_archive(self) -> None:
        response = self.client.get("/jobs")
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn("js-quick-archive", body)
        self.assertIn("js-open-archive-modal", body)
        self.assertIn('data-pt="Já me candidatei"', body)
        self.assertNotIn("archive-menu", body)
        self.assertNotIn("<details", body)

    def test_visited_tag_appears_after_visiting(self) -> None:
        before = self.client.get("/jobs").text
        self.assertNotIn('data-en="Visited"', before)

        self.client.post(f"/jobs/{self.job_id}/visit")

        after = self.client.get("/jobs").text
        self.assertIn('data-en="Visited"', after)


if __name__ == "__main__":
    unittest.main()
