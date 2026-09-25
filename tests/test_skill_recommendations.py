from __future__ import annotations

import unittest
from collections import Counter

from core.skill_recommendations import (
    build_recommendations,
    count_certification_mentions,
    count_market_demand,
    dedupe_rows,
    format_recommendation,
    normalize_key,
)
from core.skills_gap import SkillGapReport


def report(gap: dict[str, int], partial: dict[str, int] | None = None) -> SkillGapReport:
    r = SkillGapReport()
    for skill, n in gap.items():
        r.gap[skill] = n
        r.demand[skill] = n
    for skill, n in (partial or {}).items():
        r.partial[skill] = n
        r.demand[skill] = n
    return r


class MarketCountTests(unittest.TestCase):
    def test_counts_one_per_posting_even_if_repeated(self) -> None:
        texts = ["power bi and power bi again", "tableau only", "no tools here"]
        counts = count_market_demand(texts, ["Power BI", "Tableau"])
        self.assertEqual(counts["Power BI"], 1)
        self.assertEqual(counts["Tableau"], 1)

    def test_certification_must_be_near_the_skill(self) -> None:
        near = "tableau certification is a plus"
        far = "certification in nursing. " + "x" * 90 + " we use tableau"
        counts = count_certification_mentions([near, far, "tableau, no cert word"], ["Tableau"])
        self.assertEqual(counts["Tableau"], 1)

    def test_certification_word_in_ukrainian(self) -> None:
        counts = count_certification_mentions(["сертифікат power bi буде плюсом"], ["Power BI"])
        self.assertEqual(counts["Power BI"], 1)


class RecommendationTests(unittest.TestCase):
    def test_actions_follow_market_share_and_near_fit_count(self) -> None:
        rep = report({"Power BI": 20, "Looker": 6, "Snowflake": 5, "Spark": 1})
        market = Counter({"Power BI": 30, "Looker": 5, "Snowflake": 1, "Spark": 50})
        recs = {r.skill: r for r in build_recommendations(rep, market, Counter(), 100)}
        self.assertEqual(recs["Power BI"].action, "learn")      # 30% market share
        self.assertEqual(recs["Looker"].action, "optional")     # 5%
        self.assertEqual(recs["Snowflake"].action, "low priority")  # 1%
        self.assertEqual(recs["Spark"].action, "low priority")  # popular, but only 1 near-fit posting

    def test_certificate_advice_thresholds(self) -> None:
        rep = report({"Power BI": 5, "Tableau": 5, "Looker": 5})
        market = Counter({"Power BI": 30, "Tableau": 30, "Looker": 30})
        certs = Counter({"Power BI": 5, "Tableau": 1})
        recs = {r.skill: r for r in build_recommendations(rep, market, certs, 100)}
        self.assertIn("worth considering", recs["Power BI"].certificate_advice)
        self.assertIn("not a market signal", recs["Tableau"].certificate_advice)
        self.assertIn("skip the exam", recs["Looker"].certificate_advice)

    def test_partial_skills_included_and_sorted_by_near_fit_demand(self) -> None:
        rep = report({"Tableau": 3}, partial={"Python": 30})
        recs = build_recommendations(rep, Counter({"Tableau": 10, "Python": 40}), Counter(), 100)
        self.assertEqual([r.skill for r in recs], ["Python", "Tableau"])
        self.assertEqual(recs[0].status, "partial")
        self.assertIn("go deeper", format_recommendation(recs[0]))

    def test_low_confidence_skill_is_noted(self) -> None:
        rep = report({"R": 10})
        rec = build_recommendations(rep, Counter({"R": 40}), Counter(), 100)[0]
        self.assertIn("inflated", rec.note)
        self.assertEqual(rec.action, "verify first")  # would be "learn" on share alone

    def test_zero_market_total_does_not_divide_by_zero(self) -> None:
        rec = build_recommendations(report({"Power BI": 5}), Counter(), Counter(), 0)[0]
        self.assertEqual(rec.market_share, 0.0)
        self.assertEqual(rec.action, "low priority")


class DedupeTests(unittest.TestCase):
    def test_dedupe_by_normalized_company_and_title(self) -> None:
        rows = [
            {"company": "Acme", "title": "Data  Analyst"},
            {"company": " acme ", "title": "data analyst"},
            {"company": "Other", "title": "Data Analyst"},
        ]
        self.assertEqual(len(dedupe_rows(rows)), 2)
        self.assertEqual(normalize_key("Acme", "Data  Analyst"), "acme|data analyst")


if __name__ == "__main__":
    unittest.main()
