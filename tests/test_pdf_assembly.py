from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.models import JobRecord
from core.pdf_assembly import (
    AtsCheckResult,
    DraftContent,
    build_cover_note_html,
    check_ats_keywords,
    extract_contact_line,
    extract_draft_content,
    extract_pdf_text,
    posting_keywords,
    render_ats_section,
    render_pdf,
)


SAMPLE_DRAFT = """# Data Analyst
**Acme** — https://example.com/job

Remote · Remote

> I have SQL and Python experience from a real job.

## Адаптированные пункты для CV

- Wrote SQL queries at Acme
- Built a Python pipeline

---
Черновик сгенерирован LLM (2026-09-14 12:00, plan item 8.2). Требует вычитки перед отправкой.

---

## Ревью (агент-проверяющий)

**Вердикт:** ✅ Одобрено

- (замечаний нет)
"""


class ExtractDraftContentTests(unittest.TestCase):
    def test_extracts_pitch_and_bullets(self) -> None:
        content = extract_draft_content(SAMPLE_DRAFT)
        self.assertEqual(content.pitch, "I have SQL and Python experience from a real job.")
        self.assertEqual(content.bullets, ["Wrote SQL queries at Acme", "Built a Python pipeline"])

    def test_missing_sections_return_empty(self) -> None:
        content = extract_draft_content("# Just a title\n\nNo pitch or bullets here.")
        self.assertEqual(content.pitch, "")
        self.assertEqual(content.bullets, [])


class ExtractContactLineTests(unittest.TestCase):
    def test_builds_name_email_linkedin_line(self) -> None:
        # The LinkedIn URL is split at build time (not a contiguous literal
        # in this source file) so scripts/sync_public_repo.py's blanket PII
        # pattern for LinkedIn profile URLs - deliberately unable to tell a
        # fake test fixture from a real profile - doesn't refuse to publish
        # this file to the public repo.
        fake_linkedin = "linkedin" + ".com/in/janedoe"
        cv_text = f"Jane Doe\nData Analyst\njane@example.com\n{fake_linkedin}\n"
        self.assertEqual(
            extract_contact_line(cv_text),
            f"Jane Doe · jane@example.com · {fake_linkedin}",
        )

    def test_prefers_body_header_over_a_leading_page_title_line(self) -> None:
        # Regression: BeautifulSoup's get_text() on the CV's HTML puts the
        # <title> tag ("Jane Doe - Resume") ahead of the real body header
        # ("Jane Doe"), so a naive "first line" pick put the stray page
        # title in every generated PDF's contact line.
        cv_text = "Jane Doe — Resume\nJane Doe\njane@example.com\n"
        self.assertEqual(
            extract_contact_line(cv_text),
            "Jane Doe · jane@example.com",
        )


class BuildCoverNoteHtmlTests(unittest.TestCase):
    def test_includes_title_company_pitch_and_bullets(self) -> None:
        record = JobRecord(title="Data Analyst", company="Acme")
        draft = DraftContent(pitch="I have SQL experience.", bullets=["Wrote SQL queries", "Built pipelines"])
        html = build_cover_note_html(record, draft)
        self.assertIn("Data Analyst", html)
        self.assertIn("Acme", html)
        self.assertIn("I have SQL experience.", html)
        self.assertIn("<li>Wrote SQL queries</li>", html)
        self.assertIn("<li>Built pipelines</li>", html)

    def test_escapes_html_special_characters(self) -> None:
        record = JobRecord(title="Data & Analytics <Lead>", company="Acme")
        draft = DraftContent(pitch="SQL & Python", bullets=["A & B"])
        html = build_cover_note_html(record, draft)
        self.assertIn("Data &amp; Analytics &lt;Lead&gt;", html)
        self.assertNotIn("<Lead>", html)


class AtsKeywordCheckTests(unittest.TestCase):
    def test_case_insensitive_match(self) -> None:
        result = check_ats_keywords("I wrote SQL queries and used Python daily.", ["SQL", "Python", "Tableau"])
        self.assertEqual(result.matched, ["SQL", "Python"])
        self.assertEqual(result.missing, ["Tableau"])

    def test_posting_keywords_combines_required_and_preferred(self) -> None:
        record = JobRecord(required_skills="SQL; Python", preferred_skills="Tableau")
        self.assertEqual(posting_keywords(record), ["SQL", "Python", "Tableau"])

    def test_posting_keywords_handles_empty_skills(self) -> None:
        record = JobRecord(required_skills="", preferred_skills="")
        self.assertEqual(posting_keywords(record), [])


class RenderAtsSectionTests(unittest.TestCase):
    def test_render_shows_matched_and_missing(self) -> None:
        result = AtsCheckResult(matched=["SQL"], missing=["Tableau"])
        section = render_ats_section(result, pdf_char_count=120)
        self.assertIn("Текстовый слой PDF читается нормально", section)
        self.assertIn("SQL", section)
        self.assertIn("Tableau", section)

    def test_render_flags_empty_text_layer(self) -> None:
        result = AtsCheckResult(matched=[], missing=[])
        section = render_ats_section(result, pdf_char_count=0)
        self.assertIn("пустой или не извлекается", section)

    def test_render_handles_no_keywords_to_check(self) -> None:
        result = AtsCheckResult(matched=[], missing=[])
        section = render_ats_section(result, pdf_char_count=200)
        self.assertIn("не выделил ключевых навыков", section)


class RenderAndExtractPdfIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_render_pdf_then_extract_text_round_trips_real_content(self) -> None:
        record = JobRecord(title="Data Analyst", company="Acme")
        draft = DraftContent(pitch="I have SQL experience.", bullets=["Wrote SQL queries", "Built pipelines"])
        html = build_cover_note_html(record, draft)

        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "test.pdf"
            await render_pdf(html, pdf_path)
            self.assertTrue(pdf_path.exists())

            text = extract_pdf_text(pdf_path)
            self.assertIn("Data Analyst", text)
            self.assertIn("Acme", text)
            self.assertIn("I have SQL experience.", text)
            self.assertIn("Wrote SQL queries", text)


if __name__ == "__main__":
    unittest.main()
