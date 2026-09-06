from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from app.config import DATABASE_PATH


DEFAULT_KEYWORDS = [
    "ai",
    "android",
    "artificial intelligence",
    "backend",
    "back-end",
    "developer",
    "desenvolvedor",
    "desenvolvedora",
    "engineering lead",
    "flutter",
    "frontend",
    "front-end",
    "full stack",
    "fullstack",
    "inteligência artificial",
    "java",
    "javascript",
    "kotlin",
    "machine learning",
    "mobile",
    "node",
    "python",
    "react",
    "react native",
    "software engineer",
    "tech lead",
    "technical lead",
    "typescript",
]

SEED_COMPANIES = [
    ("dti digital", "https://dtidigital.inhire.app/vagas"),
    ("VR", "https://vr.inhire.app/vagas"),
    ("Lyncas", "https://lyncas.inhire.app/vagas"),
    ("Icon", "https://iconit.inhire.app/vagas"),
    ("Azos", "https://azos.inhire.app/vagas"),
    ("Programmers", "https://programmers.inhire.app/vagas"),
    ("Atlas Technologies", "https://atlastechnol.inhire.app/vagas"),
    ("Sevenred", "https://sevenred.inhire.app/vagas"),
    ("Nomad", "https://nomadglobal.inhire.app/vagas"),
    ("Pantheon Inc", "https://pantheon.inhire.app/vagas"),
    ("LWSA / Octadesk", "https://lwsa.inhire.app/octadesk/vagas"),
    ("Growdev", "https://growdev.inhire.app/vagas"),
    ("Pitang", "https://pitang.inhire.app/vagas"),
    ("Framework Digital", "https://frameworkdigital.inhire.app/vagas"),
    ("Radix", "https://radix.inhire.app/vagas"),
    ("ed", "https://somosed.inhire.app/vagas"),
    ("Premiersoft", "https://premiersoft.inhire.app/vagas"),
    ("Platform Builders", "https://platformbuilders.inhire.app/vagas"),
    ("CSP Tech", "https://csptech.inhire.app/vagas"),
    ("Upda", "https://upda.inhire.app/vagas"),
    ("Dataside", "https://dataside.inhire.app/vagas"),
    ("2biz Company", "https://2bizcompany.inhire.app/vagas"),
    ("Superlógica Tecnologias", "https://superlogica.inhire.app/vagas"),
    ("Brivia", "https://brivia.inhire.app/vagas"),
    ("Venturus", "https://venturus.inhire.app/vagas"),
    ("Mazzatech", "https://mazzatech.inhire.app/vagas"),
    ("minu.co", "https://minu.inhire.app/vagas"),
    ("Kooper / Supero", "https://kooperecooperativa.inhire.app/supero/vagas"),
    ("Remessa Online", "https://remessaonline.inhire.app/vagas"),
    ("VONBZ", "https://vonbz.inhire.app/vagas"),
    ("Alice", "https://alice.inhire.app/vagas"),
    ("Vagas by Intera", "https://vagasbyintera.inhire.app/vagas"),
    ("Portal", "https://portal.inhire.app/vagas"),
    ("Livemode", "https://livemode.inhire.app/vagas"),
    ("Global System", "https://globalsystem.inhire.app/vagas"),
    ("CashMe", "https://cashme.inhire.app/vagas"),
    ("MB Labs", "https://mblabs.inhire.app/vagas"),
    ("Olist", "https://olist.inhire.app/vagas"),
    ("MJV", "https://mjv.inhire.app/vagas"),
    ("Zallpy", "https://zallpy.inhire.app/vagas"),
    ("BRQ", "https://brq.inhire.app/vagas"),
    ("PX Center", "https://pxcenter.inhire.app/vagas"),
    ("Vórtx", "https://vortx.inhire.app/vagas"),
    ("e-Core", "https://ecore.inhire.app/vagas"),
    ("Tech6 Group", "https://tech6group.inhire.app/vagas"),
    ("Share People Hub", "https://sharepeoplehub.inhire.app/vagas"),
    ("Hand", "https://hand.inhire.app/vagas"),
    ("Deal", "https://deal.inhire.app/vagas"),
    ("Tinnova", "https://tinnova.inhire.app/vagas"),
    ("Tera", "https://tera.inhire.app/vagas"),
    ("Cora", "https://cora.inhire.app/vagas"),
    ("Intera", "https://intera.inhire.app/vagas"),
    ("Sanar", "https://sanar.inhire.app/vagas"),
    ("Raro Labs", "https://rarolabs.inhire.app/vagas"),
    ("Cubos", "https://cubos.inhire.app/vagas"),
    ("Octafy", "https://octafy.inhire.app/vagas"),
    ("Qive", "https://qive.inhire.app/vagas"),
    ("DB1", "https://db1.inhire.app/vagas"),
    ("Cardápio Web", "https://cardapioweb.inhire.app/vagas"),
    ("Housi", "https://housi.inhire.app/vagas"),
    ("Grupo Taking", "https://grupotaking.inhire.app/vagas"),
    ("Dot Group", "https://dotgroup.inhire.app/vagas"),
    ("RPO XP Inc", "https://rpo-xpinc.inhire.app/vagas"),
    ("Grupo GCB Investimentos", "https://grupogcbinvestimentos.inhire.app/vagas"),
    ("Frete.com", "https://frete.inhire.app/vagas"),
    ("Cielo", "https://cielo.inhire.app/tecnologia/vagas"),
    ("Magazord", "https://magazord.inhire.app/vagas"),
    ("Inbazz", "https://inbazz.inhire.app/vagas"),
    ("Kobe Apps", "https://kobe.inhire.app/vagas"),
    ("Toro Investimentos", "https://toroinvestimentos.inhire.app/vagas"),
    ("Atlântico", "https://atlantico.inhire.app/vagas"),
    ("Auvo Tecnologia", "https://auvotecnologia.inhire.app/vagas"),
    ("Pris", "https://pris.inhire.app/vagas"),
    ("Bix Tecnologia", "https://bixtecnologia.inhire.app/vagas"),
]

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1,
    is_removed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_checked_at TEXT,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    archive_source TEXT,
    archive_reason TEXT,
    archive_note TEXT,
    is_highlighted INTEGER NOT NULL DEFAULT 0,
    is_new INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    archived_at TEXT,
    reopened_at TEXT,
    first_visited_at TEXT,
    last_visited_at TEXT,
    UNIQUE(company_id, external_id)
);

