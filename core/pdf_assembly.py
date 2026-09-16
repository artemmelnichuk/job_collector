"""Assemble a one-page cover-note PDF from a reviewed draft, and run a
mechanical ATS-style keyword check against its extracted text layer (plan
item 8.4).

No LLM call here - the drafting (8.2) and reviewing (8.3) are already done
by the time this runs; this step is purely mechanical: render the existing
markdown draft's pitch + bullets to a real PDF via Playwright (already a
project dependency, no new one needed for rendering), then verify the
PDF's text layer actually contains the posting's key skills the way a real
ATS keyword parser would read it - catching the real, mundane failure mode
where a PDF renders visually fine but its text layer is garbled or
unselectable (bad font embedding, ligatures, etc.), not just checking the
source markdown we already trust.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import async_playwright
from pypdf import PdfReader

from core.models import JobRecord

_BULLETS_SECTION_RE = re.compile(
    r"## Адаптированные пункты для CV\s*\n\n(.*?)\n\n---", re.DOTALL
)
_PITCH_RE = re.compile(r"^> (.+)$", re.MULTILINE)
_BULLET_LINE_RE = re.compile(r"^- (.+)$", re.MULTILINE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_LINKEDIN_RE = re.compile(r"linkedin\.com/in/\S+")


def extract_contact_line(cv_text: str) -> str:
    """Pull a "Name · email · linkedin" contact line straight out of the
    candidate's own CV text instead of hardcoding it - keeps personal
    contact details out of source code entirely (`CV/` is gitignored, this
    module isn't).
    """
    lines = [line.strip() for line in cv_text.strip().splitlines() if line.strip()]
    name = lines[0] if lines else ""
    # BeautifulSoup's get_text() includes the <title> tag ("Name — Resume"),
    # which lands as the very first line ahead of the real body header
    # ("Name") - prefer the body header when the title line is just that
    # name with extra suffix text tacked on.
    if len(lines) > 1 and name != lines[1] and name.casefold().startswith(lines[1].casefold()):
        name = lines[1]
    email_match = _EMAIL_RE.search(cv_text)
    linkedin_match = _LINKEDIN_RE.search(cv_text)
    parts = [part for part in (name, email_match.group(0) if email_match else "",
                                linkedin_match.group(0) if linkedin_match else "") if part]
    return " · ".join(parts)


@dataclass
class DraftContent:
    pitch: str
    bullets: list[str]


def extract_draft_content(draft_markdown: str) -> DraftContent:
    """Pull the pitch paragraph and CV bullets back out of a rendered (and
    possibly hand-edited) draft .md file - the only two parts of the file
    that are the candidate's own words, as opposed to metadata or review
    commentary appended later.
    """
    pitch_match = _PITCH_RE.search(draft_markdown)
    pitch = pitch_match.group(1).strip() if pitch_match else ""

    bullets: list[str] = []
    section_match = _BULLETS_SECTION_RE.search(draft_markdown)
    if section_match:
        bullets = [line.strip() for line in _BULLET_LINE_RE.findall(section_match.group(1))]
    return DraftContent(pitch=pitch, bullets=bullets)


def build_cover_note_html(record: JobRecord, draft: DraftContent, contact_line: str = "") -> str:
    bullets_html = "\n".join(f"<li>{_escape(bullet)}</li>" for bullet in draft.bullets)
    meta_html = f'<div class="meta">{_escape(contact_line)}</div>' if contact_line else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  body {{ font-family: Georgia, 'Times New Roman', serif; color: #1a1a1a; font-size: 12pt;
          line-height: 1.5; margin: 48px 56px; }}
  h1 {{ font-size: 15pt; margin: 0 0 4px; }}
  .meta {{ color: #555; font-size: 10.5pt; margin-bottom: 24px; }}
  p {{ margin: 0 0 16px; }}
  ul {{ margin: 0; padding-left: 20px; }}
  li {{ margin-bottom: 6px; }}
</style></head>
<body>
  <h1>{_escape(record.title)} — {_escape(record.company)}</h1>
  {meta_html}
  <p>{_escape(draft.pitch)}</p>
  <ul>{bullets_html}</ul>
</body></html>"""


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def render_pdf(html: str, output_path: Path) -> None:
    """Render HTML to a PDF file via a headless Chromium page - PDF export
    only works in headless mode, which this always wants anyway.
    """
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(html)
            await page.pdf(path=str(output_path), format="A4")
        finally:
            await browser.close()


def extract_pdf_text(pdf_path: Path) -> str:
    """Read back a PDF's actual text layer - not the HTML/markdown we wrote,
    since the point is to catch rendering-introduced text-layer problems a
    real ATS parser would also hit.
    """
    reader = PdfReader(str(pdf_path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


@dataclass
class AtsCheckResult:
    matched: list[str]
    missing: list[str]


def posting_keywords(record: JobRecord) -> list[str]:
    """The posting's own key skills, per the rule-based analyzer - reusing
    that output instead of a fresh LLM call keeps this whole step free.
    """
    combined = f"{record.required_skills};{record.preferred_skills}"
    return [skill.strip() for skill in combined.split(";") if skill.strip()]


def check_ats_keywords(pdf_text: str, keywords: list[str]) -> AtsCheckResult:
    lowered = pdf_text.casefold()
    matched = [keyword for keyword in keywords if keyword.casefold() in lowered]
    missing = [keyword for keyword in keywords if keyword.casefold() not in lowered]
    return AtsCheckResult(matched=matched, missing=missing)


def render_ats_section(result: AtsCheckResult, pdf_char_count: int) -> str:
    if not result.matched and not result.missing:
        keywords_summary = "_Анализатор не выделил ключевых навыков для этой вакансии - нечего сверять._"
    else:
        matched_line = ", ".join(result.matched) if result.matched else "(нет)"
        missing_line = ", ".join(result.missing) if result.missing else "(нет)"
        keywords_summary = f"**Найдены в PDF:** {matched_line}\n\n**Отсутствуют в PDF:** {missing_line}"
    text_layer_note = (
        "✅ Текстовый слой PDF читается нормально"
        if pdf_char_count > 0
        else "⚠️ Текстовый слой PDF пустой или не извлекается — PDF может быть нечитаем для ATS"
    )
    return (
        "\n---\n\n"
        "## ATS-проверка текстового слоя (plan item 8.4)\n\n"
        f"{text_layer_note} ({pdf_char_count} символов извлечено).\n\n"
        f"{keywords_summary}\n\n"
        "_Сверка чисто механическая (по required_skills/preferred_skills из analyzer.py), без LLM. "
        "Отсутствие навыка в списке не значит, что резюме плохое — часть навыков намеренно не включена в pitch, "
        "если её нет в CV (см. правило честности 8.2)._\n"
    )
