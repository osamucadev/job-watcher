from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import urlparse

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import APP_NAME, STATIC_DIR, TEMPLATES_DIR
from app.database import connection, fetch_all, fetch_one, get_keywords, initialize_database, set_keywords, utc_now
from app.services.monitor import monitor
from app.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    await start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title=APP_NAME, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

ARCHIVE_REASONS = (
    ("applied", "Already applied", "Já me candidatei"),
    ("not_interested", "Not interested", "Não tenho interesse"),
    ("onsite", "On-site role", "Vaga presencial"),
    ("hybrid", "Hybrid role", "Vaga híbrida"),
    ("remote", "Remote role", "Vaga remota"),
    ("requirements", "Requirements do not match", "Requisitos incompatíveis"),
    ("compensation", "Compensation or conditions", "Remuneração ou condições"),
    ("closed", "Applications closed", "Inscrições encerradas"),
    ("other", "Other", "Outro"),
)
ARCHIVE_REASON_SLUGS = {reason[0] for reason in ARCHIVE_REASONS}
ARCHIVE_REASON_LABELS = {
    slug: {"en": label_en, "pt": label_pt}
    for slug, label_en, label_pt in ARCHIVE_REASONS
}
ARCHIVE_REASON_LABELS["source_removed"] = {
    "en": "Removed at source",
    "pt": "Removida na origem",
}


def common_context(request: Request, section: str) -> dict[str, object]:
    last_run = fetch_one(
        "SELECT * FROM check_runs ORDER BY started_at DESC LIMIT 1"
    )
    return {
        "request": request,
        "section": section,
        "last_run": last_run,
        "monitor_running": monitor.is_running,
        "archive_reasons": ARCHIVE_REASONS,
        "archive_reason_labels": ARCHIVE_REASON_LABELS,
    }


def safe_return_path(value: str, fallback: str) -> str:
    return value if value.startswith("/") and not value.startswith("//") else fallback


def jobs_for(view: str) -> list[object]:
    predicates = {
        "all": "j.status = 'active'",
        "highlighted": "j.status = 'active' AND j.is_highlighted = 1",
        "archived": "j.status = 'archived'",
    }
    if view not in predicates:
        raise HTTPException(status_code=404)
    return fetch_all(
        f"""
        SELECT j.*, c.name AS company_name
        FROM jobs j
        JOIN companies c ON c.id = j.company_id
        WHERE {predicates[view]}
        ORDER BY j.is_new DESC, j.first_seen_at DESC, j.title COLLATE NOCASE
        """
    )


@app.get("/")
async def dashboard(request: Request):
    stats = fetch_one(
        """
        SELECT
            COUNT(*) FILTER (WHERE status = 'active') AS active,
            COUNT(*) FILTER (WHERE status = 'active' AND is_new = 1) AS new,
            COUNT(*) FILTER (WHERE status = 'active' AND is_highlighted = 1) AS highlighted,
            COUNT(*) FILTER (WHERE status = 'archived') AS archived
        FROM jobs
        """
    )
    companies = fetch_one(
        """
        SELECT
            COUNT(*) FILTER (WHERE is_active = 1 AND is_removed = 0) AS active,
            COUNT(*) FILTER (WHERE last_error IS NOT NULL AND is_removed = 0) AS errors
        FROM companies
        """
    )
    recent_jobs = fetch_all(
        """
        SELECT j.*, c.name AS company_name
        FROM jobs j JOIN companies c ON c.id = j.company_id
        WHERE j.status = 'active'
        ORDER BY j.is_new DESC, j.first_seen_at DESC
        LIMIT 8
        """
    )
    context = common_context(request, "overview")
    context.update(stats=stats, company_stats=companies, jobs=recent_jobs)
    return templates.TemplateResponse("dashboard.html", context)


@app.get("/jobs")
async def all_jobs(request: Request):
    context = common_context(request, "jobs")
    context.update(jobs=jobs_for("all"), view="all")
    return templates.TemplateResponse("jobs.html", context)


@app.get("/jobs/highlighted")
async def highlighted_jobs(request: Request):
    context = common_context(request, "highlighted")
    context.update(jobs=jobs_for("highlighted"), view="highlighted")
    return templates.TemplateResponse("jobs.html", context)


@app.get("/jobs/archived")
async def archived_jobs(request: Request):
    context = common_context(request, "archived")
    context.update(jobs=jobs_for("archived"), view="archived")
    return templates.TemplateResponse("jobs.html", context)


