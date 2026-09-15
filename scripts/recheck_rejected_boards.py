"""Recheck company career boards previously rejected for having zero open jobs.

`config/companies.yaml` lists a few Greenhouse/Lever boards that exist and
respond, but had no postings when checked (Kraken, Prodly) — those aren't
wired into `career_boards` (so `--source company_careers` never touches
them), but a board can start posting at any time without anyone noticing.
This script re-runs the same live API check against just that short list,
on demand, instead of re-mining the whole source list by hand.

Does not touch `career_boards` automatically — a board that now has jobs
still needs a human decision (crypto/analyst relevance) before being added,
so this only reports it.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from collectors.company_careers import (
    DEFAULT_LEVER_HOST,
    build_greenhouse_url,
    build_lever_url,
    parse_greenhouse_jobs,
    parse_lever_jobs,
)

# Boards confirmed to exist (200 OK, valid ATS response) but with zero open
# jobs at the time they were checked. Add an entry here whenever a new board
# turns up in this same "exists but empty" state instead of just noting it
# in a companies.yaml comment and forgetting about it.
REJECTED_CANDIDATES = [
    {"company": "Kraken", "ats": "lever", "slug": "kraken", "host": DEFAULT_LEVER_HOST,
     "reason": "found on Lever, 0 jobs (checked 2026-09-05)"},
    {"company": "Prodly", "ats": "greenhouse", "slug": "prodlyjobs", "host": "",
     "reason": "found on Greenhouse, 0 jobs (checked 2026-09-09)"},
]


@dataclass
class RecheckResult:
    company: str
    ats: str
    slug: str
    reason: str
    status: str  # "ok" | "http_error" | "error"
    job_count: int = 0
    detail: str = ""


def _fetch(url: str) -> dict | list:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def check_board(candidate: dict[str, str]) -> RecheckResult:
    ats, slug = candidate["ats"], candidate["slug"]
    url = build_greenhouse_url(slug) if ats == "greenhouse" else build_lever_url(slug, candidate.get("host") or DEFAULT_LEVER_HOST)
    try:
        payload = _fetch(url)
    except urllib.error.HTTPError as error:
        return RecheckResult(candidate["company"], ats, slug, candidate["reason"], "http_error", detail=f"HTTP {error.code}")
    except Exception as error:  # noqa: BLE001 - report any failure, don't crash the batch
        return RecheckResult(candidate["company"], ats, slug, candidate["reason"], "error", detail=str(error))

    jobs = parse_greenhouse_jobs(payload) if ats == "greenhouse" else parse_lever_jobs(payload)
    return RecheckResult(candidate["company"], ats, slug, candidate["reason"], "ok", job_count=len(jobs))


def format_report(results: list[RecheckResult]) -> str:
    lines = []
    newly_open = [r for r in results if r.status == "ok" and r.job_count > 0]
    still_empty = [r for r in results if r.status == "ok" and r.job_count == 0]
    failed = [r for r in results if r.status != "ok"]

    if newly_open:
        lines.append("Now posting (worth reviewing for a companies.yaml career_boards entry):")
        for r in newly_open:
            lines.append(f"  {r.company} ({r.ats}/{r.slug}): {r.job_count} job(s) — was: {r.reason}")
    else:
        lines.append("Now posting: none")

    if still_empty:
        lines.append("\nStill zero jobs, no change:")
        for r in still_empty:
            lines.append(f"  {r.company} ({r.ats}/{r.slug}) — {r.reason}")

    if failed:
        lines.append("\nCould not check (board may have moved/broken):")
        for r in failed:
            lines.append(f"  {r.company} ({r.ats}/{r.slug}): {r.detail} — {r.reason}")

    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    results = [check_board(candidate) for candidate in REJECTED_CANDIDATES]
    print(format_report(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
