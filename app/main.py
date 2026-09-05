from __future__ import annotations

import asyncio
import math
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import urlencode, urlparse

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import (
    ACTIVITY_HISTORY_LIMIT,
    APP_NAME,
    PAGE_SIZE,
    STALE_RUN_SECONDS,
    STATIC_DIR,
    TEMPLATES_DIR,
)
from app.database import (
    connection,
    fetch_all,
    fetch_one,
    get_keywords,
    initialize_database,
    mark_interrupted_runs,
    set_keywords,
    utc_now,
)
from app.services.monitor import monitor
from app.services.pagination import normalize_page, page_sequence
from app.services.scheduler import next_scheduled_run, start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    mark_interrupted_runs()
    await start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title=APP_NAME, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

ASSET_VERSION = utc_now()

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


def run_looks_stalled(run: object) -> bool:
    if not run or run["status"] != "running":
        return False
    stamp = run["heartbeat_at"] or run["started_at"]
    try:
        last_beat = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return False
    return (datetime.now(UTC) - last_beat).total_seconds() > STALE_RUN_SECONDS


def common_context(request: Request, section: str) -> dict[str, object]:
    last_run = fetch_one(
        "SELECT * FROM check_runs ORDER BY started_at DESC LIMIT 1"
    )
    return {
        "request": request,
        "section": section,
        "last_run": last_run,
        "monitor_running": monitor.is_running,
        "monitor_progress": monitor.snapshot(),
        "run_stalled": run_looks_stalled(last_run),
        "archive_reasons": ARCHIVE_REASONS,
        "archive_reason_labels": ARCHIVE_REASON_LABELS,
        "asset_version": ASSET_VERSION,
    }


def safe_return_path(value: str, fallback: str) -> str:
    return value if value.startswith("/") and not value.startswith("//") else fallback


def wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


JOB_VIEW_PREDICATES = {
    "all": "j.status = 'active'",
    "highlighted": "j.status = 'active' AND j.is_highlighted = 1",
    "archived": "j.status = 'archived'",
}


def jobs_predicate(view: str) -> str:
    if view not in JOB_VIEW_PREDICATES:
        raise HTTPException(status_code=404)
    return JOB_VIEW_PREDICATES[view]


def count_jobs_for(view: str) -> int:
    predicate = jobs_predicate(view)
    row = fetch_one(f"SELECT COUNT(*) AS total FROM jobs j WHERE {predicate}")
    return row["total"]


def jobs_for(view: str, *, limit: int, offset: int) -> list[object]:
    predicate = jobs_predicate(view)
    return fetch_all(
        f"""
        SELECT j.*, c.name AS company_name
        FROM jobs j
        JOIN companies c ON c.id = j.company_id
        WHERE {predicate}
        ORDER BY j.is_new DESC, j.first_seen_at DESC, j.title COLLATE NOCASE
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )


def page_url(request: Request, page: int) -> str:
    params = dict(request.query_params)
    params["page"] = str(page)
    return f"{request.url.path}?{urlencode(params)}"


def build_pagination(request: Request, page: int, total_pages: int, total_count: int) -> dict[str, object] | None:
    if total_pages <= 1:
        return None
    entries = []
    for entry in page_sequence(page, total_pages):
        if entry == "…":
            entries.append({"kind": "ellipsis"})
        else:
            entries.append({"kind": "page", "number": entry, "url": page_url(request, entry)})
    return {"current": page, "total_pages": total_pages, "total_count": total_count, "entries": entries}


def paginated_jobs_response(request: Request, view: str, section: str):
    total_count = count_jobs_for(view)
    total_pages = math.ceil(total_count / PAGE_SIZE) if total_count else 0
    page = normalize_page(request.query_params.get("page"), total_pages)
    offset = (page - 1) * PAGE_SIZE
    jobs = jobs_for(view, limit=PAGE_SIZE, offset=offset)

    context = common_context(request, section)
    context.update(
        jobs=jobs,
        view=view,
        total_count=total_count,
        pagination=build_pagination(request, page, total_pages, total_count),
    )
    return templates.TemplateResponse("jobs.html", context)


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
    return paginated_jobs_response(request, "all", "jobs")


@app.get("/jobs/highlighted")
async def highlighted_jobs(request: Request):
    return paginated_jobs_response(request, "highlighted", "highlighted")


@app.get("/jobs/archived")
async def archived_jobs(request: Request):
    return paginated_jobs_response(request, "archived", "archived")


@app.post("/jobs/{job_id}/archive")
async def archive_job(
    request: Request,
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
    if wants_json(request):
        return {"ok": True}
    return RedirectResponse(safe_return_path(return_to, "/jobs"), status_code=303)


@app.post("/jobs/{job_id}/restore")
async def restore_job(request: Request, job_id: int, return_to: str = Form("/jobs/archived")):
    with connection() as database:
        cursor = database.execute(
            """
            UPDATE jobs SET status = 'active', archive_source = NULL,
                archive_reason = NULL, archive_note = NULL, archived_at = NULL, reopened_at = NULL
            WHERE id = ?
            """,
            (job_id,),
        )
        if not cursor.rowcount:
            raise HTTPException(status_code=404)
    if wants_json(request):
        return {"ok": True}
    return RedirectResponse(safe_return_path(return_to, "/jobs/archived"), status_code=303)


@app.post("/jobs/{job_id}/visit")
async def visit_job(job_id: int):
    now = utc_now()
    with connection() as database:
        cursor = database.execute(
            """
            UPDATE jobs
            SET first_visited_at = COALESCE(first_visited_at, ?), last_visited_at = ?
            WHERE id = ?
            """,
            (now, now, job_id),
        )
        if not cursor.rowcount:
            raise HTTPException(status_code=404)
    return {"ok": True}


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


def _run_duration_seconds(run: object) -> float | None:
    if not run["finished_at"]:
        return None
    try:
        started = datetime.fromisoformat(run["started_at"])
        finished = datetime.fromisoformat(run["finished_at"])
    except (TypeError, ValueError):
        return None
    return round((finished - started).total_seconds(), 1)


@app.get("/activity")
async def activity(request: Request):
    context = common_context(request, "activity")
    history = [
        {**dict(run), "duration_seconds": _run_duration_seconds(run)}
        for run in fetch_all(
            "SELECT * FROM check_runs ORDER BY started_at DESC LIMIT ?",
            (ACTIVITY_HISTORY_LIMIT,),
        )
    ]
    companies = fetch_all(
        """
        SELECT c.name, c.url, c.is_active, c.last_checked_at, c.last_error,
            COUNT(j.id) FILTER (WHERE j.status = 'active') AS active_jobs
        FROM companies c LEFT JOIN jobs j ON j.company_id = c.id
        WHERE c.is_removed = 0
        GROUP BY c.id
        ORDER BY c.name COLLATE NOCASE
        """
    )
    next_run = next_scheduled_run()
    context.update(
        history=history,
        companies=companies,
        next_run=next_run.isoformat() if next_run else None,
    )
    return templates.TemplateResponse("activity.html", context)


@app.post("/checks/run")
async def run_check(return_to: str = Form("/")):
    if not monitor.is_running:
        asyncio.create_task(monitor.run())
    return RedirectResponse(safe_return_path(return_to, "/"), status_code=303)


@app.get("/healthz")
async def healthcheck():
    return {"status": "ok", "time": datetime.now(UTC).isoformat()}
