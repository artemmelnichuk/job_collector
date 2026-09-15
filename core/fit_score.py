"""LLM-based fit scoring: JobRecord + master CV -> fit_score (0-100) + reasoning.

Complements `core/analyzer.py`'s rule-based classification, doesn't replace
it - both fields live side by side in `jobs_master`. Deliberately not part
of the free collect/analyze pass: each call is a real, billed Anthropic API
request, so it only runs from the explicitly-invoked `scripts/fit_score.py`,
never automatically.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

from bs4 import BeautifulSoup

from core.models import JobRecord

# A cheap, fast model is deliberate here: batch-scoring dozens of postings a
# run costs real money and doesn't need deep reasoning, just a consistent,
# honest read of "does this match the candidate's real background". Revisit
# if this evolves into full CV-drafting (plan item 8.2), which would
# reasonably want a stronger model.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MAX_OUTPUT_TOKENS = 300
MAX_DESCRIPTION_CHARS = 6000

SYSTEM_PROMPT = (
    "You are a blunt, honest job-fit evaluator helping a real candidate in a "
    "real job search. You are given the candidate's CV and one job posting. "
    "Score how well the candidate's ACTUAL background matches the posting's "
    "ACTUAL requirements - not how the candidate could spin it, and not how "
    "the posting could be read generously. Be skeptical of inflating the "
    "score: a plausible-sounding title is not a fit if the required years of "
    "experience, tech depth, language, or location don't hold up.\n\n"
    "Respond with ONLY a JSON object, nothing else - no markdown, no code "
    "fences, no commentary before or after:\n"
    '{"fit_score": <integer 0-100>, "fit_reasoning": "<one or two sentences, '
    'in Russian, naming the single biggest reason for the score>"}'
)


def load_master_cv_text(path: Path) -> str:
    """Plain-text extraction of the master CV (an HTML file) for prompting."""
    html = Path(path).read_text(encoding="utf-8")
    return BeautifulSoup(html, "html.parser").get_text("\n", strip=True)


def build_fit_score_prompt(record: JobRecord, cv_text: str) -> str:
    posting = (
        f"Title: {record.title}\n"
        f"Company: {record.company}\n"
        f"Location: {record.city_region} ({record.country})\n"
        f"Work format: {record.work_format}\n"
        f"Seniority (rule-based guess, may be wrong): {record.seniority}\n"
        f"Description:\n{record.full_text[:MAX_DESCRIPTION_CHARS]}"
    )
    return f"CANDIDATE CV:\n{cv_text}\n\n---\n\nJOB POSTING:\n{posting}"


def parse_fit_score_response(text: str) -> tuple[int, str]:
    """Parse the model's JSON reply, tolerant of stray markdown code fences."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    data = json.loads(cleaned)
    score = max(0, min(100, int(data["fit_score"])))
    reasoning = str(data.get("fit_reasoning", "")).strip()
    return score, reasoning


def score_record(client, record: JobRecord, cv_text: str, model: str = DEFAULT_MODEL) -> JobRecord:
    """Call the Anthropic API once and return the record with fit fields filled in."""
    response = client.messages.create(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_fit_score_prompt(record, cv_text)}],
    )
    text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    score, reasoning = parse_fit_score_response(text)
    return replace(record, fit_score=str(score), fit_reasoning=reasoning)
