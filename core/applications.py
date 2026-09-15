"""Application status tracker (plan item 8.5).

Turns the per-posting drafts already sitting in `CV/drafts/*.md` (8.2's
pitch/bullets, 8.3's review verdict, 8.4's assembled PDF) into one tracking
sheet keyed by `job_id`. This is the actual gate the roadmap called for:
every posting starts life here as `draft`, and nothing in this pipeline
ever sends anything - a human moves a row to `approved` and, only after
actually sending it themselves outside this tool, to `sent`. No LLM call,
no network access; this only reads local files and the processed dataset.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from core.cv_review import extract_verdict, has_review
from core.models import JobRecord

APPLICATIONS_COLUMNS = (
    "job_id",
    "title",
    "company",
    "url",
    "review_verdict",
    "pdf_ready",
    "status",
    "notes",
    "date_added",
)

# Preserved across reruns, same convention as manual_review's
# MANUAL_INPUT_COLUMNS - a human fills these in, a rerun must never
# overwrite them with a freshly-derived value.
APPLICATIONS_INPUT_COLUMNS = ("status", "notes")

DEFAULT_STATUS = "draft"
STATUS_OPTIONS = ("draft", "approved", "rejected", "sent")


@dataclass
class DraftFile:
    job_id: str
    review_verdict: str
    pdf_ready: bool


def scan_draft_files(drafts_dir: Path) -> list[DraftFile]:
    """Read every draft's review verdict and PDF-readiness off disk."""
    if not drafts_dir.exists():
        return []
    results = []
    for path in sorted(drafts_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        verdict = extract_verdict(text) if has_review(text) else ""
        pdf_ready = path.with_suffix(".pdf").exists()
        results.append(DraftFile(job_id=path.stem, review_verdict=verdict, pdf_ready=pdf_ready))
    return results


def build_applications_rows(
    drafts: list[DraftFile],
    records_by_id: dict[str, JobRecord],
    existing: dict[str, dict[str, str]],
    today: date | None = None,
) -> list[dict[str, str]]:
    """Build the applications sheet's rows: derived fields refreshed every
    run, but `status`/`notes` (and the original `date_added`) preserved from
    `existing` for any job_id already tracked - a rerun must never quietly
    reset a human's approval decision back to "draft".
    """
    today_str = (today or date.today()).isoformat()
    rows = []
    for draft in drafts:
        record = records_by_id.get(draft.job_id)
        previous = existing.get(draft.job_id, {})
        rows.append(
            {
                "job_id": draft.job_id,
                "title": record.title if record else "",
                "company": record.company if record else "",
                "url": record.url if record else "",
                "review_verdict": draft.review_verdict,
                "pdf_ready": "Да" if draft.pdf_ready else "Нет",
                "status": previous.get("status") or DEFAULT_STATUS,
                "notes": previous.get("notes", ""),
                "date_added": previous.get("date_added") or today_str,
            }
        )
    return rows
