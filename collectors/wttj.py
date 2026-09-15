"""Welcome to the Jungle collector using the shared collector contract."""

from __future__ import annotations

import html
import ast
import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

from collectors.base import BaseCollector, CollectorResult, per_query_share, setting
from core.metadata import extract_salary, infer_work_format as infer_metadata_work_format
from core.ids import build_job_id
from core.models import JobRecord

WTTJ_BASE_URL = "https://www.welcometothejungle.com"
DEFAULT_SEARCH_URL_TEMPLATE = WTTJ_BASE_URL + "/en/jobs?query={query}"
AUTH_PATH_MARKERS = ("/authenticate/", "/login", "/signup", "/signin")
CLOSED_JOB_MARKERS = (
    "job is no longer available",
    "this job has expired",
    "position has been filled",
    "offre n'est plus disponible",
    "offre a été pourvue",
)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = BeautifulSoup(text, "html.parser").get_text("\n", strip=True)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def build_search_url(query: str, template: str = DEFAULT_SEARCH_URL_TEMPLATE) -> str:
    return template.format(query=quote(query))


def page_requires_auth(url: str) -> bool:
    """Detect WTTJ's authenticated job-matching flow by URL."""
    lowered = url.casefold()
    return any(marker in lowered for marker in AUTH_PATH_MARKERS)


def detect_availability_status(current_url: str, body_text: str) -> str:
    """Classify a WTTJ detail page from visible text."""
    if page_requires_auth(current_url):
        return "unknown"
    lowered = body_text.casefold()
    if any(marker in lowered for marker in CLOSED_JOB_MARKERS):
        return "closed"
    return "active" if "/jobs/" in current_url.casefold() and body_text.strip() else "unknown"


