from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.cv_pdf import ATS_SECTION_MARKER, select_draft_files


class SelectDraftFilesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp_dir.name)

        (self.dir / "no_pdf_no_ats.md").write_text("# Title\n\n> pitch\n", encoding="utf-8")

        done_content = f"# Title\n\n> pitch\n\n---\n\n{ATS_SECTION_MARKER}\n\nchecked\n"
        (self.dir / "done.md").write_text(done_content, encoding="utf-8")
        (self.dir / "done.pdf").write_bytes(b"%PDF-1.4 fake")

        # Has the ATS section text but the .pdf file itself is missing - should still be reprocessed.
        (self.dir / "ats_text_but_no_pdf_file.md").write_text(done_content, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_missing_directory_returns_empty(self) -> None:
        self.assertEqual(select_draft_files(self.dir / "nope", regenerate=False), [])

    def test_selects_files_missing_pdf_or_ats_section(self) -> None:
        files = select_draft_files(self.dir, regenerate=False)
        names = sorted(path.name for path in files)
        self.assertEqual(names, ["ats_text_but_no_pdf_file.md", "no_pdf_no_ats.md"])

    def test_regenerate_includes_the_fully_done_file_too(self) -> None:
        files = select_draft_files(self.dir, regenerate=True)
        names = sorted(path.name for path in files)
        self.assertEqual(names, ["ats_text_but_no_pdf_file.md", "done.md", "no_pdf_no_ats.md"])


if __name__ == "__main__":
    unittest.main()
