from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from core.fit_score import (
    build_fit_score_prompt,
    parse_fit_score_response,
    score_record,
)
from core.models import JobRecord


class FitScorePromptTests(unittest.TestCase):
    def test_build_fit_score_prompt_includes_cv_and_posting_fields(self) -> None:
        record = JobRecord(
            title="Data Analyst",
            company="Acme",
            city_region="Remote",
            country="",
            work_format="Remote",
            seniority="Mid-level",
            full_text="Looking for a SQL-savvy analyst.",
        )
        prompt = build_fit_score_prompt(record, "CV TEXT HERE")
        self.assertIn("CV TEXT HERE", prompt)
        self.assertIn("Data Analyst", prompt)
        self.assertIn("Acme", prompt)
        self.assertIn("SQL-savvy analyst", prompt)

    def test_build_fit_score_prompt_truncates_long_descriptions(self) -> None:
        record = JobRecord(title="X", full_text="A" * 10000)
        prompt = build_fit_score_prompt(record, "cv")
        self.assertLess(len(prompt), 7000)


class FitScoreParsingTests(unittest.TestCase):
    def test_parses_plain_json(self) -> None:
        score, reasoning = parse_fit_score_response('{"fit_score": 72, "fit_reasoning": "Хорошее совпадение"}')
        self.assertEqual(score, 72)
        self.assertEqual(reasoning, "Хорошее совпадение")

    def test_parses_json_wrapped_in_code_fences(self) -> None:
        score, reasoning = parse_fit_score_response('```json\n{"fit_score": 40, "fit_reasoning": "Мало опыта"}\n```')
        self.assertEqual(score, 40)
        self.assertEqual(reasoning, "Мало опыта")

    def test_clamps_out_of_range_scores(self) -> None:
        score, _ = parse_fit_score_response('{"fit_score": 150, "fit_reasoning": ""}')
        self.assertEqual(score, 100)
        score, _ = parse_fit_score_response('{"fit_score": -10, "fit_reasoning": ""}')
        self.assertEqual(score, 0)


class ScoreRecordTests(unittest.TestCase):
    def test_score_record_calls_the_api_and_fills_fit_fields(self) -> None:
        record = JobRecord(job_id="test_1", title="Data Analyst", company="Acme", full_text="SQL, Python")
        fake_block = MagicMock(type="text", text='{"fit_score": 85, "fit_reasoning": "Сильное совпадение по навыкам"}')
        fake_response = MagicMock(content=[fake_block])
        fake_client = MagicMock()
        fake_client.messages.create.return_value = fake_response

        updated = score_record(fake_client, record, "CV TEXT", model="claude-haiku-4-5-20251001")

        self.assertEqual(updated.fit_score, "85")
        self.assertEqual(updated.fit_reasoning, "Сильное совпадение по навыкам")
        self.assertEqual(updated.job_id, "test_1")
        fake_client.messages.create.assert_called_once()
        call_kwargs = fake_client.messages.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "claude-haiku-4-5-20251001")
        self.assertIn("CV TEXT", call_kwargs["messages"][0]["content"])


if __name__ == "__main__":
    unittest.main()
