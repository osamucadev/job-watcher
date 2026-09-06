from __future__ import annotations

import asyncio
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


API_URL = "https://api.inhire.app/job-posts/public/pages/lean"
DEFAULT_CAREER_PAGE = "default"

REQUEST_TIMEOUT = httpx.Timeout(15.0, connect=10.0)
MAX_CONCURRENCY = 5
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 1.0
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

JOB_PATH_PATTERN = re.compile(r"/vagas/([^/?#]+)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ScrapedJob:
    external_id: str
    title: str
    url: str


class CollectionError(RuntimeError):
    """Raised when a company listing could not be retrieved or trusted.

    Raising this instead of returning an empty list guarantees the monitor
    never treats a failed collection as "the company has no jobs" and never
    archives every job because of a transient or structural failure.
    """


def extract_external_id(url: str) -> str | None:
    match = JOB_PATH_PATTERN.search(urlparse(url).path)
    if not match:
        return None
    candidate = match.group(1).strip()
    if candidate.lower() in {"", "vagas"}:
        return None
    return candidate


def extract_tenant(company_url: str) -> str:
    host = (urlparse(company_url).hostname or "").strip().lower()
    label = host.split(".")[0] if host else ""
    if not label or label in {"inhire", "www", "api"}:
        raise CollectionError(f"Cannot determine InHire tenant from URL: {company_url!r}")
    return label


def extract_career_page(company_url: str) -> str:
    segments = [segment for segment in urlparse(company_url).path.split("/") if segment]
    if segments and segments[-1].lower() == "vagas":
        segments = segments[:-1]
    return segments[0] if segments else DEFAULT_CAREER_PAGE


def _record_career_pages(record: dict) -> set[str]:
    values: set[str] = set()
    identifier = record.get("careerPageId")
    if isinstance(identifier, str) and identifier:
        values.add(identifier)
    career_page = record.get("careerPage")
    if isinstance(career_page, dict):
        for key in ("careerPage", "id", "name"):
            value = career_page.get(key)
            if isinstance(value, str) and value:
                values.add(value)
    return values


def _job_slug(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title.casefold())
    ascii_title = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character) and ord(character) < 128
    )
    # InHire removes paired punctuation instead of treating it as a word break.
    # This turns "Desenvolvedor(a)" into "desenvolvedora".
    ascii_title = re.sub(r"[()\[\]{}'\"]", "", ascii_title)
    return re.sub(r"[^a-z0-9]+", "-", ascii_title).strip("-")


def _job_link(company_url: str, job_id: str, title: str) -> str:
    parsed = urlparse(company_url)
    path = parsed.path.rstrip("/")
    if not path.lower().endswith("/vagas"):
        path = f"{path}/vagas" if path else "/vagas"
    base_url = f"{parsed.scheme}://{parsed.netloc}{path}/{job_id}"
    slug = _job_slug(title)
    return f"{base_url}/{slug}" if slug else base_url


def records_to_jobs(records: list[dict], company_url: str, career_page: str) -> list[ScrapedJob]:
    jobs: dict[str, ScrapedJob] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        if career_page not in _record_career_pages(record):
            continue
        job_id = record.get("jobId")
        title = (record.get("displayName") or "").strip()
        if not isinstance(job_id, str) or not job_id or not title:
            continue
        jobs[job_id] = ScrapedJob(job_id, title, _job_link(company_url, job_id, title))
    return list(jobs.values())


async def _fetch_records(client: httpx.AsyncClient, tenant: str) -> list[dict]:
    headers = {"Content-Type": "application/json", "X-Tenant": tenant}
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await client.get(API_URL, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as error:
            last_error = error
        else:
            if response.status_code in RETRYABLE_STATUS_CODES:
                last_error = CollectionError(
                    f"InHire API returned HTTP {response.status_code} for tenant {tenant!r}"
                )
            elif response.status_code >= 400:
                raise CollectionError(
                    f"InHire API returned HTTP {response.status_code} for tenant {tenant!r}"
                )
            else:
                try:
                    payload = response.json()
                except ValueError as error:
                    raise CollectionError(
                        f"InHire API returned invalid JSON for tenant {tenant!r}"
                    ) from error
                if not isinstance(payload, list):
                    raise CollectionError(
                        f"InHire API returned an unexpected payload for tenant {tenant!r}"
                    )
                return payload

        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)

    raise CollectionError(
        f"InHire API request failed for tenant {tenant!r} after {MAX_ATTEMPTS} attempts: {last_error}"
    )


async def collect_company(client: httpx.AsyncClient, company_url: str) -> list[ScrapedJob]:
    tenant = extract_tenant(company_url)
    career_page = extract_career_page(company_url)
    records = await _fetch_records(client, tenant)

    if career_page != DEFAULT_CAREER_PAGE:
        known_pages: set[str] = set()
        for record in records:
            if isinstance(record, dict):
                known_pages |= _record_career_pages(record)
        if career_page not in known_pages:
            raise CollectionError(
                f"Career page {career_page!r} was not present in the InHire response "
                f"for tenant {tenant!r}; refusing to archive jobs on an unconfirmed page"
            )

    return records_to_jobs(records, company_url, career_page)
