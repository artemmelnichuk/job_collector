from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.cv_review import ReviewResult, append_review_section
from scripts.cv_review import select_draft_files


class SelectDraftFilesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp_dir.name)
        (self.dir / "not_reviewed.md").write_text("# Title\n\n> pitch\n", encoding="utf-8")
        reviewed = append_review_section("# Title\n\n> pitch\n", ReviewResult(verdict="approved", issues=[]))
        (self.dir / "already_reviewed.md").write_text(reviewed, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_missing_directory_returns_empty(self) -> None:
        self.assertEqual(select_draft_files(self.dir / "nope", regenerate=False), [])

    def test_only_unreviewed_by_default(self) -> None:
        files = select_draft_files(self.dir, regenerate=False)
        self.assertEqual([path.name for path in files], ["not_reviewed.md"])

    def test_regenerate_includes_already_reviewed_files(self) -> None:
        files = select_draft_files(self.dir, regenerate=True)
        self.assertEqual(
            sorted(path.name for path in files), ["already_reviewed.md", "not_reviewed.md"]
        )


if __name__ == "__main__":
    unittest.main()
