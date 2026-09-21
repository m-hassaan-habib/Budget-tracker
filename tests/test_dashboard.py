"""
Test suite for the dashboard.

Covers the three questions the dashboard exists to answer -- where the money
went, what changed vs last month, who spent it -- plus the month scoping that
the old all-time SUM() had no notion of.
"""

import os
import sys
from decimal import Decimal
from datetime import date
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from routes.dashboard import _movers


def make_mock_connection():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor
    return conn, cursor


def login_session(client, user_id=1):
    with client.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['user_name'] = 'Test User'
        sess['household_members'] = ['Faisal', 'Hassan']
        sess['actor'] = 'Hassan'


def wire(cursor, *, setting=None, month_expense='5000.00', prev_expense='4000.00',
         month_income='10000.00', categories=None, prev_categories=None,
         people=None, daily=None, recent=None, count=3,
         all_income='20000.00', all_expense='9000.00', months=None):
    """Feed the cursor the sequence the dashboard actually asks for."""
    cursor.fetchone.side_effect = [
        setting if setting is not None else {
            'monthly_limit': Decimal('50000.00'),
            'total_savings': Decimal('1000.00'),
            'use_automated_income': 0,
        },
        {'total': Decimal(month_expense)},
        {'total': Decimal(prev_expense)},
        {'total': Decimal(month_income)},
        {'cnt': count},
        {'total': Decimal(all_income)},
        {'total': Decimal(all_expense)},
    ]
    cursor.fetchall.side_effect = [
        categories if categories is not None else [],
        prev_categories if prev_categories is not None else [],
        people if people is not None else [],
        daily if daily is not None else [],
        recent if recent is not None else [],
        months if months is not None else [],
    ]


class TestDashboardAccess:
    def test_requires_auth(self, client):
        response = client.get('/')
        assert response.status_code in (302, 308)
        assert '/auth/login' in response.headers.get('Location', '')

    def test_renders_when_logged_in(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)
        conn, cursor = make_mock_connection()
        wire(cursor)
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/')
        assert response.status_code == 200


class TestMonthScoping:
    def test_queries_are_bounded_by_the_month(self, client_no_csrf, app_no_csrf):
        """The old dashboard summed the whole table with no date filter at
        all, so its headline numbers weren't 'this month' by any definition."""
        login_session(client_no_csrf)
        conn, cursor = make_mock_connection()
        wire(cursor)
        app_no_csrf.db_pool.get_connection.return_value = conn

        client_no_csrf.get('/?month=2026-09')

        expense_total = next(c for c in cursor.execute.call_args_list
                             if 'FROM expense' in c[0][0] and 'SUM(amount)' in c[0][0])
        assert 'date BETWEEN' in expense_total[0][0]
        assert date(2026, 9, 1) in expense_total[0][1]
        assert date(2026, 9, 30) in expense_total[0][1]

    def test_daily_series_ordered_by_real_date(self, client_no_csrf, app_no_csrf):
        """It used to ORDER BY DATE_FORMAT(date,'%b %d') -- a string -- so
        'Apr 01' sorted before 'Jan 02'."""
        login_session(client_no_csrf)
        conn, cursor = make_mock_connection()
        wire(cursor)
        app_no_csrf.db_pool.get_connection.return_value = conn

        client_no_csrf.get('/')

        daily = next(c for c in cursor.execute.call_args_list
                     if 'GROUP BY date' in c[0][0])
        assert 'ORDER BY date' in daily[0][0]
        assert "DATE_FORMAT" not in daily[0][0]

    def test_no_income_expense_join(self, client_no_csrf, app_no_csrf):
        """Joining income to expense on user_id alone multiplies every income
        row by every expense row."""
        login_session(client_no_csrf)
        conn, cursor = make_mock_connection()
        wire(cursor)
        app_no_csrf.db_pool.get_connection.return_value = conn

        client_no_csrf.get('/')

        for call in cursor.execute.call_args_list:
            sql = call[0][0].upper()
            assert 'JOIN' not in sql, f"unexpected join: {call[0][0]}"

    def test_bad_month_falls_back(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)
        conn, cursor = make_mock_connection()
        wire(cursor)
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/?month=not-a-month')
        assert response.status_code == 200

    def test_scoped_to_user(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf, user_id=8)
        conn, cursor = make_mock_connection()
        wire(cursor)
        app_no_csrf.db_pool.get_connection.return_value = conn

        client_no_csrf.get('/')
        assert all(8 in c[0][1] for c in cursor.execute.call_args_list if len(c[0]) > 1)


