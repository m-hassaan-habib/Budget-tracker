"""
Test suite for month derivation.

Every month-scoped query in the app now depends on these boundaries, so the
awkward cases -- February, December, January -- are worth pinning down.
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import months


class TestMonthBounds:
    def test_ordinary_month(self):
        assert months.month_bounds('2026-09') == (date(2026, 9, 1), date(2026, 9, 30))

    def test_february_in_a_leap_year(self):
        assert months.month_bounds('2024-02') == (date(2024, 2, 1), date(2024, 2, 29))

    def test_february_in_a_common_year(self):
        assert months.month_bounds('2026-02') == (date(2026, 2, 1), date(2026, 2, 28))

    def test_december_rolls_into_next_year(self):
        assert months.month_bounds('2026-12') == (date(2026, 12, 1), date(2026, 12, 31))

    def test_bounds_are_inclusive(self):
        """Queries use BETWEEN, so the last day must be inside the range."""
        start, end = months.month_bounds('2026-09')
        assert start.day == 1
        assert (end + months.ONE_DAY).month == 10


class TestPreviousMonth:
    def test_mid_year(self):
        assert months.previous_month('2026-09') == '2026-08'

    def test_january_goes_back_a_year(self):
        assert months.previous_month('2026-01') == '2025-12'


class TestParseAndFormat:
    def test_parse_valid(self):
        assert months.parse_month('2026-09') == date(2026, 9, 1)

    def test_parse_rejects_garbage(self):
        assert months.parse_month('nonsense') is None
        assert months.parse_month('') is None
        assert months.parse_month(None) is None
        assert months.parse_month('2026-13') is None

    def test_format(self):
        assert months.format_month('2026-09') == 'September 2026'

    def test_format_passes_through_unparseable(self):
        assert months.format_month('whatever') == 'whatever'

    def test_month_key(self):
        assert months.month_key(date(2026, 9, 21)) == '2026-09'


class TestResolveMonth:
    class FakeRequest:
        def __init__(self, args):
            self.args = args

    def test_uses_requested_month(self):
        req = self.FakeRequest({'month': '2026-03'})
        assert months.resolve_month(req) == '2026-03'

    def test_falls_back_to_current_month(self):
        req = self.FakeRequest({})
        assert months.resolve_month(req) == months.current_month()

    def test_ignores_a_bad_month(self):
        """A junk ?month= must not blow up the dashboard."""
        req = self.FakeRequest({'month': 'drop-table'})
        assert months.resolve_month(req) == months.current_month()
