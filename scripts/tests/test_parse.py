"""Unit tests for source parsers + report rendering (no network)."""

import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bs4 import BeautifulSoup  # noqa: E402

from scripts.report import (  # noqa: E402
    extract_registered_section, parse_prev_events, render_report,
)
from scripts.sources.asq import _form_fields  # noqa: E402
from scripts.sources.common import Event, TORONTO  # noqa: E402
from scripts.sources.oacett import _parse_cost, _parse_dates  # noqa: E402
from scripts.sources.tpl import _parse_card  # noqa: E402

ASQ_FORM_HTML = """
<form method="post" action="./calendar">
<input type="hidden" name="__VIEWSTATE" value="VS123" />
<input type="hidden" name="__VIEWSTATEGENERATOR" value="GEN1" />
<input type="hidden" name="__EVENTVALIDATION" value="EV9" />
<input type="hidden" name="__HL-RequestVerificationToken" value="TOK" />
<select name="ctl00$MainCopy$ctl06$ddlResultsPerPage">
<option selected="selected" value="20">20 per page</option>
<option value="9999999">All</option>
</select>
</form>
"""

TPL_CARD_HTML = """
<div class="event-details">
  <div class="cp-event-title"><h3 class="cp-heading">
    <a class="cp-link" href="https://tpl.bibliocommons.com/v2/events/abc123">
      <span aria-hidden="true">Meet the Winner of the 2026 Giller Prize</span>
    </a></h3></div>
  <div><span>Wednesday, November 18</span><span>on November 18, 2026</span>,
  <span>6:00pm</span> – <span>7:00pm</span> 6:00pm to 7:00pm |
  Toronto Reference Library | Join us for an evening with the winner.
  | Registration required | Author Talks &amp; Lectures | Adults (18+)</div>
</div>
"""

PREV_MD = """# 專業協會活動報告

## 本輪新增／變動（2026-11-12）

- 新增免費：無

## 只看免費：1 場 ASQ

### ASQ

#### 1. 「Metrics That Matter」（沿用）

- 時間：11/12（四）20:00–22:00 美東
- 連結：https://my.asq.org/events/event-description?CalendarEventKey=cc1f6d77

## 圖書館活動

### TPL

#### AI／科技

##### 1. 「AI Summit 2026 (Livestream)」（沿用）

- 時間：11/28（六）9:45–16:30
- 連結：https://tpl.bibliocommons.com/v2/events/6ad0cabba76c9f3e2ae83cd3

### 圖書館已排除（僅列備查）

- 「Google AI Essentials」（11/5）：已滿額。

## 已報名

- ASQ HIRA 工作坊：10/24 已舉行結束。

## 查證限制

- 無。
"""


class TestAsqForm(unittest.TestCase):
    def test_form_fields_extracted(self):
        soup = BeautifulSoup(ASQ_FORM_HTML, "html.parser")
        fields = _form_fields(soup)
        self.assertEqual(fields["__VIEWSTATE"], "VS123")
        self.assertEqual(fields["__VIEWSTATEGENERATOR"], "GEN1")
        self.assertEqual(fields["__HL-RequestVerificationToken"], "TOK")
        self.assertEqual(fields["ctl00$MainCopy$ctl06$ddlResultsPerPage"], "20")


class TestOacettParse(unittest.TestCase):
    def test_date_range(self):
        s, e, self_study = _parse_dates("Nov. 28 - 29, 2026", date(2026, 11, 13))
        self.assertEqual(s, date(2026, 11, 28))
        self.assertEqual(e, date(2026, 11, 29))
        self.assertFalse(self_study)

    def test_single_date(self):
        s, e, _ = _parse_dates("Dec. 8, 2026", date(2026, 11, 13))
        self.assertEqual(s, date(2026, 12, 8))
        self.assertIsNone(e)

    def test_cost(self):
        status, price = _parse_cost("$375 plus HST & fees")
        self.assertEqual(status, "paid")
        self.assertEqual(price, "$375")
        status, _ = _parse_cost("FREE with code STARTNOW")
        self.assertEqual(status, "free")


