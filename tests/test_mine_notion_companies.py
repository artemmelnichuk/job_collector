from __future__ import annotations

import csv
import unittest
from pathlib import Path

from playwright.async_api import async_playwright

from scripts.mine_notion_companies import (
    dedupe_rows,
    extract_all_rows,
    row_from_cells,
    write_csv,
)


class RowExtractionTests(unittest.TestCase):
    def test_row_from_cells_prefers_link_href_over_truncated_text(self) -> None:
        headers = ["Company Name", "Career page"]
        cells = [
            {"text": "1inch Network", "href": None},
            {"text": "cryptocurrencyjobs.co/sta…", "href": "https://cryptocurrencyjobs.co/startups/1inch-network/"},
        ]
        record = row_from_cells(headers, cells)
        self.assertEqual(record["Company Name"], "1inch Network")
        self.assertEqual(record["Career page"], "https://cryptocurrencyjobs.co/startups/1inch-network/")

    def test_row_from_cells_handles_missing_trailing_cells(self) -> None:
        headers = ["Company Name", "Industry", "Location"]
        cells = [{"text": "Acme", "href": None}]
        record = row_from_cells(headers, cells)
        self.assertEqual(record, {"Company Name": "Acme", "Industry": "", "Location": ""})

    def test_dedupe_rows_keeps_first_occurrence(self) -> None:
        records = [
            {"Company Name": "Acme", "Industry": "Fintech"},
            {"Company Name": "Beta", "Industry": "AI"},
            {"Company Name": "Acme", "Industry": "duplicate-should-be-dropped"},
        ]
        result = dedupe_rows(records, "Company Name")
        self.assertEqual([r["Company Name"] for r in result], ["Acme", "Beta"])
        self.assertEqual(result[0]["Industry"], "Fintech")

    def test_dedupe_rows_drops_entries_with_no_key(self) -> None:
        records = [{"Company Name": "", "Industry": "X"}, {"Company Name": "Acme", "Industry": "Y"}]
        result = dedupe_rows(records, "Company Name")
        self.assertEqual(len(result), 1)


class CsvWritingTests(unittest.TestCase):
    def test_write_csv_round_trips_headers_and_rows(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "nested" / "companies.csv"
            headers = ["Company Name", "Industry"]
            records = [{"Company Name": "Acme", "Industry": "Fintech"}]
            write_csv(out_path, headers, records)

            with out_path.open(encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
            self.assertEqual(reader.fieldnames, headers)
            self.assertEqual(rows, [{"Company Name": "Acme", "Industry": "Fintech"}])


_NOTION_LIKE_PAGE = """
<html>
<body>
  <div class="notion-table-view-header-cell">Company Name</div>
  <div class="notion-table-view-header-cell">Career page</div>
  <div id="rows">
    <div class="notion-table-view-row">
      <div data-col-index="0">Row1</div>
      <div data-col-index="1"><a href="https://example.com/row1">short1</a></div>
    </div>
    <div class="notion-table-view-row">
      <div data-col-index="0">Row2</div>
      <div data-col-index="1"><a href="https://example.com/row2">short2</a></div>
    </div>
  </div>
  <div role="button" id="load-more">Load more</div>
  <script>
    let batch = 0;
    document.getElementById('load-more').addEventListener('click', () => {
      batch += 1;
      if (batch > 1) {
        document.getElementById('load-more').remove();
        return;
      }
      const rowsContainer = document.getElementById('rows');
      for (const n of [3, 4]) {
        const row = document.createElement('div');
        row.className = 'notion-table-view-row';
        row.innerHTML =
          '<div data-col-index="0">Row' + n + '</div>' +
          '<div data-col-index="1"><a href="https://example.com/row' + n + '">short' + n + '</a></div>';
        rowsContainer.appendChild(row);
      }
    });
  </script>
</body>
</html>
"""


class ExtractAllRowsIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Drives the real "Load more" click loop against a synthetic Notion-like
    DOM, the same route-interception-free pattern used for the WTTJ pagination
    integration test - confirms the loop re-queries the button fresh each
    click (rather than relying on a stale cached reference) and stops once
    the button disappears.
    """

    async def asyncSetUp(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch()
        self._page = await self._browser.new_page()

    async def asyncTearDown(self) -> None:
        await self._browser.close()
        await self._playwright.stop()

    async def test_clicks_load_more_until_it_disappears(self) -> None:
        await self._page.set_content(_NOTION_LIKE_PAGE)
        headers, rows = await extract_all_rows(self._page, max_rows=None)
        self.assertEqual(headers, ["Company Name", "Career page"])
        self.assertEqual(len(rows), 4)

    async def test_respects_max_rows_cap(self) -> None:
        await self._page.set_content(_NOTION_LIKE_PAGE)
        headers, rows = await extract_all_rows(self._page, max_rows=3)
        self.assertEqual(len(rows), 3)


if __name__ == "__main__":
    unittest.main()
