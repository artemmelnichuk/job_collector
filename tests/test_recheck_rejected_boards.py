from __future__ import annotations

import unittest

from scripts.recheck_rejected_boards import RecheckResult, format_report


class RecheckRejectedBoardsTests(unittest.TestCase):
    def test_reports_newly_open_boards_first(self) -> None:
        results = [
            RecheckResult("Kraken", "lever", "kraken", "0 jobs before", "ok", job_count=3),
            RecheckResult("Prodly", "greenhouse", "prodlyjobs", "0 jobs before", "ok", job_count=0),
        ]
        report = format_report(results)
        self.assertIn("Now posting (worth reviewing", report)
        self.assertIn("Kraken (lever/kraken): 3 job(s)", report)
        self.assertIn("Still zero jobs, no change:", report)
        self.assertIn("Prodly (greenhouse/prodlyjobs)", report)

    def test_reports_no_newly_open_boards(self) -> None:
        results = [RecheckResult("Prodly", "greenhouse", "prodlyjobs", "0 jobs before", "ok", job_count=0)]
        report = format_report(results)
        self.assertIn("Now posting: none", report)

    def test_reports_failed_checks_separately(self) -> None:
        results = [RecheckResult("Kraken", "lever", "kraken", "0 jobs before", "http_error", detail="HTTP 404")]
        report = format_report(results)
        self.assertIn("Could not check", report)
        self.assertIn("HTTP 404", report)


if __name__ == "__main__":
    unittest.main()
