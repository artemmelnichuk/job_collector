from __future__ import annotations

import re
import unittest

import pandas as pd

from scripts.certification_analysis import (
    ALL_TERMS,
    classify_context,
    dedupe_postings,
    level_bucket,
    location_bucket,
    normalize_key,
)


def hits(term_name: str, text: str) -> bool:
    term = next(t for t in ALL_TERMS if t.name == term_name)
    return bool(re.search(term.pattern, text, term.flags))


class TermPatternTests(unittest.TestCase):
    def test_excel_verb_is_not_the_tool(self) -> None:
        self.assertFalse(hits("Excel", "You will excel in a fast-paced team and want to excel at reporting"))
        self.assertFalse(hits("Excel", "A candidate who wants to excel."))
        self.assertTrue(hits("Excel", "Advanced Excel, SQL and Python"))
        self.assertTrue(hits("Excel", "Microsoft Excel (pivot tables)"))

    def test_nosql_is_not_sql_but_postgres_is(self) -> None:
        self.assertFalse(hits("SQL", "experience with NoSQL stores"))
        self.assertTrue(hits("SQL", "strong T-SQL skills"))
        self.assertTrue(hits("SQL", "PostgreSQL"))

    def test_dune_only_counts_capitalized_or_analytics(self) -> None:
        self.assertFalse(hits("Dune", "a sand dune landscape"))
        self.assertTrue(hits("Dune", "on-chain queries in Dune"))
        self.assertTrue(hits("Dune", "dune analytics dashboards"))

    def test_certificates(self) -> None:
        self.assertTrue(hits("PL-300 / Power BI Data Analyst Associate / Microsoft Certified", "PL-300 preferred"))
        self.assertTrue(hits("Google Analytics / GA4 certification", "GA4 certification is a plus"))
        self.assertTrue(hits("certification near a tool name", "Tableau certification desirable"))
        self.assertTrue(hits("certification near a tool name", "сертифікат Power BI"))
        far = "Certification in nursing. " + "x" * 80 + " we use SQL"
        self.assertFalse(hits("certification near a tool name", far))
        self.assertFalse(hits("certification near a tool name", "Certification in nursing.\nWe use SQL"))


class ContextTests(unittest.TestCase):
    def test_nearest_marker_wins(self) -> None:
        text = "Must have SQL and Python. Nice to have PL-300."
        start = text.index("PL-300")
        self.assertEqual(classify_context(text, start, start + 6), "preferred")

    def test_no_marker_is_mentioned(self) -> None:
        self.assertEqual(classify_context("We use PL-300 daily", 7, 13), "mentioned")


class BucketAndDedupeTests(unittest.TestCase):
    def test_levels_and_locations(self) -> None:
        self.assertEqual(level_bucket("Lead"), "senior")
        self.assertEqual(level_bucket("Mid-level"), "middle")
        self.assertEqual(level_bucket("Unknown"), "unknown")
        self.assertEqual(location_bucket("Remote", "United States"), "remote")
        self.assertEqual(location_bucket("Hybrid", "Ukraine"), "europe")
        self.assertEqual(location_bucket("On-site", ""), "other")

    def test_dedupe_by_normalized_company_and_title(self) -> None:
        frame = pd.DataFrame({
            "company": ["Acme", " acme ", "Other"],
            "title": ["Data  Analyst", "data analyst", "Data Analyst"],
        })
        self.assertEqual(len(dedupe_postings(frame)), 2)
        self.assertEqual(normalize_key("Acme", "Data  Analyst"), "acme|data analyst")


if __name__ == "__main__":
    unittest.main()
