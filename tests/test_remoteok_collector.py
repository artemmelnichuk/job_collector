from __future__ import annotations

import unittest

from collectors.remoteok import format_salary, parse_jobs, record_from_job


class RemoteOkCollectorTests(unittest.TestCase):
    def test_parse_jobs_drops_leading_legal_notice_entry(self) -> None:
        payload = [
            {"legal": "API Terms of Service..."},
            {"position": "Data Analyst", "company": "Acme"},
        ]
        jobs = parse_jobs(payload)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["position"], "Data Analyst")

    def test_parse_jobs_tolerates_non_list_payload(self) -> None:
        self.assertEqual(parse_jobs({"error": "tag filtering returned nothing"}), [])
        self.assertEqual(parse_jobs(None), [])

    def test_format_salary_handles_range_and_single_value(self) -> None:
        self.assertEqual(format_salary({"salary_min": 60000, "salary_max": 80000}), "60000-80000 USD")
        self.assertEqual(format_salary({"salary_min": 60000, "salary_max": 60000}), "60000 USD")
        self.assertEqual(format_salary({}), "")

    def test_record_from_job_is_always_remote_and_carries_provenance(self) -> None:
        job = {
            "position": "Data Analyst",
            "company": "Acme",
            "location": "Lisbon, ",
            "description": "<p>Analyze data</p>",
            "url": "https://remoteok.com/remote-jobs/data-analyst-acme-123",
            "date": "2026-09-04T15:13:46+00:00",
            "salary_min": 50000,
            "salary_max": 70000,
        }
        record = record_from_job(job, {"query": "Data Analyst", "category": "data"})
        self.assertEqual(record.source, "RemoteOK")
        self.assertEqual(record.work_format, "Remote")
        self.assertEqual(record.source_work_format, "Remote")
        self.assertEqual(record.salary, "50000-70000 USD")
        self.assertEqual(record.job_category, "data")
        self.assertTrue(record.job_id.startswith("remoteok_"))


if __name__ == "__main__":
    unittest.main()
