from __future__ import annotations

import unittest

from collectors.robota_ua import (
    COMPANY_LINK_PATTERN,
    JOB_LINK_PATTERN,
    build_search_url,
    clean_text,
    truncate_at_contamination,
)


class RobotaUaCollectorTests(unittest.TestCase):
    def test_search_url_targets_all_of_ukraine_with_no_page_segment_on_page_one(self) -> None:
        url = build_search_url("аналітик")
        self.assertEqual(url, "https://robota.ua/zapros/%D0%B0%D0%BD%D0%B0%D0%BB%D1%96%D1%82%D0%B8%D0%BA/ukraine")

    def test_search_url_adds_matrix_page_param_from_page_two_onward(self) -> None:
        url = build_search_url("аналітик", page=3)
        self.assertTrue(url.endswith("/ukraine/params;page=3"))

    def test_job_link_pattern_matches_company_vacancy_path_only(self) -> None:
        self.assertTrue(JOB_LINK_PATTERN.match("/company3235793/vacancy11320135"))
        self.assertFalse(JOB_LINK_PATTERN.match("/company3235793"))
        self.assertFalse(JOB_LINK_PATTERN.match("/vacancy11320135"))

    def test_company_link_pattern_matches_bare_company_path_only(self) -> None:
        self.assertTrue(COMPANY_LINK_PATTERN.match("/company3235793"))
        self.assertFalse(COMPANY_LINK_PATTERN.match("/company3235793/vacancy11320135"))

    def test_truncate_at_contamination_cuts_before_recommended_jobs_section(self) -> None:
        text = "Real job description here.\nГарячі вакансії\nUnrelated Job Title\nAnother Company"
        self.assertEqual(truncate_at_contamination(text), "Real job description here.\n")

    def test_truncate_at_contamination_is_a_noop_when_no_marker_present(self) -> None:
        text = "Just the job description, nothing else."
        self.assertEqual(truncate_at_contamination(text), text)

    def test_clean_text_strips_html_and_collapses_whitespace(self) -> None:
        self.assertEqual(clean_text("<p>SQL &amp; Excel</p>\n\n\n\nExtra"), "SQL & Excel\nExtra")


if __name__ == "__main__":
    unittest.main()
