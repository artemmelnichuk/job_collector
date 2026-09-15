"""RemoteOK collector — remote-only tech job board, via its public JSON API.

Plain HTTP GET + JSON, no browser rendering needed — same shape as the
Greenhouse/Lever adapters in company_careers.py.

IMPORTANT: the documented ``?tag=`` query parameter does NOT filter the feed
server-side — passing it returns zero postings (just the API's legal-notice
header), verified 2026-09-06 against https://remoteok.com/api?tag=data-analyst.
The unfiltered endpoint also only ever returns the ~100 most-recently-posted
jobs platform-wide, not a paginated full archive, so this collector polls
that fixed recent window and filters locally by title via query_matches
(same as company_careers.py) — there is no way to ask RemoteOK for "every
Data Analyst posting ever". Spot-checking the unfiltered feed found only
2-4 analyst/data-titled postings per 100 recent jobs, so expect this source
to contribute a handful of records per run, accumulating as the feed rotates
across repeated runs rather than yielding a bulk one-time result.

Every posting on RemoteOK is remote by the site's own definition, so
work_format is set directly rather than inferred from text.
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext

from collectors.base import BaseCollector, CollectorResult, get_with_retry, setting
from core.ids import build_job_id
from core.metadata import extract_salary, infer_country, query_matches
from core.models import JobRecord


REMOTEOK_API_URL = "https://remoteok.com/api"


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text("\n", strip=True)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_jobs(payload: Any) -> list[dict[str, Any]]:
    """Drop the feed's leading legal-notice entry (it has no "position" field)."""
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict) and item.get("position")]


def format_salary(job: dict[str, Any]) -> str:
    minimum, maximum = job.get("salary_min"), job.get("salary_max")
    if not minimum and not maximum:
        return ""
    if minimum and maximum and minimum != maximum:
        return f"{minimum}-{maximum} USD"
    return f"{minimum or maximum} USD"


def record_from_job(job: dict[str, Any], query: dict[str, str]) -> JobRecord:
    location = clean_text(job.get("location"))
    description = clean_text(job.get("description"))
    url = clean_text(job.get("url") or job.get("apply_url"))
    record = JobRecord(
        source="RemoteOK",
        date_collected=datetime.now().astimezone().isoformat(timespec="seconds"),
        date_published=clean_text(job.get("date")),
        title=clean_text(job.get("position")),
        company=clean_text(job.get("company")),
        city_region=location,
        country=infer_country(location),
        work_format="Remote",
        source_work_format="Remote",
        salary=format_salary(job) or extract_salary({}, description),
        url=url,
        full_text=description,
        status="collected",
        availability_status="active",
        note="Source: RemoteOK public API",
        search_query=query["query"],
        job_category=query["category"],
    )
    record.job_id = build_job_id(record)
    return record


class RemoteOkCollector(BaseCollector):
    """Collect matching postings from RemoteOK's public, unfiltered feed."""

    source_name = "RemoteOK"

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or {}

    async def collect(self, context: BrowserContext, queries: list[dict[str, str]], limit: int) -> CollectorResult:
        result = CollectorResult(source=self.source_name, queries=[item["query"] for item in queries])
        timeout_ms = int(setting(self.settings, "request", "timeout_seconds", default=60) * 1000)
        retry_attempts = int(setting(self.settings, "request", "retry_attempts", default=0))
        delay_min = float(setting(self.settings, "request", "delay_min_seconds", default=1.0))
        delay_max = float(setting(self.settings, "request", "delay_max_seconds", default=delay_min))
        seen_urls: set[str] = set()

        try:
            response = await get_with_retry(
                context, REMOTEOK_API_URL, timeout_ms=timeout_ms, retry_attempts=retry_attempts,
                delay_min_seconds=delay_min, delay_max_seconds=delay_max,
            )
            payload = await response.json()
        except Exception as error:
            result.errors += 1
            result.error_messages.append(f"RemoteOK feed: {error}")
            return result

        for job in parse_jobs(payload):
            if len(result.records) >= limit:
                break
            title = clean_text(job.get("position"))
            query = next((item for item in queries if query_matches(item["query"], title)), None)
            if query is None:
                continue
            record = record_from_job(job, query)
            if record.url and record.url not in seen_urls:
                seen_urls.add(record.url)
                result.records.append(record)

        result.found = len(result.records)
        return result
