from __future__ import annotations

import unittest

from core.models import JobRecord
from scripts.fit_score import select_candidates


class SelectCandidatesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records = [
            JobRecord(job_id="a", title="Decided"),
            JobRecord(job_id="b", title="Undecided, unscored"),
            JobRecord(job_id="c", title="Undecided, already scored", fit_score="60"),
        ]
        self.manual_review = {
            "a": {"decision": "Подходит"},
            "b": {"decision": ""},
            "c": {"decision": ""},
        }

    def test_skips_decided_and_already_scored_by_default(self) -> None:
        candidates = select_candidates(self.records, self.manual_review, rescore=False)
        self.assertEqual([r.job_id for r in candidates], ["b"])

    def test_rescore_includes_already_scored_undecided_records(self) -> None:
        candidates = select_candidates(self.records, self.manual_review, rescore=True)
        self.assertEqual([r.job_id for r in candidates], ["b", "c"])

    def test_never_includes_decided_records_even_with_rescore(self) -> None:
        candidates = select_candidates(self.records, self.manual_review, rescore=True)
        self.assertNotIn("a", [r.job_id for r in candidates])


if __name__ == "__main__":
    unittest.main()
