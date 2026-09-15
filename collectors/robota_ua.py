"""Robota.ua collector — Ukraine's other major general job board.

Same rationale as work_ua.py (see that module's docstring): a native
Ukrainian/Russian speaker has a real edge on Ukrainian-market postings
regardless of physical location, and general boards surface bank/retail/
fintech analyst roles that IT-only boards like Djinni don't carry.

No RSS/keyword-search API exists publicly — robota.ua only documents a
per-company API (``api.robota.ua/companies/{id}/published-vacancies``),
useless for a cross-employer keyword search. A plain (non-browser) request
to robota.ua returns 403 even for robots.txt itself, so — like work_ua.py —
this collector requires full Playwright page navigation, not
``collectors.base.get_with_retry``.

URL scheme is confirmed by hand: ``/zapros/{query}/{city}`` requires a city
segment (a bare ``/zapros/{query}`` 404s) — ``ukraine`` is the special value
that means "all of Ukraine" rather than one city, which is what a
remote-eligible search needs. Pagination is
``/zapros/{query}/ukraine/params;page=N`` (a matrix parameter, not a query
string ``?page=``). Job detail URLs are ``/company{id}/vacancy{id}`` with no
distinguishing prefix segment, so they're matched by regex rather than a
fixed path prefix.
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext, Page

from collectors.base import BaseCollector, CollectorResult, per_query_share, setting
from core.metadata import extract_salary, infer_work_format
from core.ids import build_job_id
from core.models import JobRecord


ROBOTA_UA_BASE_URL = "https://robota.ua"
JOB_LINK_PATTERN = re.compile(r"^/company\d+/vacancy\d+$")
COMPANY_LINK_PATTERN = re.compile(r"^/company\d+$")
# Confirmed 2026-09-07: robota.ua returns a Cloudflare interstitial (HTTP 403,
# page title "Just a moment..." / "Attention Required! | Cloudflare") to
# Playwright automation from this environment — unlike work.ua, this happens
# in BOTH headless and non-headless mode, and with a completely fresh browser
# profile, so it isn't a headless-detection or stale-cookie issue. This
# source is NOT currently functional; kept selectable (and out of
# `--source all`, see scripts/collector.py) in case bot-protection
# circumvention becomes feasible later (e.g. a residential proxy or a
# stealth-patched browser). Without this check, a run silently "finds" 0
# links per page instead of surfacing the real cause.
CHALLENGE_TITLE_MARKERS = ("just a moment", "attention required", "checking your browser")


def is_challenge_page_title(title: str) -> bool:
    lowered = str(title or "").casefold()
    return any(marker in lowered for marker in CHALLENGE_TITLE_MARKERS)
# Marks the start of unrelated recommended/similar postings on a job detail
# page — cut here so full_text doesn't pick up other jobs' titles/skills,
# the same contamination bug already fixed for LinkedIn and work_ua.py.
CONTAMINATION_MARKERS = ("Гарячі вакансії", "Схожі вакансії")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = BeautifulSoup(text, "html.parser").get_text("\n", strip=True)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def build_search_url(query: str, page: int = 1) -> str:
    base = f"{ROBOTA_UA_BASE_URL}/zapros/{quote(query)}/ukraine"
    return f"{base}/params;page={page}" if page > 1 else base


def truncate_at_contamination(text: str) -> str:
    cut = len(text)
    for marker in CONTAMINATION_MARKERS:
        index = text.find(marker)
        if index != -1:
            cut = min(cut, index)
    return text[:cut]


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


async def extract_company(page: Page) -> str:
    """First /company{id} link with visible text — company profile links have
    no distinguishing class in this React app's markup, only the href shape.
    """
    links = page.locator("article a[href]")
    for index in range(await links.count()):
        link = links.nth(index)
        href = await link.get_attribute("href")
        if href and COMPANY_LINK_PATTERN.match(href):
            text = clean_text(await link.inner_text())
            if text:
                return text
    return ""


async def record_from_page(page: Page, *, query: str, category: str) -> JobRecord:
    title = await first_text(page, ["h1"])
    company = await extract_company(page)
    # No stable id/class for individual fields in this SPA (only a bare
    # data-id attribute) — same tradeoff as work_ua.py: take the whole
    # article body and let infer_work_format/extract_salary scan it as free
    # text rather than chasing per-field selectors that would break on the
    # next markup change.
    article_text = await first_text(page, ["article"])
    full_text = truncate_at_contamination(article_text).strip()
    work_format = infer_work_format(full_text)
    url = page.url
    record = JobRecord(
        source="Robota.ua",
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


class RobotaUaCollector(BaseCollector):
    """Collect matching postings from Robota.ua's nationwide keyword search."""

    source_name = "Robota.ua"

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or {}

    async def collect(self, context: BrowserContext, queries: list[dict[str, str]], limit: int) -> CollectorResult:
        result = CollectorResult(source=self.source_name, queries=[item["query"] for item in queries])
        timeout = int(setting(self.settings, "request", "timeout_seconds", default=60) * 1000)
        delay_ms = int(float(setting(self.settings, "request", "delay_min_seconds", default=1)) * 1000)
        max_pages = int(setting(self.settings, "sources", "robota_ua", "max_pages", default=5))
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
                            raise RuntimeError(
                                "Blocked by an anti-bot challenge page (confirmed unresolvable with a "
                                "plain Playwright browser as of 2026-09-07 - see module docstring)"
                            )
                        links = search_page.locator("a[href^='/company']")
                        page_added = 0
                        for index in range(await links.count()):
                            href = await links.nth(index).get_attribute("href")
                            if not href or not JOB_LINK_PATTERN.match(href):
                                continue
                            job_url = urljoin(ROBOTA_UA_BASE_URL, href)
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
                result.records.append(await record_from_page(page, query=query, category=category))
            except Exception as exc:
                result.errors += 1
                result.error_messages.append(f"{job_url}: {exc}")
            finally:
                await page.close()
        return result