@app.post("/jobs/{job_id}/archive")
async def archive_job(
    job_id: int,
    reason: str = Form(...),
    note: str = Form(""),
    return_to: str = Form("/jobs"),
):
    if reason not in ARCHIVE_REASON_SLUGS:
        raise HTTPException(status_code=422, detail="Invalid archive reason")
    with connection() as database:
        cursor = database.execute(
            """
            UPDATE jobs SET status = 'archived', archive_source = 'manual',
                archive_reason = ?, archive_note = ?, archived_at = ?, is_new = 0
            WHERE id = ?
            """,
            (reason, note.strip()[:500] or None, utc_now(), job_id),
        )
        if not cursor.rowcount:
            raise HTTPException(status_code=404)
    return RedirectResponse(safe_return_path(return_to, "/jobs"), status_code=303)


@app.post("/jobs/{job_id}/restore")
async def restore_job(job_id: int, return_to: str = Form("/jobs/archived")):
    with connection() as database:
        cursor = database.execute(
            """
            UPDATE jobs SET status = 'active', archive_source = NULL,
                archive_reason = NULL, archive_note = NULL, archived_at = NULL, reopened_at = ?
            WHERE id = ?
            """,
            (utc_now(), job_id),
        )
        if not cursor.rowcount:
            raise HTTPException(status_code=404)
    return RedirectResponse(safe_return_path(return_to, "/jobs/archived"), status_code=303)


@app.get("/companies")
async def companies(request: Request):
    context = common_context(request, "companies")
    context["companies"] = fetch_all(
        """
        SELECT c.*,
            COUNT(j.id) FILTER (WHERE j.status = 'active') AS active_jobs
        FROM companies c LEFT JOIN jobs j ON j.company_id = c.id
        WHERE c.is_removed = 0
        GROUP BY c.id
        ORDER BY c.name COLLATE NOCASE
        """
    )
    return templates.TemplateResponse("companies.html", context)


@app.post("/companies")
async def add_company(name: str = Form(...), url: str = Form(...)):
    clean_name = name.strip()
    clean_url = url.strip().rstrip("/")
    parsed = urlparse(clean_url)
    hostname = (parsed.hostname or "").casefold()
    if (
        not clean_name
        or parsed.scheme not in {"http", "https"}
        or not hostname.endswith(".inhire.app")
    ):
        return RedirectResponse("/companies?message=invalid", status_code=303)
    now = utc_now()
    with connection() as database:
        database.execute(
            """
            INSERT INTO companies(name, url, is_active, is_removed, created_at, updated_at)
            VALUES (?, ?, 1, 0, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                name = excluded.name, is_active = 1, is_removed = 0, updated_at = excluded.updated_at
            """,
            (clean_name, clean_url, now, now),
        )
    return RedirectResponse("/companies", status_code=303)


@app.post("/companies/{company_id}/toggle")
async def toggle_company(company_id: int):
    with connection() as database:
        database.execute(
            """
            UPDATE companies SET is_active = CASE is_active WHEN 1 THEN 0 ELSE 1 END,
                updated_at = ? WHERE id = ? AND is_removed = 0
            """,
            (utc_now(), company_id),
        )
    return RedirectResponse("/companies", status_code=303)


@app.post("/companies/{company_id}/remove")
async def remove_company(company_id: int):
    now = utc_now()
    with connection() as database:
        database.execute(
            "UPDATE companies SET is_active = 0, is_removed = 1, updated_at = ? WHERE id = ?",
            (now, company_id),
        )
        database.execute(
            """
            UPDATE jobs SET status = 'archived', archive_source = 'source',
                archive_reason = 'source_removed', archive_note = NULL,
                archived_at = ?, is_new = 0
            WHERE company_id = ? AND status = 'active'
            """,
            (now, company_id),
        )
    return RedirectResponse("/companies", status_code=303)


@app.get("/settings")
async def settings(request: Request):
    context = common_context(request, "settings")
    context["keywords"] = "\n".join(get_keywords())
    return templates.TemplateResponse("settings.html", context)


@app.post("/settings/keywords")
async def update_keywords(keywords: str = Form("")):
    values = sorted({line.strip() for line in keywords.splitlines() if line.strip()}, key=str.casefold)
    set_keywords(values)
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.post("/checks/run")
async def run_check(return_to: str = Form("/")):
    if not monitor.is_running:
        asyncio.create_task(monitor.run())
    return RedirectResponse(safe_return_path(return_to, "/"), status_code=303)


@app.get("/healthz")
async def healthcheck():
    return {"status": "ok", "time": datetime.now(UTC).isoformat()}
