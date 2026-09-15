from __future__ import annotations

import unittest

from scripts.active_near_fit_report import build_active_near_fit


class ActiveNearFitReportTests(unittest.TestCase):
    def test_keeps_only_active_near_fit_not_filtered(self) -> None:
        rows = [
            {"decision": "Подходит", "should_be_filtered": "Нет", "availability_status": "active", "title": "A"},
            {"decision": "Подходит", "should_be_filtered": "Нет", "availability_status": "closed", "title": "B"},
            {"decision": "Не подходит", "should_be_filtered": "Нет", "availability_status": "active", "title": "C"},
            {"decision": "Возможно", "should_be_filtered": "Да", "availability_status": "active", "title": "D"},
            {"decision": "Возможно", "should_be_filtered": "Нет", "availability_status": "active", "title": "E"},
        ]
        kept = build_active_near_fit(rows)
        self.assertEqual([row["title"] for row in kept], ["A", "E"])

    def test_sorts_подходит_before_возможно(self) -> None:
        rows = [
            {"decision": "Возможно", "should_be_filtered": "Нет", "availability_status": "active", "title": "First", "source": "A"},
            {"decision": "Подходит", "should_be_filtered": "Нет", "availability_status": "active", "title": "Second", "source": "B"},
        ]
        kept = build_active_near_fit(rows)
        self.assertEqual([row["title"] for row in kept], ["Second", "First"])


if __name__ == "__main__":
    unittest.main()
