"""Turn the skill-gap report into study recommendations backed by market data.

`core/skills_gap.py` says which skills recur in near-fit postings but are
missing from the candidate's toolset. That alone can't say whether a skill
is worth learning: it may be demanded by a handful of hand-picked postings
only. This module adds the market side - what share of ALL collected
postings mention the skill, and whether anyone asks for a certificate in
it - and derives a plain action from those numbers. Nothing here names a
specific tool or certificate; every recommendation is computed.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping

from core.analyzer import SKILL_PATTERN_BY_NAME
from core.skills_gap import SkillGapReport

# A gap skill needs this share of all collected postings to count as core
# demand, and a lower one to count as an optional extra.
LEARN_MIN_MARKET_SHARE = 0.10
OPTIONAL_MIN_MARKET_SHARE = 0.03
# A skill seen in fewer near-fit postings than this may be one employer's quirk.
MIN_NEAR_FIT_POSTINGS = 2
# A certificate mentioned in fewer postings than this is not a market signal.
CERT_MIN_POSTINGS = 3
CERT_PROXIMITY_CHARS = 60

# The analyzer's patterns for these match bare short tokens or generic words,
# so their market counts overstate real demand (see CLAUDE.md).
LOW_CONFIDENCE_SKILLS = {"R", "Machine Learning"}

_CERT_WORD = r"(?:certif\w*|сертиф\w*)"


@dataclass(slots=True)
class Recommendation:
    skill: str
    status: str  # "gap" (missing) or "partial" (known at a basic level)
    near_fit_postings: int
    market_postings: int
    market_share: float
    cert_postings: int
    action: str
    certificate_advice: str
    note: str


def normalize_key(company: object, title: object) -> str:
    def clean(value: object) -> str:
        return re.sub(r"\s+", " ", str(value if value == value else "").strip().lower())

    return f"{clean(company)}|{clean(title)}"


def dedupe_rows(rows: Iterable[Mapping[str, object]]) -> list[Mapping[str, object]]:
    """Keep the first posting per normalized company + title."""
    seen: set[str] = set()
    kept = []
    for row in rows:
        key = normalize_key(row.get("company", ""), row.get("title", ""))
        if key not in seen:
            seen.add(key)
            kept.append(row)
    return kept


def posting_text(row: Mapping[str, object]) -> str:
    return f"{row.get('title', '') or ''}\n{row.get('full_text', '') or ''}".casefold()


def count_market_demand(texts: Iterable[str], skills: Iterable[str]) -> Counter:
    """Postings mentioning each skill, one count per posting."""
    patterns = {s: re.compile(SKILL_PATTERN_BY_NAME[s], re.IGNORECASE) for s in skills if s in SKILL_PATTERN_BY_NAME}
    counts: Counter = Counter()
    for text in texts:
        for skill, pattern in patterns.items():
            if pattern.search(text):
                counts[skill] += 1
    return counts


def count_certification_mentions(texts: Iterable[str], skills: Iterable[str]) -> Counter:
    """Postings where a certification word sits within a short span of the skill."""
    compiled = {}
    for skill in skills:
        base = SKILL_PATTERN_BY_NAME.get(skill)
        if base:
            near = rf"{_CERT_WORD}[^\n]{{0,{CERT_PROXIMITY_CHARS}}}?(?:{base})|(?:{base})[^\n]{{0,{CERT_PROXIMITY_CHARS}}}?{_CERT_WORD}"
            compiled[skill] = re.compile(near, re.IGNORECASE)
    counts: Counter = Counter()
    for text in texts:
        for skill, pattern in compiled.items():
            if pattern.search(text):
                counts[skill] += 1
    return counts


def _action(near_fit: int, share: float) -> str:
    if near_fit < MIN_NEAR_FIT_POSTINGS:
        return "low priority"
    if share >= LEARN_MIN_MARKET_SHARE:
        return "learn"
    if share >= OPTIONAL_MIN_MARKET_SHARE:
        return "optional"
    return "low priority"


def _certificate_advice(cert_postings: int) -> str:
    if cert_postings >= CERT_MIN_POSTINGS:
        return f"certificate mentioned in {cert_postings} postings: worth considering"
    if cert_postings:
        return f"certificate mentioned in {cert_postings} posting(s): not a market signal, learn the skill instead"
    return "no certificate asked: learn the skill, skip the exam"


def build_recommendations(
    report: SkillGapReport,
    market_counts: Mapping[str, int],
    cert_counts: Mapping[str, int],
    market_total: int,
) -> list[Recommendation]:
    """One recommendation per missing or partially known skill, most demanded first."""
    rows = []
    for status, skills in (("gap", report.gap), ("partial", report.partial)):
        for skill in skills:
            near_fit = report.demand[skill]
            market = market_counts.get(skill, 0)
            share = market / market_total if market_total else 0.0
            action = _action(near_fit, share)
            if action == "learn" and skill in LOW_CONFIDENCE_SKILLS:
                action = "verify first"
            rows.append(Recommendation(
                skill=skill,
                status=status,
                near_fit_postings=near_fit,
                market_postings=market,
                market_share=share,
                cert_postings=cert_counts.get(skill, 0),
                action=action,
                certificate_advice=_certificate_advice(cert_counts.get(skill, 0)),
                note="pattern matches short or generic tokens, market count is inflated" if skill in LOW_CONFIDENCE_SKILLS else "",
            ))
    rows.sort(key=lambda r: (-r.near_fit_postings, -r.market_postings, r.skill))
    return rows


def format_recommendation(rec: Recommendation) -> str:
    line = (f"{rec.action.upper():<13} {rec.skill}: near-fit {rec.near_fit_postings}, "
            f"all postings {rec.market_postings} ({rec.market_share:.0%}); {rec.certificate_advice}")
    if rec.status == "partial":
        line += " [known at a basic level: go deeper]"
    if rec.note:
        line += f" [{rec.note}]"
    return line
