from __future__ import annotations

import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.async_api import async_playwright

from collectors.wttj import (
    WttjCollector,
    build_search_url,
    detect_availability_status,
    infer_work_format,
    location_parts,
    normalize_saved_location,
    page_requires_auth,
    parse_json_ld,
    record_from_page,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class WttjCollectorTests(unittest.TestCase):
    def test_search_url_quotes_query(self) -> None:
        url = build_search_url("Market Data Analyst")
        self.assertIn("query=Market%20Data%20Analyst", url)

    def test_json_ld_parser_accepts_job_posting(self) -> None:
        self.assertEqual(parse_json_ld('{"@type":"JobPosting","title":"Risk Analyst"}')['title'], "Risk Analyst")

    def test_work_format_is_inferred_from_text(self) -> None:
        self.assertEqual(infer_work_format("This is a remote role"), "Remote")
        self.assertEqual(infer_work_format("Hybrid office"), "Hybrid")
        self.assertEqual(infer_work_format("Office-based"), "On-site")

    def test_authentication_paths_are_detected(self) -> None:
        self.assertTrue(page_requires_auth("https://www.welcometothejungle.com/en/authenticate/signin"))
        self.assertFalse(page_requires_auth("https://www.welcometothejungle.com/en/jobs"))

    def test_job_location_is_flattened(self) -> None:
        location, country = location_parts([
            {
                "@type": "Place",
                "address": {
                    "@type": "PostalAddress",
                    "addressLocality": "Paris",
                    "addressRegion": "Ile-de-France",
                    "addressCountry": "FR",
                },
            }
        ])
        self.assertEqual(location, "Paris, Ile-de-France, FR")
        self.assertEqual(country, "FR")

    def test_availability_status_detects_closed_job(self) -> None:
        self.assertEqual(
            detect_availability_status(
                "https://www.welcometothejungle.com/en/companies/example/jobs/test",
                "Cette offre n'est plus disponible",
            ),
            "closed",
        )

    def test_legacy_saved_location_is_normalized(self) -> None:
        location, country = normalize_saved_location(
            "[{'@type': 'Place', 'address': {'addressLocality': 'Neuilly-sur-Seine', 'addressRegion': 'Hauts-de-Seine', 'addressCountry': 'FR'}}]"
        )
        self.assertEqual(location, "Neuilly-sur-Seine, Hauts-de-Seine, FR")
        self.assertEqual(country, "FR")


class RecordFromPageIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Exercises record_from_page against a real (headless) rendered page.

    Complements the string/dict-level tests above with coverage of the
    Playwright locator/selector plumbing (first_text, json_ld_job) that
    those can't reach without a live DOM.
    """

    async def asyncSetUp(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch()
        self._page = await self._browser.new_page()

    async def asyncTearDown(self) -> None:
        await self._browser.close()
        await self._playwright.stop()

    async def test_record_from_page_uses_json_ld_when_present(self) -> None:
        html = (FIXTURES_DIR / "wttj_json_ld.html").read_text(encoding="utf-8")
        await self._page.set_content(html)
        record = await record_from_page(self._page, search_query="Quant Researcher", category="quant")
        self.assertEqual(record.title, "Quant Researcher")
        self.assertEqual(record.company, "Crypto Fund")
        self.assertEqual(record.city_region, "Paris, Ile-de-France, FR")
        self.assertEqual(record.country, "FR")
        # work_format is inferred from the *visible page body*, not the JSON-LD
        # description - the fixture states "remote" only in the rendered <p>.
        self.assertEqual(record.work_format, "Remote")
        self.assertEqual(record.salary, "60000-80000 EUR/year")
        self.assertIn("We are hiring a Quant Researcher", record.full_text)
        self.assertTrue(record.job_id)


class WttjCollectorPaginationIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Drives the real WttjCollector.collect() pagination loop end-to-end.

    Uses Playwright route interception to serve synthetic, deterministic
    "search result" and "job detail" pages instead of hitting the live site -
    this is what lets a limit-driven pagination bug (stopping too early/late,
    off-by-one on page numbers) show up in a fast, offline test.
    """

    JOBS_PER_PAGE = 2

    async def asyncSetUp(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch()
        self._context = await self._browser.new_context()
        self.requested_pages: list[int] = []
        await self._context.route("https://www.welcometothejungle.com/**", self._handle_route)

    async def asyncTearDown(self) -> None:
        await self._context.close()
        await self._browser.close()
        await self._playwright.stop()

    async def _handle_route(self, route, request) -> None:
        parsed = urlparse(request.url)
        if parsed.path == "/en/jobs":
            page_number = int(parse_qs(parsed.query).get("page", ["1"])[0])
            self.requested_pages.append(page_number)
            start = (page_number - 1) * self.JOBS_PER_PAGE + 1
            links = "".join(
                f'<a href="/en/jobs/job-{start + offset}">Job {start + offset}</a>'
                for offset in range(self.JOBS_PER_PAGE)
            )
            await route.fulfill(status=200, content_type="text/html", body=f"<html><body>{links}</body></html>")
        elif parsed.path.startswith("/en/jobs/job-"):
            job_id = parsed.path.rsplit("-", 1)[-1]
            html = (
                '<html><head><script type="application/ld+json">'
                f'{{"@type":"JobPosting","title":"Job {job_id}",'
                '"hiringOrganization":{"name":"TestCo"},"description":"Remote role"}'
                "</script></head><body></body></html>"
            )
            await route.fulfill(status=200, content_type="text/html", body=html)
        else:
            await route.fulfill(status=404, body="not found")

    async def test_pagination_stops_once_the_limit_is_reached(self) -> None:
        collector = WttjCollector(settings={
            "request": {"timeout_seconds": 5, "delay_min_seconds": 0},
            "browser": {"manual_login_timeout_seconds": 5},
            "sources": {"wttj": {"max_pages": 5}},
        })
        result = await collector.collect(
            self._context,
            queries=[{"query": "Quant Researcher", "category": "quant"}],
            limit=4,
        )
        self.assertEqual(len(result.records), 4)
        self.assertEqual(result.found, 4)
        self.assertEqual({record.title for record in result.records}, {"Job 1", "Job 2", "Job 3", "Job 4"})
        # 2 jobs/page and a limit of 4 means only pages 1-2 should ever be
        # requested - page 3 being fetched would mean the limit check isn't
        # actually stopping the loop.
        self.assertEqual(self.requested_pages, [1, 2])

    async def test_pagination_walks_multiple_pages_when_limit_allows(self) -> None:
        collector = WttjCollector(settings={
            "request": {"timeout_seconds": 5, "delay_min_seconds": 0},
            "browser": {"manual_login_timeout_seconds": 5},
            "sources": {"wttj": {"max_pages": 5}},
        })
        result = await collector.collect(
            self._context,
            queries=[{"query": "Quant Researcher", "category": "quant"}],
            limit=6,
        )
        self.assertEqual(len(result.records), 6)
        self.assertEqual(self.requested_pages, [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
