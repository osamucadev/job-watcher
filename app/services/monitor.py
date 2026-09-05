from __future__ import annotations

import asyncio
import logging
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.config import DATABASE_PATH
from app.database import connection, get_keywords, utc_now
from app.services.inhire import (
    MAX_CONCURRENCY,
    REQUEST_TIMEOUT,
    ScrapedJob,
    collect_company,
)


logger = logging.getLogger(__name__)


def normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def is_highlighted(title: str, keywords: list[str]) -> bool:
    normalized_title = normalized(title)
    return any(normalized(keyword) in normalized_title for keyword in keywords if keyword.strip())


def process_company_snapshot(
    company_id: int,
    jobs: list[ScrapedJob],
    *,
    database_path: Path | None = None,
) -> tuple[int, int]:
    now = utc_now()
    keywords = get_keywords() if database_path is None else _keywords_from(database_path)
    new_count = 0
    archived_count = 0

    with connection(database_path or DATABASE_PATH) as database:
        company = database.execute(
            "SELECT last_checked_at FROM companies WHERE id = ?", (company_id,)
        ).fetchone()
        if not company:
            raise ValueError(f"Company {company_id} does not exist")
        is_baseline = company["last_checked_at"] is None
        seen_ids: list[str] = []

        for job in jobs:
            seen_ids.append(job.external_id)
            existing = database.execute(
                "SELECT id, status, archive_source FROM jobs WHERE company_id = ? AND external_id = ?",
                (company_id, job.external_id),
            ).fetchone()
            highlighted = int(is_highlighted(job.title, keywords))

            if existing is None:
                is_new = int(not is_baseline)
                new_count += is_new
                database.execute(
                    """
                    INSERT INTO jobs(
                        company_id, external_id, title, url, is_highlighted, is_new,
                        first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        company_id,
                        job.external_id,
                        job.title,
                        job.url,
                        highlighted,
                        is_new,
                        now,
                        now,
                    ),
                )
            elif existing["status"] == "archived" and existing["archive_source"] == "source":
                new_count += 1
                database.execute(
                    """
                    UPDATE jobs
                    SET title = ?, url = ?, status = 'active', archive_source = NULL,
                        archive_reason = NULL, archive_note = NULL,
                        is_highlighted = ?, is_new = 1, last_seen_at = ?,
                        archived_at = NULL, reopened_at = ?
                    WHERE id = ?
                    """,
                    (job.title, job.url, highlighted, now, now, existing["id"]),
                )
            else:
                database.execute(
                    """
                    UPDATE jobs
                    SET title = ?, url = ?, is_highlighted = ?, last_seen_at = ?
                    WHERE id = ?
                    """,
                    (job.title, job.url, highlighted, now, existing["id"]),
                )

        active_rows = database.execute(
            "SELECT id, external_id FROM jobs WHERE company_id = ? AND status = 'active'",
            (company_id,),
        ).fetchall()
        seen_set = set(seen_ids)
        for row in active_rows:
            if row["external_id"] in seen_set:
                continue
            archived_count += 1
            database.execute(
                """
                UPDATE jobs
                SET status = 'archived', archive_source = 'source',
                    archive_reason = 'source_removed', archive_note = NULL,
                    archived_at = ?, is_new = 0
                WHERE id = ?
                """,
                (now, row["id"]),
            )

        database.execute(
            """
            UPDATE companies
            SET last_checked_at = ?, last_error = NULL, updated_at = ?
            WHERE id = ?
            """,
            (now, now, company_id),
        )

    return new_count, archived_count


def _keywords_from(database_path: Path) -> list[str]:
    import json

    with connection(database_path) as database:
        row = database.execute(
            "SELECT value FROM settings WHERE key = 'highlight_keywords'"
        ).fetchone()
    return json.loads(row["value"]) if row else []


class JobMonitor:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._lock.locked()

    async def run(self) -> None:
        if self._lock.locked():
            logger.info("A monitoring run is already active")
            return

        async with self._lock:
            await self._run_locked()

    async def _run_locked(self) -> None:
        started_at = utc_now()
        with connection() as database:
            database.execute("UPDATE jobs SET is_new = 0")
            companies = database.execute(
                """
                SELECT id, name, url FROM companies
                WHERE is_active = 1 AND is_removed = 0
                ORDER BY name COLLATE NOCASE
                """
            ).fetchall()
            cursor = database.execute(
                """
                INSERT INTO check_runs(started_at, status, companies_total)
                VALUES (?, 'running', ?)
                """,
                (started_at, len(companies)),
            )
            run_id = cursor.lastrowid

        totals = {"checked": 0, "found": 0, "new": 0, "archived": 0}
        errors: list[str] = []

        try:
            limits = httpx.Limits(
                max_connections=MAX_CONCURRENCY,
                max_keepalive_connections=MAX_CONCURRENCY,
            )
            async with httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT, limits=limits, follow_redirects=True
            ) as client:
                semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

                async def collect(company: object) -> None:
                    async with semaphore:
                        try:
                            jobs = await collect_company(client, company["url"])
                            new_count, archived_count = await asyncio.to_thread(
                                process_company_snapshot, company["id"], jobs
                            )
                            totals["checked"] += 1
                            totals["found"] += len(jobs)
                            totals["new"] += new_count
                            totals["archived"] += archived_count
                        except Exception as error:
                            message = f"{company['name']}: {error}"
                            logger.warning("Failed to collect %s: %s", company["name"], error)
                            errors.append(message)
                            with connection() as database:
                                database.execute(
                                    "UPDATE companies SET last_error = ?, updated_at = ? WHERE id = ?",
                                    (str(error)[:500], utc_now(), company["id"]),
                                )

                await asyncio.gather(*(collect(company) for company in companies))

            status = "success" if not errors else "partial"
            with connection() as database:
                database.execute(
                    """
                    UPDATE check_runs
                    SET finished_at = ?, status = ?, companies_checked = ?, jobs_found = ?,
                        jobs_new = ?, jobs_archived = ?, error = ?
                    WHERE id = ?
                    """,
                    (
                        utc_now(),
                        status,
                        totals["checked"],
                        totals["found"],
                        totals["new"],
                        totals["archived"],
                        "\n".join(errors)[:4000] or None,
                        run_id,
                    ),
                )
        except Exception as error:
            logger.exception("Monitoring run failed")
            with connection() as database:
                database.execute(
                    "UPDATE check_runs SET finished_at = ?, status = 'failed', error = ? WHERE id = ?",
                    (utc_now(), str(error)[:4000], run_id),
                )


monitor = JobMonitor()
