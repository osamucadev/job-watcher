from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database import connection, initialize_database
from app.services.monitor import is_highlighted, process_company_snapshot
from app.services.scraper import ScrapedJob, extract_external_id


class ScraperTests(unittest.TestCase):
    def test_extracts_job_identifier_from_nested_inhire_url(self) -> None:
        url = "https://lwsa.inhire.app/octadesk/vagas/abc-123/python-developer"
        self.assertEqual(extract_external_id(url), "abc-123")

    def test_rejects_company_listing_url(self) -> None:
        self.assertIsNone(extract_external_id("https://example.inhire.app/vagas"))

    def test_highlight_matching_ignores_case_and_accents(self) -> None:
        self.assertTrue(is_highlighted("Pessoa Desenvolvedora Python", ["desenvolvedor"]))
        self.assertFalse(is_highlighted("Analista Financeiro", ["python", "developer"]))


class SnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "test.db"
        initialize_database(self.path)
        with connection(self.path) as database:
            self.company_id = database.execute(
                "SELECT id FROM companies ORDER BY id LIMIT 1"
            ).fetchone()[0]

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_first_snapshot_is_baseline_and_later_job_is_new(self) -> None:
        first = ScrapedJob("one", "Backend Developer", "https://example.test/vagas/one/job")
        second = ScrapedJob("two", "Data Analyst", "https://example.test/vagas/two/job")

        new_count, archived_count = process_company_snapshot(
            self.company_id, [first], database_path=self.path
        )
        self.assertEqual((new_count, archived_count), (0, 0))

        new_count, archived_count = process_company_snapshot(
            self.company_id, [first, second], database_path=self.path
        )
        self.assertEqual((new_count, archived_count), (1, 0))

    def test_missing_job_is_archived_and_reappearance_restores_it(self) -> None:
        job = ScrapedJob("one", "Mobile Developer", "https://example.test/vagas/one/job")
        process_company_snapshot(self.company_id, [job], database_path=self.path)
        _, archived_count = process_company_snapshot(self.company_id, [], database_path=self.path)
        self.assertEqual(archived_count, 1)

        new_count, _ = process_company_snapshot(self.company_id, [job], database_path=self.path)
        self.assertEqual(new_count, 1)
        with connection(self.path) as database:
            restored = database.execute(
                "SELECT status, reopened_at FROM jobs WHERE external_id = 'one'"
            ).fetchone()
        self.assertEqual(restored["status"], "active")
        self.assertIsNotNone(restored["reopened_at"])


if __name__ == "__main__":
    unittest.main()
