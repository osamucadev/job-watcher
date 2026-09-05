from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

import app.database as db
import app.main as main_module
from app.database import (
    connection,
    initialize_database,
    mark_interrupted_runs,
    record_run_progress,
)
from app.main import _run_duration_seconds, run_looks_stalled


async def _noop_start() -> None:
    return None


def _noop_stop() -> None:
    return None


def _iso(offset_seconds: float) -> str:
    return (datetime.now(UTC) + timedelta(seconds=offset_seconds)).isoformat()


class InterruptedRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "test.db"
        initialize_database(self.path)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _insert_run(self, status: str, *, finished: bool) -> int:
        with connection(self.path) as database:
            cursor = database.execute(
                """
                INSERT INTO check_runs(started_at, finished_at, status, companies_total)
                VALUES (?, ?, ?, 30)
                """,
                (_iso(-60), _iso(-10) if finished else None, status),
            )
            return cursor.lastrowid

    def test_running_row_is_marked_failed(self) -> None:
        run_id = self._insert_run("running", finished=False)
        changed = mark_interrupted_runs(self.path)
        self.assertEqual(changed, 1)
        with connection(self.path) as database:
            row = database.execute(
                "SELECT status, finished_at, error FROM check_runs WHERE id = ?", (run_id,)
            ).fetchone()
        self.assertEqual(row["status"], "failed")
        self.assertIsNotNone(row["finished_at"])
        self.assertEqual(row["error"], "Interrupted before completion")

    def test_finished_runs_are_left_untouched(self) -> None:
        run_id = self._insert_run("success", finished=True)
        self.assertEqual(mark_interrupted_runs(self.path), 0)
        with connection(self.path) as database:
            row = database.execute(
                "SELECT status FROM check_runs WHERE id = ?", (run_id,)
            ).fetchone()
        self.assertEqual(row["status"], "success")


class RunProgressPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "test.db"
        initialize_database(self.path)
        with connection(self.path) as database:
            cursor = database.execute(
                """
                INSERT INTO check_runs(started_at, heartbeat_at, status, companies_total)
                VALUES (?, ?, 'running', 3)
                """,
                (_iso(-5), _iso(-5)),
            )
            self.run_id = cursor.lastrowid

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_progress_accumulates_and_moves_heartbeat(self) -> None:
        record_run_progress(
            self.run_id, checked=1, found=10, new=2, archived=1, database_path=self.path
        )
        record_run_progress(
            self.run_id, checked=1, found=5, new=0, archived=0, database_path=self.path
        )
        with connection(self.path) as database:
            row = database.execute(
                "SELECT * FROM check_runs WHERE id = ?", (self.run_id,)
            ).fetchone()
        self.assertEqual(row["companies_checked"], 2)
        self.assertEqual(row["jobs_found"], 15)
        self.assertEqual(row["jobs_new"], 2)
        self.assertEqual(row["jobs_archived"], 1)
        self.assertGreater(row["heartbeat_at"], row["started_at"])

    def test_failed_company_still_refreshes_heartbeat_without_counts(self) -> None:
        record_run_progress(self.run_id, database_path=self.path)
        with connection(self.path) as database:
            row = database.execute(
                "SELECT * FROM check_runs WHERE id = ?", (self.run_id,)
            ).fetchone()
        self.assertEqual(row["companies_checked"], 0)
        self.assertEqual(row["jobs_found"], 0)
        self.assertIsNotNone(row["heartbeat_at"])


class StalledDetectionTests(unittest.TestCase):
    def _run(self, **columns: object) -> dict[str, object]:
        base = {
            "status": "running",
            "started_at": _iso(-600),
            "heartbeat_at": _iso(-5),
        }
        base.update(columns)
        return base

    def test_fresh_heartbeat_is_not_stalled(self) -> None:
        self.assertFalse(run_looks_stalled(self._run()))

    def test_old_heartbeat_is_stalled(self) -> None:
        self.assertTrue(run_looks_stalled(self._run(heartbeat_at=_iso(-3600))))

    def test_missing_heartbeat_falls_back_to_started_at(self) -> None:
        self.assertTrue(run_looks_stalled(self._run(heartbeat_at=None)))

    def test_finished_run_is_never_stalled(self) -> None:
        self.assertFalse(
            run_looks_stalled(self._run(status="success", heartbeat_at=_iso(-3600)))
        )

    def test_none_is_not_stalled(self) -> None:
        self.assertFalse(run_looks_stalled(None))


class RunDurationTests(unittest.TestCase):
    def test_duration_is_rounded_seconds(self) -> None:
        run = {"started_at": "2026-09-05T10:00:00+00:00", "finished_at": "2026-09-05T10:00:08.7+00:00"}
        self.assertEqual(_run_duration_seconds(run), 8.7)

    def test_unfinished_run_has_no_duration(self) -> None:
        self.assertIsNone(_run_duration_seconds({"started_at": _iso(-10), "finished_at": None}))


class ActivityPageTests(unittest.TestCase):
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

        self.client = TestClient(main_module.app)
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        main_module.start_scheduler = self._original_start
        main_module.stop_scheduler = self._original_stop
        db.DATABASE_PATH = self._original_db_path
        self.directory.cleanup()

    def test_idle_activity_page_renders(self) -> None:
        response = self.client.get("/activity")
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn('data-pt="Nenhuma verificação em andamento"', body)
        self.assertNotIn('http-equiv="refresh"', body)

    def test_nav_has_activity_link_on_every_page(self) -> None:
        for route in ("/", "/jobs", "/companies", "/settings", "/activity"):
            body = self.client.get(route).text
            self.assertIn('href="/activity"', body)
            self.assertIn('data-pt="Atividade"', body)

    def test_history_row_is_shown(self) -> None:
        with connection(self.path) as database:
            database.execute(
                """
                INSERT INTO check_runs(started_at, finished_at, status, companies_total,
                    companies_checked, jobs_found, jobs_new, jobs_archived)
                VALUES (?, ?, 'partial', 30, 29, 812, 3, 1)
                """,
                (_iso(-120), _iso(-110)),
            )
        body = self.client.get("/activity").text
        self.assertIn('data-en="Partial"', body)
        self.assertIn("812", body)

    def test_running_check_shows_live_banner_and_auto_refresh(self) -> None:
        from types import SimpleNamespace

        original_monitor = main_module.monitor
        with connection(self.path) as database:
            database.execute(
                """
                INSERT INTO check_runs(started_at, heartbeat_at, status, companies_total)
                VALUES (?, ?, 'running', 2)
                """,
                (_iso(-4), _iso(-2)),
            )
        snapshot = {
            "run_id": 1,
            "started_at": _iso(-4),
            "updated_at": _iso(-2),
            "total": 2,
            "settled": 1,
            "counts": {"pending": 0, "collecting": 1, "done": 1, "error": 0},
            "companies": [
                {"name": "Alpha", "state": "done", "jobs": 7},
                {"name": "Beta", "state": "collecting", "jobs": None},
            ],
        }
        main_module.monitor = SimpleNamespace(is_running=True, snapshot=lambda: snapshot)
        try:
            body = self.client.get("/activity").text
        finally:
            main_module.monitor = original_monitor
        self.assertIn('http-equiv="refresh"', body)
        self.assertIn('data-pt="Verificando agora"', body)
        self.assertIn("check-status", body)
        self.assertIn('data-pt="Ver status"', body)
        self.assertIn("Alpha", body)
        self.assertIn("Beta", body)


if __name__ == "__main__":
    unittest.main()