class TestWhereItWent:
    def test_categories_ranked_with_amounts(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)
        conn, cursor = make_mock_connection()
        wire(cursor, month_expense='3000.00', categories=[
            {'category': 'Grocery', 'total': Decimal('2000.00'), 'count': 5},
            {'category': 'Fuel', 'total': Decimal('1000.00'), 'count': 2},
        ])
        app_no_csrf.db_pool.get_connection.return_value = conn

        body = client_no_csrf.get('/').get_data(as_text=True)
        assert 'Where it went' in body
        assert 'Grocery' in body and 'Fuel' in body
        # Amounts are always visible -- the palette's light-mode contrast
        # warning is relieved by labels, not by colour alone.
        assert '2000' in body and '1000' in body
        assert body.index('Grocery') < body.index('Fuel')


class TestWhatChanged:
    def test_movers_sorted_by_absolute_swing(self):
        this = {'Grocery': {'total': 10000.0}, 'Fuel': {'total': 500.0}}
        last = {'Grocery': {'total': 2000.0}, 'Fuel': {'total': 3000.0}}

        movers = _movers(this, last)

        assert movers[0]['category'] == 'Grocery'
        assert movers[0]['change'] == 8000.0
        assert movers[1]['category'] == 'Fuel'
        assert movers[1]['change'] == -2500.0

    def test_unchanged_categories_are_omitted(self):
        this = {'Rent': {'total': 25000.0}, 'Fuel': {'total': 900.0}}
        last = {'Rent': {'total': 25000.0}, 'Fuel': {'total': 500.0}}

        movers = _movers(this, last)
        assert [m['category'] for m in movers] == ['Fuel']

    def test_new_category_flagged_without_percent(self):
        movers = _movers({'Pets': {'total': 1200.0}}, {})
        assert movers[0]['is_new'] is True
        assert movers[0]['percent'] is None  # no division by zero

    def test_stopped_category_flagged(self):
        movers = _movers({}, {'Gym': {'total': 3000.0}})
        assert movers[0]['stopped'] is True
        assert movers[0]['change'] == -3000.0

    def test_percent_computed_against_last_month(self):
        movers = _movers({'Fuel': {'total': 150.0}}, {'Fuel': {'total': 100.0}})
        assert movers[0]['percent'] == 50.0

    def test_rendered_with_direction(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)
        conn, cursor = make_mock_connection()
        wire(cursor,
             categories=[{'category': 'Grocery', 'total': Decimal('9000.00'), 'count': 4}],
             prev_categories=[{'category': 'Grocery', 'total': Decimal('1000.00'), 'count': 2}])
        app_no_csrf.db_pool.get_connection.return_value = conn

        body = client_no_csrf.get('/').get_data(as_text=True)
        assert 'What changed' in body
        assert '8000' in body


class TestWhoSpent:
    def test_per_person_totals_and_top_category(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)
        conn, cursor = make_mock_connection()
        wire(cursor, month_expense='3000.00', people=[
            {'done_by': 'Faisal', 'category': 'Grocery', 'total': Decimal('2000.00'), 'count': 3},
            {'done_by': 'Faisal', 'category': 'Fuel', 'total': Decimal('500.00'), 'count': 1},
            {'done_by': 'Hassan', 'category': 'Bills', 'total': Decimal('500.00'), 'count': 1},
        ])
        app_no_csrf.db_pool.get_connection.return_value = conn

        body = client_no_csrf.get('/').get_data(as_text=True)
        assert 'Who spent' in body
        assert 'Faisal' in body and 'Hassan' in body
        # Faisal's biggest category, not merely his most recent.
        assert 'mostly Grocery' in body
        assert body.index('Faisal') < body.index('Hassan')

    def test_missing_person_labelled(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)
        conn, cursor = make_mock_connection()
        wire(cursor, people=[
            {'done_by': None, 'category': 'Grocery', 'total': Decimal('100.00'), 'count': 1},
        ])
        app_no_csrf.db_pool.get_connection.return_value = conn

        body = client_no_csrf.get('/').get_data(as_text=True)
        assert 'Unknown' in body


class TestEmptyStates:
    def test_handles_no_data(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)
        conn, cursor = make_mock_connection()
        wire(cursor, setting=None, month_expense='0', prev_expense='0',
             month_income='0', count=0, all_income='0', all_expense='0')
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/')
        assert response.status_code == 200
        assert b'Nothing recorded this month' in response.data

    def test_no_previous_month_avoids_divide_by_zero(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)
        conn, cursor = make_mock_connection()
        wire(cursor, prev_expense='0')
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/')
        assert response.status_code == 200
        assert b'to compare' in response.data


class TestRecentEntries:
    def test_shows_latest_expenses(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)
        conn, cursor = make_mock_connection()
        wire(cursor, recent=[
            {'id': 1, 'amount': Decimal('450.00'), 'category': 'Grocery',
             'note': 'Milk', 'date': date(2026, 9, 20), 'done_by': 'Faisal'},
        ])
        app_no_csrf.db_pool.get_connection.return_value = conn

        body = client_no_csrf.get('/').get_data(as_text=True)
        assert 'Latest entries' in body
        assert 'Milk' in body
