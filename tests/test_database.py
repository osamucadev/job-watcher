from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database import SEED_COMPANIES, connection, initialize_database


class DatabaseTests(unittest.TestCase):
    def test_initialize_database_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.db"
            initialize_database(path)
            initialize_database(path)

            with connection(path) as database:
                companies = database.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
                settings = database.execute("SELECT COUNT(*) FROM settings").fetchone()[0]

            self.assertEqual(companies, len(SEED_COMPANIES))
            self.assertEqual(settings, 1)

    def test_migrates_legacy_archive_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.db"
            initialize_database(path)
            with connection(path) as database:
                company_id = database.execute("SELECT id FROM companies LIMIT 1").fetchone()[0]
                database.execute(
                    """
                    INSERT INTO jobs(
                        company_id, external_id, title, url, status, archive_reason,
                        first_seen_at, last_seen_at
                    ) VALUES (?, 'legacy', 'Legacy job', 'https://example.test', 'archived', 'manual', 'now', 'now')
                    """,
                    (company_id,),
                )
                database.execute("UPDATE jobs SET archive_source = NULL WHERE external_id = 'legacy'")

            initialize_database(path)
            with connection(path) as database:
                job = database.execute(
                    "SELECT archive_source, archive_reason FROM jobs WHERE external_id = 'legacy'"
                ).fetchone()

            self.assertEqual(job["archive_source"], "manual")
            self.assertIsNone(job["archive_reason"])

    def test_adds_visit_columns_to_existing_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.db"
            initialize_database(path)
            with connection(path) as database:
                database.execute("ALTER TABLE jobs DROP COLUMN first_visited_at")
                database.execute("ALTER TABLE jobs DROP COLUMN last_visited_at")
                company_id = database.execute("SELECT id FROM companies LIMIT 1").fetchone()[0]
                database.execute(
                    """
                    INSERT INTO jobs(company_id, external_id, title, url, first_seen_at, last_seen_at)
                    VALUES (?, 'legacy-job', 'Legacy Role', 'https://example.test', 'now', 'now')
                    """,
                    (company_id,),
                )

            initialize_database(path)
            with connection(path) as database:
                columns = {row["name"] for row in database.execute("PRAGMA table_info(jobs)")}
                job = database.execute(
                    "SELECT * FROM jobs WHERE external_id = 'legacy-job'"
                ).fetchone()

            self.assertIn("first_visited_at", columns)
            self.assertIn("last_visited_at", columns)
            self.assertEqual(job["title"], "Legacy Role")
            self.assertIsNone(job["first_visited_at"])


if __name__ == "__main__":
    unittest.main()
