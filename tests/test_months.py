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


class FakeCursor:
    """Records the SQL it was handed and replays one canned result."""

    def __init__(self, rows):
        self.rows = rows
        self.sql = None
        self.params = None

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return self.rows


class TestAvailableMonths:
    def test_unions_both_ledgers_by_default(self):
        cur = FakeCursor([{'m': '2026-09'}, {'m': '2026-08'}])
        assert months.available_months(cur, 7) == ['2026-09', '2026-08']
        assert 'FROM expense' in cur.sql
        assert 'FROM income' in cur.sql
        assert cur.params == (7, 7)

    def test_can_be_narrowed_to_one_ledger(self):
        """The expenses page must not offer months it has no expenses for."""
        cur = FakeCursor([{'m': '2026-09'}])
        assert months.available_months(cur, 7, tables=('expense',)) == ['2026-09']
        assert 'FROM income' not in cur.sql
        assert cur.params == (7,)

    def test_drops_null_months(self):
        cur = FakeCursor([{'m': '2026-09'}, {'m': None}])
        assert months.available_months(cur, 7) == ['2026-09']

    def test_placeholders_survive_the_format_string(self):
        """DATE_FORMAT's %Y/%m must reach the driver, not be eaten by str.format."""
        cur = FakeCursor([])
        months.available_months(cur, 7, tables=('expense',))
        assert "DATE_FORMAT(date, '%Y-%m')" in cur.sql
        assert cur.sql.count('%s') == 1


class TestMonthOptions:
    def test_labels_each_month(self):
        cur = FakeCursor([{'m': '2026-09'}])
        assert months.month_options(cur, 7) == [('2026-09', 'September 2026')]

    def test_keeps_the_selected_month_selectable(self):
        """A month emptied of rows must stay in its own dropdown."""
        cur = FakeCursor([{'m': '2026-09'}])
        assert months.month_options(cur, 7, selected='2026-10') == [
            ('2026-10', 'October 2026'), ('2026-09', 'September 2026')
        ]

    def test_does_not_duplicate_an_existing_month(self):
        cur = FakeCursor([{'m': '2026-09'}])
        assert months.month_options(cur, 7, selected='2026-09') == [
            ('2026-09', 'September 2026')
        ]


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
