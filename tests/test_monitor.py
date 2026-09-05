from __future__ import annotations

import asyncio
import logging
import tempfile
import unittest
from pathlib import Path

import app.database as db
import app.services.monitor as monitor_module
from app.database import connection, initialize_database
from app.services.inhire import CollectionError, ScrapedJob, extract_external_id
from app.services.monitor import (
    JobMonitor,
    RunProgress,
    is_highlighted,
    process_company_snapshot,
)


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
                "SELECT status, reopened_at, archive_source FROM jobs WHERE external_id = 'one'"
            ).fetchone()
        self.assertEqual(restored["status"], "active")
        self.assertIsNotNone(restored["reopened_at"])
        self.assertIsNone(restored["archive_source"])


class RunProgressTests(unittest.TestCase):
    def test_counts_and_settled_track_company_states(self) -> None:
        progress = RunProgress(1, "2026-09-05T10:00:00+00:00", ["Alpha", "Beta", "Gamma"])
        snapshot = progress.as_dict()
        self.assertEqual(snapshot["total"], 3)
        self.assertEqual(snapshot["settled"], 0)
        self.assertEqual(snapshot["counts"]["pending"], 3)

        progress.mark("Alpha", "collecting")
        progress.mark("Alpha", "done", jobs=12)
        progress.mark("Beta", "error")
        snapshot = progress.as_dict()
        self.assertEqual(snapshot["settled"], 2)
        self.assertEqual(snapshot["counts"], {"pending": 1, "collecting": 0, "done": 1, "error": 1})
        alpha = next(entry for entry in snapshot["companies"] if entry["name"] == "Alpha")
        self.assertEqual(alpha["jobs"], 12)

    def test_marking_unknown_company_is_ignored(self) -> None:
        progress = RunProgress(1, "2026-09-05T10:00:00+00:00", ["Alpha"])
        progress.mark("Nobody", "done")
        self.assertEqual(progress.as_dict()["counts"]["done"], 0)


class JobMonitorRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "test.db"
        initialize_database(self.path)
        self._db_path = db.DATABASE_PATH
        self._monitor_db_path = monitor_module.DATABASE_PATH
        db.DATABASE_PATH = self.path
        monitor_module.DATABASE_PATH = self.path
        self._collect = monitor_module.collect_company
        logging.getLogger("app.services.monitor").setLevel(logging.CRITICAL)

    def tearDown(self) -> None:
        monitor_module.collect_company = self._collect
        db.DATABASE_PATH = self._db_path
        monitor_module.DATABASE_PATH = self._monitor_db_path
        logging.getLogger("app.services.monitor").setLevel(logging.NOTSET)
        self.directory.cleanup()

    def _seed_baseline(self) -> None:
        # A first successful run turns the seeded companies into their baseline.
        async def one_job(_client, url):
            return [ScrapedJob("seed-1", "Seed Role", f"{url}/seed-1")]

        monitor_module.collect_company = one_job
        asyncio.run(JobMonitor().run())

    def _latest_run(self):
        with connection(self.path) as database:
            return database.execute(
                "SELECT * FROM check_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()

    def test_successful_run_records_incremental_totals_and_clears_progress(self) -> None:
        async def one_job(_client, url):
            return [ScrapedJob("job-1", "Backend Engineer", f"{url}/job-1")]

        monitor_module.collect_company = one_job
        instance = JobMonitor()
        asyncio.run(instance.run())

        run = self._latest_run()
        with connection(self.path) as database:
            company_total = database.execute(
                "SELECT COUNT(*) FROM companies WHERE is_active = 1 AND is_removed = 0"
            ).fetchone()[0]
        self.assertEqual(run["status"], "success")
        self.assertEqual(run["companies_checked"], company_total)
        self.assertEqual(run["jobs_found"], company_total)
        self.assertIsNotNone(run["finished_at"])
        self.assertIsNone(instance.snapshot())

    def test_collection_failure_never_archives_and_keeps_run_partial(self) -> None:
        self._seed_baseline()

        async def always_fails(_client, _url):
            raise CollectionError("InHire API request failed")

        monitor_module.collect_company = always_fails
        asyncio.run(JobMonitor().run())

        run = self._latest_run()
        with connection(self.path) as database:
            archived = database.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = 'archived'"
            ).fetchone()[0]
            active = database.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = 'active'"
            ).fetchone()[0]
        self.assertEqual(run["status"], "partial")
        self.assertEqual(run["companies_checked"], 0)
        self.assertEqual(archived, 0)
        self.assertGreater(active, 0)
        self.assertIsNotNone(run["error"])


if __name__ == "__main__":
    unittest.main()
