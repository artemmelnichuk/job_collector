from __future__ import annotations

import unittest

from collectors.work_ua import JOB_LINK_PATTERN, build_search_url, clean_text, is_challenge_page_title


class WorkUaCollectorTests(unittest.TestCase):
    def test_search_url_uses_plus_separated_percent_encoded_slug_on_page_one(self) -> None:
        url = build_search_url("бізнес аналітик")
        self.assertTrue(url.startswith("https://www.work.ua/jobs-"))
        self.assertIn("+", url)  # words joined with "+", not URL-encoded %20
        self.assertNotIn("?page=", url)

    def test_search_url_adds_page_param_from_page_two_onward(self) -> None:
        url = build_search_url("аналітик", page=2)
        self.assertTrue(url.endswith("/?page=2"))

    def test_job_link_pattern_matches_only_numeric_job_detail_paths(self) -> None:
        self.assertTrue(JOB_LINK_PATTERN.match("/jobs/8164251/"))
        self.assertFalse(JOB_LINK_PATTERN.match("/jobs/by-company/1308472/"))
        self.assertFalse(JOB_LINK_PATTERN.match("/jobs-analityk/"))

    def test_is_challenge_page_title_detects_cloudflare_style_interstitials(self) -> None:
        self.assertTrue(is_challenge_page_title("Just a moment..."))
        self.assertTrue(is_challenge_page_title("Attention Required! | Cloudflare"))
        self.assertTrue(is_challenge_page_title("Трохи зачекайте…"))
        self.assertFalse(is_challenge_page_title("Робота: аналітик. Вакансії і робота в Україні — Work.ua"))
        self.assertFalse(is_challenge_page_title(""))
        self.assertFalse(is_challenge_page_title(None))

    def test_clean_text_strips_html_and_collapses_whitespace(self) -> None:
        self.assertEqual(clean_text("<p>SQL &amp; Excel</p>\n\n\n\nExtra"), "SQL & Excel\nExtra")


if __name__ == "__main__":
    unittest.main()
