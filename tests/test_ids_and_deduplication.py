from __future__ import annotations

import unittest

from core.deduplication import deduplicate_records
from core.ids import build_deduplication_key, build_job_id, normalize_url
from core.models import JobRecord


def make_record(**overrides: str) -> JobRecord:
    values = {
        "source": "LinkedIn",
        "title": "Trading Analyst",
        "company": "Example Exchange",
        "city_region": "Paris",
        "url": "https://example.com/jobs/123",
    }
    values.update(overrides)
    return JobRecord(**values)


class JobIdentityTests(unittest.TestCase):
    def test_tracking_parameters_do_not_change_normalized_url(self) -> None:
        first = "https://Example.com/jobs/123/?utm_source=linkedin"
        second = "https://example.com/jobs/123"

        self.assertEqual(normalize_url(first), normalize_url(second))
        self.assertEqual(build_job_id(make_record(url=first)), build_job_id(make_record(url=second)))

    def test_fallback_identity_is_stable_without_url(self) -> None:
        first = make_record(url="", company=" Example Exchange ")
        second = make_record(url="", company="example exchange")

        self.assertEqual(build_deduplication_key(first), build_deduplication_key(second))
        self.assertEqual(build_job_id(first), build_job_id(second))

    def test_source_is_part_of_identity(self) -> None:
        linkedin = make_record()
        wttj = make_record(source="Welcome to the Jungle")

        self.assertNotEqual(build_job_id(linkedin), build_job_id(wttj))


class DeduplicationTests(unittest.TestCase):
    def test_duplicate_url_is_kept_once_and_gets_job_id(self) -> None:
        records = [
            make_record(search_query="Trading Analyst"),
            make_record(search_query="Crypto Analyst", url="https://example.com/jobs/123?utm_campaign=test"),
        ]

        result = deduplicate_records(records)

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.duplicates, 1)
        self.assertTrue(result.records[0].job_id)

    def test_different_urls_are_not_duplicates(self) -> None:
        result = deduplicate_records(
            [make_record(url="https://example.com/jobs/123"), make_record(url="https://example.com/jobs/456")]
        )

        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.duplicates, 0)
        self.assertNotEqual(result.records[0].job_id, result.records[1].job_id)


if __name__ == "__main__":
    unittest.main()
