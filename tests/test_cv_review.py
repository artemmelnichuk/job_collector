from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from core.cv_review import (
    REVIEW_SECTION_MARKER,
    SYSTEM_PROMPT,
    ReviewResult,
    append_review_section,
    build_review_prompt,
    generate_review,
    has_review,
    parse_review_response,
    strip_existing_review,
)
from core.models import JobRecord


class ReviewPromptTests(unittest.TestCase):
    def test_build_review_prompt_includes_cv_posting_and_draft(self) -> None:
        record = JobRecord(title="Data Analyst", company="Acme", full_text="Needs SQL.")
        prompt = build_review_prompt(record, "CV TEXT", "DRAFT MARKDOWN")
        self.assertIn("CV TEXT", prompt)
        self.assertIn("Data Analyst", prompt)
        self.assertIn("Needs SQL.", prompt)
        self.assertIn("DRAFT MARKDOWN", prompt)


class SystemPromptGuardrailTests(unittest.TestCase):
    def test_prompt_clarifies_the_posting_location_line_is_not_a_candidate_claim(self) -> None:
        # Regression: the first live 16-draft review batch flagged the
        # draft's own "Ukraine · Remote"-style header (the JOB POSTING's
        # location/format, rendered by core/cv_draft.py:render_draft_markdown)
        # as a candidate residency claim in nearly every file - even ones
        # whose pitch correctly stated the candidate's actual current city. The
        # reviewer was never told that line is the posting's metadata, not
        # the candidate's own words. Guard the clarification that fixed it.
        self.assertIn("JOB POSTING's own location", SYSTEM_PROMPT)
        self.assertIn("not a claim about where the candidate lives", SYSTEM_PROMPT)


class ReviewParsingTests(unittest.TestCase):
    def test_parses_approved_with_no_issues(self) -> None:
        review = parse_review_response('{"verdict": "approved", "issues": []}')
        self.assertEqual(review.verdict, "approved")
        self.assertEqual(review.issues, [])

    def test_parses_needs_revision_with_issues(self) -> None:
        review = parse_review_response(
            '{"verdict": "needs_revision", "issues": ["Claims Power BI, not in CV", "Says based in Ukraine"]}'
        )
        self.assertEqual(review.verdict, "needs_revision")
        self.assertEqual(review.issues, ["Claims Power BI, not in CV", "Says based in Ukraine"])

    def test_parses_json_wrapped_in_code_fences(self) -> None:
        review = parse_review_response('```json\n{"verdict": "approved", "issues": []}\n```')
        self.assertEqual(review.verdict, "approved")

    def test_missing_verdict_defaults_to_needs_revision(self) -> None:
        review = parse_review_response('{"issues": []}')
        self.assertEqual(review.verdict, "needs_revision")


class GenerateReviewTests(unittest.TestCase):
    def test_generate_review_calls_the_api_and_returns_parsed_result(self) -> None:
        record = JobRecord(job_id="test_1", title="Data Analyst", company="Acme", full_text="SQL")
        fake_block = MagicMock(type="text", text='{"verdict": "approved", "issues": []}')
        fake_response = MagicMock(content=[fake_block])
        fake_client = MagicMock()
        fake_client.messages.create.return_value = fake_response

        review = generate_review(fake_client, record, "CV TEXT", "DRAFT", model="claude-sonnet-5")

        self.assertEqual(review.verdict, "approved")
        fake_client.messages.create.assert_called_once()
        call_kwargs = fake_client.messages.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "claude-sonnet-5")

    def test_generate_review_raises_a_diagnosable_error_on_empty_reply(self) -> None:
        record = JobRecord(job_id="test_2", title="X", company="Y")
        fake_response = MagicMock(content=[], stop_reason="max_tokens")
        fake_client = MagicMock()
        fake_client.messages.create.return_value = fake_response

        with self.assertRaises(RuntimeError) as ctx:
            generate_review(fake_client, record, "CV TEXT", "DRAFT")
        self.assertIn("max_tokens", str(ctx.exception))


class ReviewSectionTests(unittest.TestCase):
    def test_has_review_detects_the_marker(self) -> None:
        self.assertFalse(has_review("# Title\n\nsome content"))
        self.assertTrue(has_review(f"# Title\n\n---\n\n{REVIEW_SECTION_MARKER}\n\n**Вердикт:** ✅ Одобрено\n"))

    def test_append_review_section_adds_verdict_and_issues(self) -> None:
        draft = "# Title\n**Acme** — url\n\n> pitch\n\n## Адаптированные пункты для CV\n\n- bullet\n"
        review = ReviewResult(verdict="needs_revision", issues=["Claims Power BI, not in CV"])
        result = append_review_section(draft, review)
        self.assertIn(REVIEW_SECTION_MARKER, result)
        self.assertIn("⚠️ Нужна правка", result)
        self.assertIn("Claims Power BI, not in CV", result)
        self.assertIn("- bullet", result)  # original content preserved

    def test_append_review_section_approved_shows_no_issues_placeholder(self) -> None:
        draft = "# Title\n\n> pitch\n"
        review = ReviewResult(verdict="approved", issues=[])
        result = append_review_section(draft, review)
        self.assertIn("✅ Одобрено", result)
        self.assertIn("(замечаний нет)", result)

    def test_regenerating_replaces_rather_than_stacks_review_sections(self) -> None:
        draft = "# Title\n\n> pitch\n"
        first = append_review_section(draft, ReviewResult(verdict="needs_revision", issues=["Old issue"]))
        second = append_review_section(first, ReviewResult(verdict="approved", issues=[]))
        self.assertEqual(second.count(REVIEW_SECTION_MARKER), 1)
        self.assertNotIn("Old issue", second)
        self.assertIn("✅ Одобрено", second)

    def test_strip_existing_review_removes_only_the_review_section(self) -> None:
        draft = "# Title\n\n> pitch\n"
        reviewed = append_review_section(draft, ReviewResult(verdict="approved", issues=[]))
        stripped = strip_existing_review(reviewed)
        self.assertNotIn(REVIEW_SECTION_MARKER, stripped)
        self.assertIn("# Title", stripped)
        self.assertIn("> pitch", stripped)


if __name__ == "__main__":
    unittest.main()
