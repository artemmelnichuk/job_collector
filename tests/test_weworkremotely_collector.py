from __future__ import annotations

import unittest

from collectors.weworkremotely import (
    parse_rss_items,
    record_from_item,
    split_company_title,
)


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>We Work Remotely</title>
<item>
<title>UTTR: Project Manager</title>
<region>Anywhere in the World</region>
<country></country>
<state>New York</state>
<category>Sales and Marketing</category>
<type>Full-Time</type>
<description>&lt;p&gt;Manage projects. Salary: $60,000 - $80,000&lt;/p&gt;</description>
<pubDate>Wed, 09 Sep 2026 15:41:42 +0000</pubDate>
<guid>https://weworkremotely.com/remote-jobs/uttr-project-manager</guid>
<link>https://weworkremotely.com/remote-jobs/uttr-project-manager</link>
</item>
<item>
<title>LawnStarter: Data Governance and Platform Manager</title>
<region>Anywhere in the World</region>
<country>United States</country>
<state></state>
<category>Product</category>
<type>Full-Time</type>
<description>&lt;p&gt;Own data governance across the platform.&lt;/p&gt;</description>
<pubDate>Tue, 08 Sep 2026 10:00:00 +0000</pubDate>
<guid>https://weworkremotely.com/remote-jobs/lawnstarter-data-governance</guid>
<link>https://weworkremotely.com/remote-jobs/lawnstarter-data-governance</link>
</item>
</channel></rss>"""


class WeWorkRemotelyCollectorTests(unittest.TestCase):
    def test_split_company_title_splits_on_first_colon_space(self) -> None:
        self.assertEqual(split_company_title("UTTR: Project Manager"), ("UTTR", "Project Manager"))

    def test_split_company_title_handles_colon_in_job_title_too(self) -> None:
        # partition() splits on the FIRST ": " only, so a second colon in the
        # job title itself (e.g. a subtitle) stays part of the title.
        self.assertEqual(
            split_company_title("Toptal: Senior Consultant (SOC 2 & GRC): Remote"),
            ("Toptal", "Senior Consultant (SOC 2 & GRC): Remote"),
        )

    def test_split_company_title_falls_back_when_no_separator(self) -> None:
        self.assertEqual(split_company_title("Data Analyst"), ("", "Data Analyst"))

    def test_parse_rss_items_reads_all_fields(self) -> None:
        items = parse_rss_items(SAMPLE_RSS)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "UTTR: Project Manager")
        self.assertEqual(items[0]["region"], "Anywhere in the World")
        self.assertEqual(items[1]["country"], "United States")
        self.assertEqual(items[1]["category"], "Product")

    def test_parse_rss_items_tolerates_malformed_xml(self) -> None:
        self.assertEqual(parse_rss_items("not xml at all <<<"), [])

    def test_record_from_item_splits_company_and_infers_remote(self) -> None:
        items = parse_rss_items(SAMPLE_RSS)
        query = {"query": "Data Analyst", "category": "data"}

        record = record_from_item(items[1], query)
        self.assertEqual(record.source, "We Work Remotely")
        self.assertEqual(record.company, "LawnStarter")
        self.assertEqual(record.title, "Data Governance and Platform Manager")
        self.assertEqual(record.work_format, "Remote")
        self.assertEqual(record.country, "United States")
        self.assertEqual(record.contract_type, "Full-Time")
        self.assertTrue(record.job_id)

    def test_record_from_item_extracts_salary_from_description(self) -> None:
        items = parse_rss_items(SAMPLE_RSS)
        record = record_from_item(items[0], {"query": "Project Manager", "category": "other"})
        self.assertIn("60,000", record.salary)


if __name__ == "__main__":
    unittest.main()
