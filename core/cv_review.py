"""LLM review of an already-drafted CV pitch/bullets (plan item 8.3).

A separate, stateless call from `core/cv_draft.py`'s drafting call - not the
same conversation "checking its own work" from memory, a fresh model
instance given only the CV, the posting, and the finished draft to grade.
Reviews whatever is currently on disk in `CV/drafts/<job_id>.md`, including
any hand edits made to it - it grades the real artifact, not a re-generated
one.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

from core.models import JobRecord

# Same tier as the drafter: catching a subtle fabrication needs the same
# judgment quality that produced the draft, not a cheaper pass.
DEFAULT_MODEL = "claude-sonnet-5"
# claude-sonnet-5 spends part of this budget on an internal "thinking" block
# before writing the reply (confirmed live in core/cv_draft.py) - sized the
# same way for the same reason.
MAX_OUTPUT_TOKENS = 4096
MAX_DESCRIPTION_CHARS = 6000

REVIEW_SECTION_MARKER = "## Ревью (агент-проверяющий)"

SYSTEM_PROMPT = (
    "You are reviewing a job-application draft (a short first-person pitch "
    "paragraph plus adapted CV bullets) that another AI wrote for a real "
    "candidate applying to a real job posting. You will be given the "
    "candidate's real CV, the job posting, and the draft to review. Grade "
    "it - do not rewrite it.\n\n"
    "The draft is a markdown file: a title/company/URL header, then a line "
    "giving the JOB POSTING's own location and work format (e.g. 'Ukraine · "
    "Remote' means the ROLE is based in Ukraine and remote-friendly - this "
    "is metadata about the vacancy, not a claim about where the candidate "
    "lives). Only the blockquoted pitch paragraph and the CV bullets below "
    "it are the candidate's own words - review those for what the candidate "
    "claims about themselves. Do not flag the posting's own location line "
    "as a candidate residency claim.\n\n"
    "Check for exactly these things:\n"
    "1. FABRICATION - does every fact in the pitch/bullets (employer, tool, "
    "skill, degree, certification, date, achievement) trace back to "
    "something actually stated in the CV? Flag anything invented or "
    "exaggerated, however small.\n"
    "2. LOCATION HONESTY - within the pitch/bullets (not the posting's own "
    "location line), does the candidate's own text ever claim or imply they "
    "physically live or are based somewhere other than the CV's stated "
    "current location? A genuine timezone-overlap fact is fine (e.g. "
    "'my time zone is close to Ukraine's' when the CV's country really is "
    "close); a residency claim ('I'm based in Ukraine', 'I'm currently in "
    "Ukraine') when the CV states a different current location is not.\n"
    "3. RELEVANCE - does the pitch/bullets actually address the posting's "
    "key requirements using real CV content, or does it ignore them?\n"
    "4. TONE - is it dry and factual (plain verbs: built, analyzed, "
    "wrote) rather than a 'success story' sales pitch (fluency, expertise, "
    "passionate, deep understanding)?\n\n"
    "Be skeptical - the candidate is relying on you to catch dishonesty "
    "before this reaches a real recruiter, not to rubber-stamp it.\n\n"
    "Respond with ONLY a JSON object, nothing else - no markdown, no code "
    "fences, no commentary before or after:\n"
    '{"verdict": "approved" | "needs_revision", "issues": ["<short, '
    'specific issue - what is wrong and where>", ...]}\n'
    "An empty issues list means approved."
)


@dataclass
class ReviewResult:
    verdict: str
    issues: list[str]


def build_review_prompt(record: JobRecord, cv_text: str, draft_markdown: str) -> str:
    posting = (
        f"Title: {record.title}\n"
        f"Company: {record.company}\n"
        f"Description:\n{record.full_text[:MAX_DESCRIPTION_CHARS]}"
    )
    return (
        f"CANDIDATE CV:\n{cv_text}\n\n---\n\n"
        f"JOB POSTING:\n{posting}\n\n---\n\n"
        f"DRAFT TO REVIEW:\n{draft_markdown}"
    )


def parse_review_response(text: str) -> ReviewResult:
    """Parse the model's JSON reply, tolerant of stray markdown code fences."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    data = json.loads(cleaned)
    verdict = str(data.get("verdict", "")).strip() or "needs_revision"
    issues = [str(item).strip() for item in data.get("issues", []) if str(item).strip()]
    return ReviewResult(verdict=verdict, issues=issues)


def generate_review(
    client, record: JobRecord, cv_text: str, draft_markdown: str, model: str = DEFAULT_MODEL
) -> ReviewResult:
    """Call the Anthropic API once and return the parsed review."""
    response = client.messages.create(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_review_prompt(record, cv_text, draft_markdown)}],
    )
    text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    try:
        return parse_review_response(text)
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        stop_reason = getattr(response, "stop_reason", "unknown")
        block_types = [getattr(block, "type", "?") for block in response.content]
        raise RuntimeError(
            f"could not parse model reply (stop_reason={stop_reason!r}, "
            f"content_block_types={block_types!r}, raw_text={text[:200]!r}): {error}"
        ) from error


def strip_existing_review(draft_markdown: str) -> str:
    """Drop a previously-appended review section, if any, before re-reviewing."""
    return draft_markdown.split(f"\n---\n\n{REVIEW_SECTION_MARKER}")[0].rstrip() + "\n"


def has_review(draft_markdown: str) -> bool:
    return REVIEW_SECTION_MARKER in draft_markdown


def extract_verdict(draft_markdown: str) -> str:
    """Read the verdict back out of an already-reviewed draft file, without
    re-running the review - used by the applications tracker (8.5) to show
    "did this pass 8.3" without a fresh API call.
    """
    if "✅ Одобрено" in draft_markdown:
        return "approved"
    if "⚠️ Нужна правка" in draft_markdown:
        return "needs_revision"
    return ""


def append_review_section(draft_markdown: str, review: ReviewResult) -> str:
    base = strip_existing_review(draft_markdown) if has_review(draft_markdown) else draft_markdown.rstrip() + "\n"
    verdict_line = "✅ Одобрено" if review.verdict == "approved" else "⚠️ Нужна правка"
    issues_block = "\n".join(f"- {issue}" for issue in review.issues) if review.issues else "- (замечаний нет)"
    reviewed_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    return (
        f"{base}\n"
        f"---\n\n"
        f"{REVIEW_SECTION_MARKER}\n\n"
        f"**Вердикт:** {verdict_line}\n\n"
        f"{issues_block}\n\n"
        f"_Проверено LLM ({reviewed_at}, plan item 8.3) — отдельным вызовом от того, кто писал черновик. "
        f"Финальное решение отправлять или нет всё равно за тобой (пункт 8.5)._\n"
    )