class TestTplCard(unittest.TestCase):
    def test_card_parsed(self):
        soup = BeautifulSoup(TPL_CARD_HTML, "html.parser")
        card = soup.select_one("div.event-details")
        parsed = _parse_card(card)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["title"], "Meet the Winner of the 2026 Giller Prize")
        self.assertEqual(parsed["date"], date(2026, 11, 18))
        self.assertEqual(parsed["start"].hour, 18)
        self.assertIn("Toronto Reference Library", parsed["location"])


class TestOspePrice(unittest.TestCase):
    """_detail_price must not mistake footer 'Toll Free' for a free event."""

    def _run(self, html: str):
        from unittest.mock import patch
        from scripts.sources import ospe

        class Resp:
            text = html

        with patch.object(ospe, "get", return_value=Resp()):
            return ospe._detail_price(None, "https://example.com/event/x/")

    def test_toll_free_footer_with_paid_price(self):
        html = ("<html><body><div class='tribe-events-single'>"
                "<h1>Risk, Operational Readiness &amp; Monte Carlo Simulations</h1>"
                "<p>$ 90.00 – $ 190.00 Price range: $90.00 through $190.00</p>"
                "</div><footer>Phone: 416-223-9961 Toll Free: 1-866-763-1654</footer>"
                "</body></html>")
        status, _ = self._run(html)
        self.assertEqual(status, "paid")

    def test_cost_free(self):
        html = ("<html><body><div>Cost: Free to everyone. $0.00</div>"
                "<footer>Toll Free: 1-866-763-1654</footer></body></html>")
        status, _ = self._run(html)
        self.assertEqual(status, "free")

    def test_member_pending(self):
        html = ("<html><body><div>Member Price: $0.00 (Please log in to see "
                "Member pricing) Non-member $59</div></body></html>")
        status, _ = self._run(html)
        self.assertEqual(status, "member_pending")


class TestPrevReport(unittest.TestCase):
    def test_registered_section(self):
        sec = extract_registered_section(PREV_MD)
        self.assertIn("HIRA", sec)
        self.assertNotIn("查證限制", sec)

    def test_prev_events(self):
        evs = parse_prev_events(PREV_MD)
        self.assertEqual(len(evs), 2)
        self.assertIn("https://my.asq.org/events/event-description?CalendarEventKey=cc1f6d77", evs)
        self.assertIn("https://tpl.bibliocommons.com/v2/events/6ad0cabba76c9f3e2ae83cd3", evs)
        self.assertEqual(evs["https://my.asq.org/events/event-description?CalendarEventKey=cc1f6d77"]["title"],
                         "Metrics That Matter")

    def test_render_smoke(self):
        ev = Event(source="asq", title="Metrics That Matter",
                   start=datetime(2026, 11, 12, 20, 0, tzinfo=TORONTO),
                   end=datetime(2026, 11, 12, 22, 0, tzinfo=TORONTO),
                   location="線上", url="https://example.com/x",
                   price_evidence="COST: Free. Open to all.",
                   summary="Six Sigma 指標講座。", relevance="medium",
                   relevance_reason="品質管理", status="free")
        md = render_report(
            today=date(2026, 11, 13), end=date(2026, 12, 25),
            scan_mode="test", assoc_events=[ev], lib_events=[],
            excluded=[], lib_excluded=[], supplementary=[], asq_stats={"listed": 93, "detail_checked": 34, "free": 1, "paid": 0, "unpriced": 0},
            asq_unpriced=[], notes=[], failures=[],
            prev_events={}, registered_section="- HIRA 10/24 已舉行。",
            source_notes={},
        )
        self.assertIn("Metrics That Matter", md)
        self.assertIn("## 已報名", md)
        self.assertIn("HIRA 10/24", md)
        self.assertIn("## 查證限制", md)


if __name__ == "__main__":
    unittest.main()