def parse_json_ld(raw: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    values = value if isinstance(value, list) else [value]
    for item in values:
        if isinstance(item, dict) and item.get("@type") == "JobPosting":
            return item
    return None


def infer_work_format(text: str) -> str:
    return infer_metadata_work_format(text)


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


async def json_ld_job(page: Page) -> dict[str, Any] | None:
    scripts = page.locator('script[type="application/ld+json"]')
    for index in range(await scripts.count()):
        raw = await scripts.nth(index).text_content()
        if raw and (job := parse_json_ld(raw)):
            return job
    return None


async def wait_for_manual_login(page: Page, timeout_seconds: int) -> None:
    """Wait for the user to finish WTTJ login in the persistent browser."""
    print(
        "[WTTJ] Login is required to access job results. Complete it in the open Chromium window; "
        f"waiting up to {timeout_seconds} seconds."
    )
    for _ in range(max(timeout_seconds, 1)):
        if not page_requires_auth(page.url):
            print("[WTTJ] Login detected, continuing collection.")
            return
        await page.wait_for_timeout(1000)
    raise TimeoutError("WTTJ login was not completed within the configured timeout")


async def submit_search(page: Page, query: str, timeout: int) -> None:
    """Use the current WTTJ search form when query URLs show the landing page."""
    textbox = page.get_by_role("textbox").first
    if await textbox.count() and await textbox.is_visible():
        await textbox.fill(query)
        button = page.get_by_role("button", name=re.compile("search", re.IGNORECASE)).first
        if await button.count() and await button.is_visible():
            await button.click()
            await page.wait_for_load_state("domcontentloaded", timeout=timeout)


def _value(value: Any) -> str:
    if isinstance(value, dict):
        return clean_text(value.get("name") or value.get("value") or value.get("addressLocality"))
    return clean_text(value)


def location_parts(value: Any) -> tuple[str, str]:
    """Extract a readable location and country from JobPosting.jobLocation."""
    locations = value if isinstance(value, list) else [value]
    readable: list[str] = []
    countries: list[str] = []

    for location in locations:
        if not isinstance(location, dict):
            continue
        address = location.get("address", location)
        if not isinstance(address, dict):
            continue

        parts = [
            clean_text(address.get("addressLocality")),
            clean_text(address.get("addressRegion")),
        ]
        country = clean_text(address.get("addressCountry"))
        if country:
            countries.append(country)
        if country and country not in parts:
            parts.append(country)
        value_text = ", ".join(dict.fromkeys(part for part in parts if part))
        if value_text:
            readable.append(value_text)

    return " / ".join(dict.fromkeys(readable)), " / ".join(dict.fromkeys(countries))


def normalize_saved_location(value: Any) -> tuple[str, str]:
    """Normalize current or legacy WTTJ location values from saved records."""
    parsed = value
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return clean_text(value), ""
    return location_parts(parsed)


async def record_from_page(page: Page, search_query: str, category: str) -> JobRecord:
    job = await json_ld_job(page) or {}
    body = clean_text(await page.locator("body").inner_text())
    title = _value(job.get("title")) or await first_text(page, ["h1", "[data-testid='job-title']"])
    company_data = job.get("hiringOrganization", {})
    company = _value(company_data) or await first_text(page, ["[data-testid='job-company-name']", "a[href*='/companies/']"])
    location_data = job.get("jobLocation", {})
    location, country = location_parts(location_data)
    location = location or await first_text(page, ["[data-testid='job-location']"])
    country = country or (location.rsplit(",", 1)[-1].strip() if "," in location else "")
    date_published = _value(job.get("datePosted"))
    work_format = infer_work_format(body)
    url = page.url
    record = JobRecord(
        source="Welcome to the Jungle",
        date_collected=datetime.now().astimezone().isoformat(timespec="seconds"),
        date_published=date_published,
        title=title,
        company=company,
        city_region=location,
        country=country,
        work_format=work_format,
        source_work_format=work_format,
        contract_type=_value(job.get("employmentType")),
        salary=extract_salary(job.get("baseSalary"), body),
        url=url,
        full_text=clean_text(job.get("description")) or body,
        status="collected",
        availability_status=detect_availability_status(page.url, body),
        search_query=search_query,
        job_category=category or "other",
    )
    record.job_id = build_job_id(record)
    return record


class WttjCollector(BaseCollector):
    source_name = "Welcome to the Jungle"

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or {}

    async def collect(self, context: BrowserContext, queries: list[dict[str, str]], limit: int) -> CollectorResult:
        result = CollectorResult(source=self.source_name, queries=[item["query"] for item in queries])
        timeout = int(setting(self.settings, "request", "timeout_seconds", default=60) * 1000)
        login_timeout = int(setting(self.settings, "browser", "manual_login_timeout_seconds", default=180))
        template = setting(self.settings, "sources", "wttj", "search_url_template", default=DEFAULT_SEARCH_URL_TEMPLATE)
        delay_ms = int(float(setting(self.settings, "request", "delay_min_seconds", default=1)) * 1000)
        max_pages = int(setting(self.settings, "sources", "wttj", "max_pages", default=15))
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
                        search_url = build_search_url(query, template)
                        separator = "&" if "?" in search_url else "?"
                        await search_page.goto(f"{search_url}{separator}page={page_number}", wait_until="domcontentloaded", timeout=timeout)
                        await search_page.wait_for_timeout(delay_ms)
                        if "/pages/" not in template:
                            await submit_search(search_page, query, timeout)
                        if page_requires_auth(search_page.url):
                            await wait_for_manual_login(search_page, login_timeout)
                        links = search_page.locator("a[href*='/jobs/']")
                        page_added = 0
                        for index in range(await links.count()):
                            href = await links.nth(index).get_attribute("href")
                            if not href:
                                continue
                            url = urljoin(WTTJ_BASE_URL, href).split("?")[0]
                            if url not in seen:
                                seen.add(url)
                                urls.append((url, query, category))
                                page_added += 1
                                query_added += 1
                                if len(urls) >= limit or query_added >= query_cap:
                                    break
                        if len(urls) >= limit or query_added >= query_cap or page_added == 0:
                            break
                    if query_added == 0:
                        result.error_messages.append(
                            f"Search {query}: WTTJ returned no public job links; login/job matching may be required."
                        )
                except Exception as exc:
                    result.errors += 1
                    result.error_messages.append(f"Search {query}: {exc}")
                if len(urls) >= limit:
                    break
        finally:
            await search_page.close()
        result.found = len(urls)
        for url, query, category in urls:
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                await page.wait_for_timeout(delay_ms)
                result.records.append(await record_from_page(page, query, category))
            except (PlaywrightTimeoutError, Exception) as exc:
                result.errors += 1
                result.error_messages.append(f"{url}: {exc}")
            finally:
                await page.close()
        return result
