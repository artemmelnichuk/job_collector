# Job Collector

A Python pipeline that collects job postings from several sources, deduplicates and classifies them, shows which skills and certifications the market actually asks for, and drafts application material with a human approval gate. Built for data / business / product analyst roles, with a crypto and fintech lean.

Russian version: [README_RU.md](README_RU.md). Operational notes for contributors and AI assistants: [CLAUDE.md](CLAUDE.md).

> This is the public showcase copy. The real, accumulating dataset and personal review notes live in a private repository; here `data/processed/` holds an empty template with the same schema.

## What it does

```
SEARCH -> COLLECT -> DEDUPLICATE -> SAVE RAW -> MERGE INTO DATASET
                                                     |
             ANALYZE (rules)  ->  REPORTS (skill gap, market demand, recommendations)
                                                     |
             LLM WORKFLOW (optional, paid):  fit score -> draft -> review -> PDF + ATS check -> tracker
```

1. **Collect** postings from six kinds of source into one `JobRecord` schema.
2. **Deduplicate and merge**: a stable ID (`source + normalized URL`) makes reruns idempotent; hand-entered review columns survive every rerun.
3. **Filter** at collection time: language requirements (French, German), on-site roles in excluded countries, scam-like listings, minimum experience.
4. **Analyze** with transparent rules: role family, seniority, years of experience, skills split into required and preferred.
5. **Report**: which skills recur in near-fit postings but are missing from the candidate's toolset, joined with the share of all postings that mention them and whether anyone asks for a certificate. Actions (`learn`, `optional`, `low priority`, `verify first`) are computed from thresholds, never from hardcoded tool names.
6. **Apply (optional, uses an LLM API)**: score fit, draft a short pitch and CV bullets, review the draft with a separate model call, assemble a PDF, check its text layer for the posting's keywords, and track status in a sheet. Nothing is ever sent automatically.

## Sources

| Source | How | Notes |
|---|---|---|
| LinkedIn | Playwright, JSON-LD first, CSS fallback | Authwalls and markup drift are expected failure modes |
| Company career boards | Greenhouse and Lever public APIs | Boards are listed in `config/companies.yaml` |
| Djinni | RSS | Ukrainian IT board, own category vocabulary |
| RemoteOK | JSON API | Remote-only; filtered locally by title |
| We Work Remotely | RSS | Remote-only; small rolling window |
| Welcome to the Jungle | Playwright | Opt-in only (`--source wttj`) |
| Work.ua, Robota.ua | Playwright | Implemented, but blocked by anti-bot protection; opt-in only |

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# validate configuration only
.venv\Scripts\python.exe -B scripts\collector.py --dry-run

# collect from all default sources
.venv\Scripts\python.exe -B scripts\collector.py --source all --limit 50

# classify and extract skills
.venv\Scripts\python.exe -B scripts\analyzer.py

# what to study: skill gap + market demand + recommendations
.venv\Scripts\python.exe -B scripts\skills_gap_report.py

# how often tools and certifications appear in the collected postings
.venv\Scripts\python.exe -B scripts\certification_analysis.py

# recheck whether saved postings are still open
.venv\Scripts\python.exe -B scripts\collector.py --check-availability --check-limit 500 --headless

# tests
.venv\Scripts\python.exe -B -m unittest discover -s tests
```

The application workflow reads a master CV from `CV/` (not in the repository) and needs `ANTHROPIC_API_KEY`. Every LLM call is billed, so these steps are separate scripts with per-run limits:

```powershell
.venv\Scripts\python.exe -B scripts\fit_score.py --limit 20     # score undecided postings
.venv\Scripts\python.exe -B scripts\cv_draft.py --limit 10      # draft pitch + CV bullets
.venv\Scripts\python.exe -B scripts\cv_review.py --limit 10     # separate reviewer call
.venv\Scripts\python.exe -B scripts\cv_pdf.py --limit 20        # PDF + ATS text-layer check (free)
.venv\Scripts\python.exe -B scripts\applications_tracker.py     # status sheet (free)
```

## Design notes

- **One schema.** Every collector returns the same `JobRecord`; normalization happens after parsing, not during it, because sources give incomplete and inconsistent data.
- **Reruns are safe.** Identity is derived from the URL, merge preserves manual columns, and analysis results carry forward when a posting is re-collected.
- **Honesty gate in the LLM workflow.** The drafting prompt may only rephrase what is in the CV, and a separate review call checks each draft for unsupported claims, wrong location claims, relevance and tone. Real failures found and fixed this way are documented in [CLAUDE.md](CLAUDE.md).
- **Human approval.** The application tracker has `draft / approved / rejected / sent`; only a person moves a row to `sent`.
- **Fragile sources are labeled as such.** Browser-scraped sources can break at any time and some sites block automation outright; both facts are recorded rather than hidden.
- **Privacy by construction.** Personal contact details are read from the local CV at run time instead of living in the code, and the public copy is produced by a script that scans every file for personal identifiers and refuses to publish on a match.

## Layout

```text
config/       queries, companies and ATS boards, run settings
collectors/   one adapter per source
core/         models, storage, analyzer, skill gap and recommendations, LLM steps
scripts/      command-line entry points
data/raw/     one file per collection run (not tracked)
data/processed/  accumulating dataset (empty template in this copy)
tests/        unit and browser-integration tests
```

## Limitations

- LinkedIn and Welcome to the Jungle have no stable public API; markup changes will break selectors.
- Skill extraction is rule-based. Short tokens (`R`) and generic words (`ML`) produce false positives; the recommendation report flags those skills instead of trusting them.
- Market counts describe the collected sample (built around one search profile), not the whole job market.
- Portions of this project were developed with Claude Code assistance.
