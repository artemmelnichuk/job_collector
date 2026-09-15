"""Work.ua collector — Ukraine's largest *general* (not IT-only) job board.

Added alongside Djinni because Djinni skews toward IT/dev roles, while
analyst positions at Ukrainian banks, retail, and fintech companies (which
value Excel/reporting more than deep coding) show up on Work.ua instead —
see PROJECT context: the candidate is a native Ukrainian/Russian speaker,
which is a real edge on the Ukrainian market regardless of physical location
(remote-eligible postings don't require being in Ukraine).

No RSS/public search API exists (confirmed by checking robots.txt and
searching for one) — this is Playwright-rendered HTML, same fragility
tradeoff as linkedin.py/wttj.py, not the plain-HTTP-GET reliability of
djinni.py/company_careers.py. A plain (non-browser) HTTP request to a
work.ua page returns 403 even though a real browser loads it fine, so this
collector must use full page navigation (`page.goto`), not
`collectors.base.get_with_retry`.

**STILL NOT DEPENDABLE — revised 2026-09-08.** A realistic Chrome
`user_agent` + `uk-UA` locale + explicit `Accept-Language` header
(`STEALTH_USER_AGENT`/`STEALTH_LOCALE`/`STEALTH_HEADERS` below, launched as
a dedicated context by `scripts/collector.py` rather than changing the
shared context LinkedIn/WTTJ rely on) measurably helps — 3/3 trials passed
right after switching to it — but does NOT eliminate the block: the same
dedicated profile got challenged again (HTTP 403, Cloudflare's Ukrainian-
language interstitial "Трохи зачекайте…") after only a handful more
requests in a later run. This reads as IP/request-volume-based rate limiting
on top of (not instead of) fingerprint checking, which no header tuning
alone fixes. `is_challenge_page_title()` (now matching the Ukrainian
challenge title too, not just the English ones) turns a block into a clear
error instead of a silent "0 results" either way. Treat this source as
usable for occasional short bursts from a fresh profile, not a dependable
member of unattended `--source all` runs — kept out of `all` for that
reason; select it explicitly and expect it to work intermittently.

robots.txt disallows several query-string search filters (employment=,
salaryfrom=, salaryto=, sort=, experience=, etc.) and `/jobs-*-/` (a
trailing-hyphen slug pattern used by old multi-segment category+location
URLs) — neither is used here: search is a plain `/jobs-{query}/` slug with
`+` between words, and pagination is the allowed `?page=N` parameter.
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext, Page

from collectors.base import BaseCollector, CollectorResult, per_query_share, setting
from core.metadata import extract_salary, infer_work_format
from core.ids import build_job_id
from core.models import JobRecord


WORK_UA_BASE_URL = "https://www.work.ua"
JOB_LINK_PATTERN = re.compile(r"^/jobs/\d+/$")
# Marks the end of the real posting and the start of an unrelated "similar
# jobs" list — without this cut, full_text picks up other postings' titles
# and requirements, the same contamination bug already fixed for LinkedIn.
SIMILAR_JOBS_MARKER = "Схожі вакансії"
# Confirmed 2026-09-07: work.ua returns a Cloudflare interstitial (HTTP 403,
# page title "Just a moment...") to HEADLESS Playwright specifically — the
# exact same request succeeds with a visible (non-headless) browser. Without
# this check, a --headless run silently "finds" 0 links per page (looks
# identical to a query with no results) instead of surfacing the real cause.
CHALLENGE_TITLE_MARKERS = (
    "just a moment", "attention required", "checking your browser",
    # Ukrainian equivalent — Cloudflare serves the challenge page in the
    # request's own locale, and this collector deliberately sets locale=uk-UA
    # (see STEALTH_LOCALE), so the English markers alone miss it.
    "трохи зачекайте",
)


def is_challenge_page_title(title: str) -> bool:
    lowered = str(title or "").casefold()
    return any(marker in lowered for marker in CHALLENGE_TITLE_MARKERS)


# Confirmed 2026-09-07 (after the above was written): the block was not
# actually a headless/non-headless split — the default browser context (no
# explicit user_agent/locale/Accept-Language, "en-US" locale from
# settings.yaml) gets challenged, but a context launched with a realistic
# Chrome user_agent, Ukrainian locale, and an explicit Accept-Language header
# passed 3/3 repeated trials (fresh profile each time). scripts/collector.py
# launches a dedicated context with these for work_ua specifically, rather
# than changing the shared context's fingerprint (which LinkedIn etc. rely on
# working as-is). If this collector starts failing again, re-verify with
# tests/manual runs before assuming the fingerprint fix has stopped working —
# Cloudflare's rules can change.
STEALTH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
STEALTH_LOCALE = "uk-UA"
STEALTH_HEADERS = {"Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8"}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = BeautifulSoup(text, "html.parser").get_text("\n", strip=True)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def build_search_url(query: str, page: int = 1) -> str:
    base = f"{WORK_UA_BASE_URL}/jobs-{quote_plus(query)}/"
    return f"{base}?page={page}" if page > 1 else base


async def first_text(page: Page, selectors: list[str]) -> str:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.count() and await locator.is_visible():
                value = clean_text(await locator.inner_text())
                if value:
                    return value
        except Exception:
            continue
    return ""


async def record_from_page(page: Page, *, query: str, category: str) -> JobRecord:
    title = await first_text(page, ["#h1-name"])
    # The company name link's href is /jobs/by-company/{id}/ — unique enough
    # on the page that this doesn't need a more specific ancestor scope.
    company = await first_text(page, ["a.inline"])
    description = await first_text(page, ["#job-description"])
    # Salary/work-format/employment-type badges render as plain <li> text
    # near the title with no stable id/class (utility-CSS, changes with any
    # redesign) — grabbing the whole main content area and cutting it off
    # before the "similar jobs" section is far more robust than chasing that
    # specific markup, and infer_work_format/extract_salary already work by
    # scanning free text rather than requiring an exact field.
    main_text = await first_text(page, ["#center"])
    header = main_text.split(SIMILAR_JOBS_MARKER)[0] if main_text else ""
    full_text = f"{header}\n\n{description}".strip()
    work_format = infer_work_format(full_text)
    url = page.url
    record = JobRecord(
        source="Work.ua",
        date_collected=datetime.now().astimezone().isoformat(timespec="seconds"),
        title=title,
        company=company,
        city_region="",
        country="Ukraine",
        work_format=work_format,
        source_work_format=work_format,
        salary=extract_salary({}, full_text),
        url=url,
        full_text=full_text,
        status="collected",
        availability_status="active",
        search_query=query,
        job_category=category or "other",
    )
    record.job_id = build_job_id(record)
    return record


class WorkUaCollector(BaseCollector):
    """Collect matching postings from Work.ua's free-text keyword search."""

    source_name = "Work.ua"

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or {}

    async def collect(self, context: BrowserContext, queries: list[dict[str, str]], limit: int) -> CollectorResult:
        result = CollectorResult(source=self.source_name, queries=[item["query"] for item in queries])
        timeout = int(setting(self.settings, "request", "timeout_seconds", default=60) * 1000)
        delay_ms = int(float(setting(self.settings, "request", "delay_min_seconds", default=1)) * 1000)
        max_pages = int(setting(self.settings, "sources", "work_ua", "max_pages", default=5))
        urls: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        query_cap = per_query_share(limit, len(queries))
        search_page = await context.new_page()
        try:
            for item in queries:
                query, category = item["query"], item.get("category", "other")
                query_added = 0
                try:
                    for page_number in range(1, max_pages + 1):
                        await search_page.goto(
                            build_search_url(query, page_number), wait_until="domcontentloaded", timeout=timeout
                        )
                        await search_page.wait_for_timeout(delay_ms)
                        if is_challenge_page_title(await search_page.title()):
                            raise RuntimeError("Blocked by an anti-bot challenge page on the search results")
                        links = search_page.locator("a[href^='/jobs/']")
                        page_added = 0
                        for index in range(await links.count()):
                            href = await links.nth(index).get_attribute("href")
                            if not href or not JOB_LINK_PATTERN.match(href):
                                continue
                            job_url = urljoin(WORK_UA_BASE_URL, href)
                            if job_url not in seen:
                                seen.add(job_url)
                                urls.append((job_url, query, category))
                                page_added += 1
                                query_added += 1
                                if len(urls) >= limit or query_added >= query_cap:
                                    break
                        if len(urls) >= limit or query_added >= query_cap or page_added == 0:
                            break
                except Exception as exc:
                    result.errors += 1
                    result.error_messages.append(f"Search {query}: {exc}")
                if len(urls) >= limit:
                    break
        finally:
            await search_page.close()
        result.found = len(urls)
        for job_url, query, category in urls:
            page = await context.new_page()
            try:
                await page.goto(job_url, wait_until="domcontentloaded", timeout=timeout)
                await page.wait_for_timeout(delay_ms)
                if is_challenge_page_title(await page.title()):
                    raise RuntimeError("Blocked by an anti-bot challenge page on the job detail page")
                result.records.append(await record_from_page(page, query=query, category=category))
            except Exception as exc:
                result.errors += 1
                result.error_messages.append(f"{job_url}: {exc}")
            finally:
                await page.close()
        return result
