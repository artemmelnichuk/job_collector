from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.models import JobRecord
from scripts.cv_draft import draft_path, select_candidates


class SelectCandidatesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.tmp_dir.name)
        self.records = [
            JobRecord(job_id="a", title="Not decided Подходит", availability_status="active"),
            JobRecord(job_id="b", title="Подходит + active, no draft yet", availability_status="active"),
            JobRecord(job_id="c", title="Подходит + active, already drafted", availability_status="active"),
            JobRecord(job_id="d", title="Подходит but closed", availability_status="closed"),
            JobRecord(job_id="e", title="Возможно + active", availability_status="active"),
        ]
        self.manual_review = {
            "a": {"decision": "Возможно"},
            "b": {"decision": "Подходит"},
            "c": {"decision": "Подходит"},
            "d": {"decision": "Подходит"},
            "e": {"decision": "Возможно"},
        }
        draft_path(self.output_dir, "c").write_text("existing draft", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_only_подходит_and_active_and_undrafted_by_default(self) -> None:
        candidates = select_candidates(self.records, self.manual_review, self.output_dir, regenerate=False)
        self.assertEqual([r.job_id for r in candidates], ["b"])

    def test_regenerate_includes_already_drafted_postings(self) -> None:
        candidates = select_candidates(self.records, self.manual_review, self.output_dir, regenerate=True)
        self.assertEqual([r.job_id for r in candidates], ["b", "c"])

    def test_excludes_closed_postings_even_with_regenerate(self) -> None:
        candidates = select_candidates(self.records, self.manual_review, self.output_dir, regenerate=True)
        self.assertNotIn("d", [r.job_id for r in candidates])

    def test_excludes_non_подходит_decisions(self) -> None:
        candidates = select_candidates(self.records, self.manual_review, self.output_dir, regenerate=True)
        self.assertNotIn("a", [r.job_id for r in candidates])
        self.assertNotIn("e", [r.job_id for r in candidates])


if __name__ == "__main__":
    unittest.main()