CREATE TABLE IF NOT EXISTS check_runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    heartbeat_at TEXT,
    status TEXT NOT NULL,
    companies_total INTEGER NOT NULL DEFAULT 0,
    companies_checked INTEGER NOT NULL DEFAULT 0,
    jobs_found INTEGER NOT NULL DEFAULT 0,
    jobs_new INTEGER NOT NULL DEFAULT 0,
    jobs_archived INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_seen
ON jobs(status, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_jobs_highlighted_status
ON jobs(is_highlighted, status);

CREATE INDEX IF NOT EXISTS idx_jobs_company_status
ON jobs(company_id, status);

CREATE INDEX IF NOT EXISTS idx_check_runs_status_finished
ON check_runs(status, finished_at DESC);
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def connection(database_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = database_path or DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(path, timeout=30)
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA foreign_keys = ON")
    database.execute("PRAGMA journal_mode = WAL")
    try:
        yield database
        database.commit()
    except Exception:
        database.rollback()
        raise
    finally:
        database.close()


def initialize_database(database_path: Path | None = None) -> None:
    now = utc_now()
    with connection(database_path) as database:
        database.executescript(SCHEMA)
        _migrate_jobs_archive_fields(database)
        _migrate_jobs_visit_fields(database)
        _migrate_check_runs_heartbeat(database)
        database.execute(
            "INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES (?, ?, ?)",
            ("highlight_keywords", json.dumps(DEFAULT_KEYWORDS, ensure_ascii=False), now),
        )
        database.executemany(
            """
            INSERT OR IGNORE INTO companies(name, url, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            [(name, url, now, now) for name, url in SEED_COMPANIES],
        )
        database.execute("PRAGMA optimize")


def _migrate_jobs_archive_fields(database: sqlite3.Connection) -> None:
    columns = {row["name"] for row in database.execute("PRAGMA table_info(jobs)")}
    if "archive_source" not in columns:
        database.execute("ALTER TABLE jobs ADD COLUMN archive_source TEXT")
    if "archive_note" not in columns:
        database.execute("ALTER TABLE jobs ADD COLUMN archive_note TEXT")
    database.execute(
        """
        UPDATE jobs
        SET archive_source = CASE archive_reason WHEN 'source' THEN 'source' ELSE 'manual' END,
            archive_reason = CASE archive_reason WHEN 'source' THEN 'source_removed' ELSE NULL END
        WHERE status = 'archived' AND archive_source IS NULL
        """
    )


def _migrate_jobs_visit_fields(database: sqlite3.Connection) -> None:
    columns = {row["name"] for row in database.execute("PRAGMA table_info(jobs)")}
    if "first_visited_at" not in columns:
        database.execute("ALTER TABLE jobs ADD COLUMN first_visited_at TEXT")
    if "last_visited_at" not in columns:
        database.execute("ALTER TABLE jobs ADD COLUMN last_visited_at TEXT")


def _migrate_check_runs_heartbeat(database: sqlite3.Connection) -> None:
    columns = {row["name"] for row in database.execute("PRAGMA table_info(check_runs)")}
    if "heartbeat_at" not in columns:
        database.execute("ALTER TABLE check_runs ADD COLUMN heartbeat_at TEXT")


def mark_interrupted_runs(database_path: Path | None = None) -> int:
    """Close out any check run still marked running from a previous process.

    A single web worker owns the scheduler, so when the app starts no check can
    genuinely be in progress. Any leftover running row means the process died
    mid-run; mark it failed so the activity page never shows a phantom run.
    """
    now = utc_now()
    with connection(database_path) as database:
        cursor = database.execute(
            """
            UPDATE check_runs
            SET status = 'failed', finished_at = ?,
                error = COALESCE(error, 'Interrupted before completion')
            WHERE status = 'running'
            """,
            (now,),
        )
        return cursor.rowcount


def record_run_progress(
    run_id: int,
    *,
    checked: int = 0,
    found: int = 0,
    new: int = 0,
    archived: int = 0,
    database_path: Path | None = None,
) -> None:
    """Fold one company's result into its check run and refresh the heartbeat."""
    with connection(database_path) as database:
        database.execute(
            """
            UPDATE check_runs
            SET heartbeat_at = ?,
                companies_checked = companies_checked + ?,
                jobs_found = jobs_found + ?,
                jobs_new = jobs_new + ?,
                jobs_archived = jobs_archived + ?
            WHERE id = ?
            """,
            (utc_now(), checked, found, new, archived, run_id),
        )


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with connection() as database:
        return list(database.execute(query, params).fetchall())


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    with connection() as database:
        return database.execute(query, params).fetchone()


def execute(query: str, params: tuple[Any, ...] = ()) -> int:
    with connection() as database:
        cursor = database.execute(query, params)
        return cursor.lastrowid


def get_keywords() -> list[str]:
    row = fetch_one("SELECT value FROM settings WHERE key = ?", ("highlight_keywords",))
    if not row:
        return DEFAULT_KEYWORDS.copy()
    return json.loads(row["value"])


def set_keywords(keywords: list[str]) -> None:
    execute(
        """
        INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        ("highlight_keywords", json.dumps(keywords, ensure_ascii=False), utc_now()),
    )
