from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from core.applications import DraftFile, build_applications_rows, scan_draft_files
from core.cv_review import extract_verdict
from core.models import JobRecord


class ExtractVerdictTests(unittest.TestCase):
    def test_extracts_approved(self) -> None:
        self.assertEqual(extract_verdict("...\n**Вердикт:** ✅ Одобрено\n..."), "approved")

    def test_extracts_needs_revision(self) -> None:
        self.assertEqual(extract_verdict("...\n**Вердикт:** ⚠️ Нужна правка\n..."), "needs_revision")

    def test_no_verdict_present_returns_empty(self) -> None:
        self.assertEqual(extract_verdict("# Just a draft, never reviewed"), "")


class ScanDraftFilesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp_dir.name)

        (self.dir / "reviewed_with_pdf.md").write_text(
            "# Title\n\n> pitch\n\n---\n\n## Ревью (агент-проверяющий)\n\n**Вердикт:** ✅ Одобрено\n",
            encoding="utf-8",
        )
        (self.dir / "reviewed_with_pdf.pdf").write_bytes(b"%PDF-1.4 fake")

        (self.dir / "not_reviewed_no_pdf.md").write_text("# Title\n\n> pitch\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_missing_directory_returns_empty(self) -> None:
        self.assertEqual(scan_draft_files(self.dir / "nope"), [])

    def test_reads_verdict_and_pdf_presence(self) -> None:
        drafts = {draft.job_id: draft for draft in scan_draft_files(self.dir)}
        self.assertEqual(drafts["reviewed_with_pdf"].review_verdict, "approved")
        self.assertTrue(drafts["reviewed_with_pdf"].pdf_ready)
        self.assertEqual(drafts["not_reviewed_no_pdf"].review_verdict, "")
        self.assertFalse(drafts["not_reviewed_no_pdf"].pdf_ready)


class BuildApplicationsRowsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records_by_id = {
            "job_a": JobRecord(job_id="job_a", title="Data Analyst", company="Acme", url="https://example.com/a"),
        }
        self.drafts = [DraftFile(job_id="job_a", review_verdict="approved", pdf_ready=True)]

    def test_new_posting_defaults_to_draft_status_and_todays_date(self) -> None:
        rows = build_applications_rows(self.drafts, self.records_by_id, existing={}, today=date(2026, 9, 15))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["job_id"], "job_a")
        self.assertEqual(row["title"], "Data Analyst")
        self.assertEqual(row["company"], "Acme")
        self.assertEqual(row["review_verdict"], "approved")
        self.assertEqual(row["pdf_ready"], "Да")
        self.assertEqual(row["status"], "draft")
        self.assertEqual(row["date_added"], "2026-09-15")

    def test_existing_status_and_notes_are_preserved_across_reruns(self) -> None:
        existing = {"job_a": {"status": "approved", "notes": "sending Monday", "date_added": "2026-09-10"}}
        rows = build_applications_rows(self.drafts, self.records_by_id, existing, today=date(2026, 9, 15))
        row = rows[0]
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["notes"], "sending Monday")
        self.assertEqual(row["date_added"], "2026-09-10")  # not overwritten to today

    def test_derived_fields_still_refresh_even_when_status_is_preserved(self) -> None:
        # review_verdict/pdf_ready reflect the CURRENT file state, not
        # whatever was true the first time this job_id was tracked.
        existing = {"job_a": {"status": "rejected", "notes": "", "date_added": "2026-09-01"}}
        drafts = [DraftFile(job_id="job_a", review_verdict="needs_revision", pdf_ready=False)]
        rows = build_applications_rows(drafts, self.records_by_id, existing, today=date(2026, 9, 15))
        self.assertEqual(rows[0]["review_verdict"], "needs_revision")
        self.assertEqual(rows[0]["pdf_ready"], "Нет")
        self.assertEqual(rows[0]["status"], "rejected")

    def test_missing_record_leaves_title_company_url_blank(self) -> None:
        drafts = [DraftFile(job_id="ghost_job", review_verdict="", pdf_ready=False)]
        rows = build_applications_rows(drafts, records_by_id={}, existing={}, today=date(2026, 9, 15))
        self.assertEqual(rows[0]["title"], "")
        self.assertEqual(rows[0]["company"], "")


if __name__ == "__main__":
    unittest.main()
