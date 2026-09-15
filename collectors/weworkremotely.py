"""We Work Remotely collector — remote-only job board, via its public RSS feed.

Plain HTTP GET + XML parse, no browser rendering needed — same reliability
tier as djinni.py/remoteok.py. The site's old per-category RSS URLs
(``/categories/remote-...-jobs.rss``) 301-redirect to the homepage and no
longer work (confirmed 2026-09-09, presumably a site redesign) — only the
single unfiltered firehose at ``/remote-jobs.rss`` is live, and it has no
"Data"/"Analytics" category of its own (categories are broad buckets like
"Product", "Management and Finance", "All Other Remote"). So, like
remoteok.py, this collector fetches the unfiltered feed once and filters
locally by title via ``query_matches``.

Unlike Djinni/RemoteOK, the feed is well-structured: ``<region>``/
``<country>``/``<state>`` are separate fields (no location-string parsing
needed), and the title itself is ``"{Company}: {Job Title}"`` — company name
is a clean split on the first ": ", not a fragile HTML heuristic.

Every posting on We Work Remotely is remote by the site's own definition,
so work_format is set directly rather than inferred from text.

Same caveat as remoteok.py: the feed is only ~90-100 of the most-recently-
posted jobs platform-wide (not a paginated archive), skewed toward eng/
sales/management roles — a single run spot-checked 2026-09-09 found zero
analyst-titled matches among 90 items. Expect this source to contribute
sporadically, accumulating across repeated runs as the feed rotates, not a
reliable per-run yield.
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext

from collectors.base import BaseCollector, CollectorResult, get_with_retry, setting
from core.ids import build_job_id
from core.metadata import extract_salary, query_matches
from core.models import JobRecord


WWR_RSS_URL = "https://weworkremotely.com/remote-jobs.rss"


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text("\n", strip=True)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_rss_items(xml_text: str) -> list[dict[str, str]]:
    """Parse a We Work Remotely RSS document into plain dicts, tolerating malformed XML."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    items = []
    for item in root.iter("item"):
        items.append({
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "description": item.findtext("description") or "",
            "pub_date": (item.findtext("pubDate") or "").strip(),
            "region": (item.findtext("region") or "").strip(),
            "country": (item.findtext("country") or "").strip(),
            "category": (item.findtext("category") or "").strip(),
            "type": (item.findtext("type") or "").strip(),
        })
    return items


def split_company_title(raw_title: str) -> tuple[str, str]:
    """Split "{Company}: {Job Title}" — the feed's own title format.

    Falls back to an empty company and the raw title unchanged if there's no
    ": " separator (rare, but not guaranteed by the feed).
    """
    company, separator, title = raw_title.partition(": ")
    if not separator:
        return "", raw_title.strip()
    return company.strip(), title.strip()


def record_from_item(item: dict[str, str], query: dict[str, str]) -> JobRecord:
    company, title = split_company_title(clean_text(item["title"]))
    description_text = clean_text(item["description"])
    location = item["region"] or item["country"]
    record = JobRecord(
        source="We Work Remotely",
        date_collected=datetime.now().astimezone().isoformat(timespec="seconds"),
        date_published=item["pub_date"],
        title=title,
        company=company,
        city_region=location,
        country=item["country"],
        work_format="Remote",
        source_work_format="Remote",
        contract_type=item["type"],
        salary=extract_salary({}, description_text),
        url=item["link"],
        full_text=description_text,
        status="collected",
        availability_status="active",
        note="Source: We Work Remotely public RSS feed",
        search_query=query["query"],
        job_category=query["category"],
    )
    record.job_id = build_job_id(record)
    return record


class WeWorkRemotelyCollector(BaseCollector):
    """Collect matching postings from We Work Remotely's public, unfiltered feed."""

    source_name = "We Work Remotely"

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
                context, WWR_RSS_URL, timeout_ms=timeout_ms, retry_attempts=retry_attempts,
                delay_min_seconds=delay_min, delay_max_seconds=delay_max,
            )
            xml_text = await response.text()
        except Exception as error:
            result.errors += 1
            result.error_messages.append(f"We Work Remotely feed: {error}")
            return result

        for item in parse_rss_items(xml_text):
            if len(result.records) >= limit:
                break
            if not item["link"] or item["link"] in seen_urls:
                continue
            _, title = split_company_title(clean_text(item["title"]))
            query = next((candidate for candidate in queries if query_matches(candidate["query"], title)), None)
            if query is None:
                continue
            seen_urls.add(item["link"])
            result.records.append(record_from_item(item, query))

        result.found = len(result.records)
        return result
