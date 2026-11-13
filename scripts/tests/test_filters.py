"""Unit tests for shared helpers (no network)."""

import sys
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.sources.common import (  # noqa: E402
    classify, extract_price_evidence, location_ok, parse_asq_when,
    parse_month_day_year, parse_time_range,
)


class TestParseAsqWhen(unittest.TestCase):
    def test_mountain_time_converted_to_toronto(self):
        when = parse_asq_when("When: Thu, Nov 12, 2026 from 06:00 PM to 08:00 PM (MT)")
        self.assertIsNotNone(when)
        start, end = when
        # 18:00 MST = 20:00 EST
        self.assertEqual((start.hour, start.minute), (20, 0))
        self.assertEqual((end.hour, end.minute), (22, 0))
        self.assertEqual(start.date(), date(2026, 11, 12))

    def test_pacific_time(self):
        when = parse_asq_when("When: Thu, Nov 5, 2026 from 06:00 PM to 08:00 PM (PT)")
        self.assertIsNotNone(when)
        self.assertEqual(when[0].hour, 21)  # 18:00 PST = 21:00 EST

    def test_unparseable_returns_none(self):
        self.assertIsNone(parse_asq_when("When: sometime next week"))


class TestPriceEvidence(unittest.TestCase):
    def test_free_verbatim(self):
        status, ev, _ = extract_price_evidence("COST: Free. Open to all.")
        self.assertEqual(status, "free")
        self.assertIn("Free", ev)

    def test_no_charge(self):
        status, _, _ = extract_price_evidence("There is no charge, but advance registration is required.")
        self.assertEqual(status, "free")

    def test_zero_dollars(self):
        status, _, _ = extract_price_evidence("Web-Based Connection - $0")
        self.assertEqual(status, "free")

    def test_paid(self):
        status, _, amount = extract_price_evidence("Cost: $20 for members, $25 otherwise.")
        self.assertEqual(status, "paid")
        self.assertEqual(amount, "$20")

    def test_unpriced(self):
        status, _, _ = extract_price_evidence("Join us on Zoom for this session.")
        self.assertEqual(status, "unpriced")


class TestClassify(unittest.TestCase):
    def test_high_medtech(self):
        include, rel, _ = classify("Beyond the Clinical Trial: Real-World Data Across the Device Lifecycle")
        self.assertTrue(include)
        self.assertEqual(rel, "high")

    def test_ai_quality(self):
        include, rel, _ = classify("Applying Artificial Intelligence to Quality and Reliability")
        self.assertTrue(include)

    def test_civil_excluded(self):
        include, _, _ = classify("Modern Tall Timber Construction in the Ontario Building Code")
        self.assertFalse(include)

    def test_ospe_civil_titles_excluded(self):
        for t in [
            "Designing for the Future: Using Climate Information to Support Resilient Infrastructure",
            "Pollution in the Distribution Network",
            "Upstream of Engineering: How Land Development Decisions Shape the Work That Follows",
            "PEO Canada's Cities in a Changing World 1920-2120: An Engineer's Perspective",
        ]:
            self.assertFalse(classify(t)[0], t)

    def test_ospe_licensing_titles_included(self):
        for t in [
            "PE300 – Journey to P.Eng",
            "CBA Workshop: Crafting Your CBA Stories",
            "Antimicrobial Resistance (AMR), the New Challenge",
            "Risk, Operational Readiness (OR) & Monte Carlo Simulations",
        ]:
            self.assertTrue(classify(t)[0], t)

    def test_generic_book_club_excluded(self):
        for t in ["Book Club", "Afternoon Book Club", "Mimico Book Club",
                  "Afternoon Silent Book Club", "Reading Challenge Book Club"]:
            self.assertFalse(classify(t)[0], t)
        self.assertTrue(classify("Dystopia Nonfiction Book Club: AI Snake Oil")[0])

    def test_kids_excluded(self):
        include, _, _ = classify("Kids Storytime: Dragons Love Tacos")
        self.assertFalse(include)

    def test_retirement_excluded(self):
        include, _, _ = classify("Your Retirement Reset: A Guide to Retiring Well")
        self.assertFalse(include)

    def test_teens_excluded(self):
        include, _, _ = classify("Lego Robotics and Coding for Teens")
        self.assertFalse(include)

    def test_after_school_excluded(self):
        include, _, _ = classify("After School Club: Robots!")
        self.assertFalse(include)

    def test_social_excluded(self):
        include, _, _ = classify("Coffee Talk! Conflict in the Workplace")
        self.assertFalse(include)

    def test_gala_excluded(self):
        include, _, _ = classify("2026 Ontario Professional Engineers Awards Gala")
        self.assertFalse(include)

    def test_writing_included(self):
        include, _, _ = classify("Community Writing Workshop")
        self.assertTrue(include)


class TestLocation(unittest.TestCase):
    def test_online(self):
        ok, _ = location_ok("Online (Zoom)")
        self.assertTrue(ok)

    def test_chinese_online(self):
        # Regression (2026-11-13): location_ok("線上") returned False, which
        # excluded every free ASQ event whose listing Where: was blank.
        ok, _ = location_ok("線上")
        self.assertTrue(ok)

    def test_empty_unknown(self):
        ok, _ = location_ok("")
        self.assertTrue(ok)

    def test_toronto(self):
        ok, _ = location_ok("Toronto Reference Library")
        self.assertTrue(ok)

    def test_out_of_province(self):
        ok, _ = location_ok("Middleton, WI")
        self.assertFalse(ok)


class TestDates(unittest.TestCase):
    def test_month_day_year(self):
        self.assertEqual(parse_month_day_year("Nov. 28, 2026"), date(2026, 11, 28))
        self.assertEqual(parse_month_day_year("November 25, 2026"), date(2026, 11, 25))

    def test_time_range(self):
        d = date(2026, 11, 12)
        s, e = parse_time_range("6:00pm - 8:00pm", d)
        self.assertEqual((s.hour, e.hour), (18, 20))

    def test_time_range_am_pm(self):
        d = date(2026, 11, 12)
        s, e = parse_time_range("09:00 am - 12:00 pm", d)
        self.assertEqual((s.hour, s.minute), (9, 0))
        self.assertEqual((e.hour, e.minute), (12, 0))


if __name__ == "__main__":
    unittest.main()
