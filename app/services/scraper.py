from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError


JOB_PATH_PATTERN = re.compile(r"/vagas/([^/?#]+)(?:/[^?#]+)?", re.IGNORECASE)
NEXT_LABEL_PATTERN = re.compile(
    r"^(próxima|proxima|próximo|proximo|next|carregar mais|ver mais|›|»)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ScrapedJob:
    external_id: str
    title: str
    url: str


def extract_external_id(url: str) -> str | None:
    match = JOB_PATH_PATTERN.search(urlparse(url).path)
    if not match:
        return None
    candidate = match.group(1).strip()
    if candidate.lower() in {"", "vagas"}:
        return None
    return candidate


async def _scroll_until_stable(page: Page) -> None:
    previous_height = 0
    stable_rounds = 0
    for _ in range(15):
        height = await page.evaluate("document.body.scrollHeight")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(250)
        if height == previous_height:
            stable_rounds += 1
            if stable_rounds >= 2:
                break
        else:
            stable_rounds = 0
        previous_height = height


async def _read_jobs(page: Page, company_url: str) -> list[ScrapedJob]:
    anchors = page.locator('a[href*="/vagas/"]')
    records: dict[str, ScrapedJob] = {}
    for index in range(await anchors.count()):
        anchor = anchors.nth(index)
        href = await anchor.get_attribute("href")
        if not href:
            continue
        absolute_url = urljoin(company_url, href)
        external_id = extract_external_id(absolute_url)
        if not external_id:
            continue
        title = " ".join((await anchor.inner_text()).split())
        if not title:
            title = (await anchor.get_attribute("aria-label") or "").strip()
        if not title:
            continue
        records[external_id] = ScrapedJob(external_id, title, absolute_url)
    return list(records.values())


async def _click_next_page(page: Page) -> bool:
    candidates = page.get_by_role("button").or_(page.get_by_role("link"))
    for index in range(await candidates.count()):
        candidate = candidates.nth(index)
        if not await candidate.is_visible() or not await candidate.is_enabled():
            continue
        label = " ".join((await candidate.inner_text()).split())
        aria_label = (await candidate.get_attribute("aria-label") or "").strip()
        if not (NEXT_LABEL_PATTERN.match(label) or NEXT_LABEL_PATTERN.match(aria_label)):
            continue
        try:
            await candidate.click(timeout=2_000)
            await page.wait_for_timeout(500)
            return True
        except PlaywrightTimeoutError:
            continue
    return False


async def scrape_company(page: Page, company_url: str) -> list[ScrapedJob]:
    await page.goto(company_url, wait_until="domcontentloaded", timeout=45_000)
    try:
        await page.locator('a[href*="/vagas/"]').first.wait_for(timeout=15_000)
    except PlaywrightTimeoutError:
        pass

    collected: dict[str, ScrapedJob] = {}
    visited_signatures: set[tuple[str, ...]] = set()

    for _ in range(50):
        await _scroll_until_stable(page)
        page_jobs = await _read_jobs(page, company_url)
        signature = tuple(sorted(job.external_id for job in page_jobs))
        if signature in visited_signatures:
            break
        visited_signatures.add(signature)
        collected.update({job.external_id: job for job in page_jobs})
        if not await _click_next_page(page):
            break

    return list(collected.values())

