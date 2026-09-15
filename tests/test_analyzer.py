from __future__ import annotations

import unittest

from core.analyzer import analyze_record, classify_role, classify_seniority, extract_skills
from core.models import JobRecord


class AnalyzerTests(unittest.TestCase):
    def make_record(self, title: str, text: str) -> JobRecord:
        return JobRecord(title=title, full_text=text)

    def test_classifies_risk_role_and_seniority(self) -> None:
        record = self.make_record(
            "Senior Risk Analyst",
            "5+ years of experience. Required: SQL and Python. Nice to have: Power BI.",
        )
        self.assertEqual(classify_role(record)[0], "Risk Analytics")
        self.assertEqual(classify_seniority(record)[0], "Senior")

    def test_classifies_risk_variants(self) -> None:
        for title in ("Risk Control Analyst", "Risk Manager", "Operational Risk Analyst"):
            self.assertEqual(classify_role(self.make_record(title, ""))[0], "Risk Analytics")

    def test_classifies_french_data_and_confirmed_roles(self) -> None:
        data_record = self.make_record("Analyste de donnees", "")
        confirmed_record = self.make_record("Data Analyst confirmé", "")
        self.assertEqual(classify_role(data_record)[0], "Data Analytics")
        self.assertEqual(classify_seniority(confirmed_record)[0], "Mid-level")

    def test_extracts_normalized_skills(self) -> None:
        record = self.make_record("Product Analyst", "Use SQL, Python, Power BI and A/B testing.")
        self.assertEqual(extract_skills(record), ["SQL", "Python", "Power BI", "A/B testing"])

    def test_splits_required_and_preferred_skills(self) -> None:
        analyzed = analyze_record(
            self.make_record("Data Analyst", "Required: SQL and Python. Nice to have: Tableau.")
        )
        self.assertEqual(analyzed.required_skills, "SQL; Python")
        self.assertEqual(analyzed.preferred_skills, "Tableau")

    def test_classifies_ukrainian_and_russian_role_titles(self) -> None:
        # Real phrasing from collected Djinni.co postings (2026-09-06).
        self.assertEqual(classify_role(self.make_record("", "Шукаємо бізнес-аналітика в команду"))[0], "Business Analytics")
        self.assertEqual(classify_role(self.make_record("", "Вакансія: аналітик даних для e-commerce"))[0], "Data Analytics")
        self.assertEqual(classify_role(self.make_record("", "Потрібен ризик-аналітик у фінтех"))[0], "Risk Analytics")

    def test_classifies_ukrainian_seniority_and_years(self) -> None:
        record = self.make_record("Product Analyst", "Досвід в Product-аналітиці від 3х років")
        seniority, minimum, maximum = classify_seniority(record)
        self.assertEqual(minimum, "3")
        self.assertEqual(seniority, "Mid-level")
        self.assertEqual(classify_seniority(self.make_record("", "Шукаємо джуніора в команду"))[0], "Junior")
        self.assertEqual(classify_seniority(self.make_record("", "Потрібен старший аналітик"))[0], "Senior")

    def test_splits_required_and_preferred_with_ukrainian_markers(self) -> None:
        analyzed = analyze_record(
            self.make_record("Data Analyst", "Обов'язково: SQL та Excel. Буде перевагою: Power BI.")
        )
        self.assertEqual(analyzed.required_skills, "SQL; Excel")
        self.assertEqual(analyzed.preferred_skills, "Power BI")

    def test_skill_mentioned_before_and_after_marker_stays_required(self) -> None:
        # Regression: a skill required up front and mentioned again in a
        # closing "nice to have: more X" summary used to be bucketed as
        # preferred-only, since only the post-marker text was checked.
        analyzed = analyze_record(
            self.make_record(
                "Data Analyst",
                "Required: SQL and Python. Nice to have: further Python/ML experience is a bonus.",
            )
        )
        self.assertEqual(analyzed.required_skills, "SQL; Python")
        self.assertEqual(analyzed.preferred_skills, "Machine Learning")

    def test_analyze_record_fills_city_region_and_salary_usd_equivalent(self) -> None:
        analyzed = analyze_record(
            JobRecord(
                title="Data Analyst",
                city_region="Paris, Ile-de-France, FR",
                country="FR",
                salary="80000-95000 EUR/year",
            )
        )
        self.assertEqual(analyzed.city, "Paris")
        self.assertEqual(analyzed.region, "Ile-de-France")
        self.assertEqual(analyzed.salary_usd_equivalent, "≈86,400-102,600 USD")


if __name__ == "__main__":
    unittest.main()
