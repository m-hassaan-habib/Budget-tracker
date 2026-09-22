"""
Test suite for income routes.
Tests cover Expected Income CRUD and Actual Income display.
"""

import pytest
import os
import sys
from unittest.mock import MagicMock
from decimal import Decimal
from datetime import date

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def make_mock_connection():
    """Create a mock MySQL connection with cursor context manager."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor
    return conn, cursor


def login_session(client, user_id=1, user_name='Test User'):
    """Helper to set up a logged-in session."""
    with client.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['user_name'] = user_name


class TestIncomeAccess:
    """Test income page access control."""

    def test_income_requires_auth(self, client):
        """Income page should require authentication."""
        response = client.get('/income/')
        assert response.status_code in (302, 308)
        assert '/auth/login' in response.headers.get('Location', '')

    def test_income_accessible_when_logged_in(self, client_no_csrf, app_no_csrf):
        """Income page should be accessible for logged-in users."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        # Query order: 1. settings, 2. manual income, 3. automated income
        cursor.fetchone.return_value = {'use_automated_income': 0}  # settings
        cursor.fetchall.side_effect = [
            [{'id': 1, 'source': 'Salary', 'amount': Decimal('5000.00'), 'date': date(2024, 1, 5)}],  # manual income
            [{'done_by': 'Self', 'total': Decimal('3000.00')}],  # automated income
            [],  # month options
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/income/')
        assert response.status_code == 200


class TestIncomeList:
    """Test income listing."""

    def test_income_shows_expected_income(self, client_no_csrf, app_no_csrf):
        """Income page should display manual income sources when toggle is off."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {'use_automated_income': 0}  # manual mode
        cursor.fetchall.side_effect = [
            [
                {'id': 1, 'source': 'Salary', 'amount': Decimal('10000.00'), 'date': date(2024, 1, 5)},
                {'id': 2, 'source': 'Freelance', 'amount': Decimal('5000.00'), 'date': None},
            ],
            [{'done_by': 'Self', 'total': Decimal('8000.00')}],
            [],  # month options
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/income/')
        assert response.status_code == 200
        assert b'Salary' in response.data
        assert b'Freelance' in response.data

    def test_income_shows_actual_income(self, client_no_csrf, app_no_csrf):
        """Income page should display automated income when toggle is on."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {'use_automated_income': 1}  # automated mode
        cursor.fetchall.side_effect = [
            [{'id': 1, 'source': 'Salary', 'amount': Decimal('10000.00'), 'date': date(2024, 1, 5)}],
            [
                {'done_by': 'Person1', 'total': Decimal('4000.00')},
                {'done_by': 'Person2', 'total': Decimal('3000.00')},
            ],
            [],  # month options
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/income/')
        assert response.status_code == 200

    def test_income_calculates_variance(self, client_no_csrf, app_no_csrf):
        """Income page should show both manual and automated income."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {'use_automated_income': 0}
        cursor.fetchall.side_effect = [
            [{'id': 1, 'source': 'Salary', 'amount': Decimal('10000.00'), 'date': date(2024, 1, 5)}],  # manual = 10000
            [{'done_by': 'Self', 'total': Decimal('7000.00')}],  # automated = 7000
            [],  # month options
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/income/')
        assert response.status_code == 200

    def test_income_empty_state(self, client_no_csrf, app_no_csrf):
        """Income page should handle empty income gracefully."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = None  # no settings
        cursor.fetchall.side_effect = [[], [], []]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/income/')
        assert response.status_code == 200


class TestIncomeMonthFilter:
    """The month dropdown scopes manual sources and contributors alike."""

    def _mock_page(self, cursor, months=(('2024-01',),)):
        cursor.fetchone.return_value = {'use_automated_income': 1}
        cursor.fetchall.side_effect = [[], [], [{'m': m} for (m,) in months]]

    def test_month_narrows_both_halves(self, client_no_csrf, app_no_csrf):
        """Manual income and the contributor split are both date-bounded."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        self._mock_page(cursor)
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/income/?month=2024-01')
        assert response.status_code == 200

        bounded = [c for c in cursor.execute.call_args_list if 'date BETWEEN' in c.args[0]]
        assert len(bounded) == 2, "manual income and automated income must both be scoped"
        assert any('FROM income' in c.args[0] for c in bounded)
        assert any('FROM expense' in c.args[0] for c in bounded)
        for call in bounded:
            assert call.args[1][-2:] == (date(2024, 1, 1), date(2024, 1, 31))

    def test_no_month_leaves_queries_unbounded(self, client_no_csrf, app_no_csrf):
        """Without ?month=, the page still totals everything."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        self._mock_page(cursor)
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/income/')
        assert response.status_code == 200
        assert not any('date BETWEEN' in c.args[0] for c in cursor.execute.call_args_list)

    def test_junk_month_is_ignored(self, client_no_csrf, app_no_csrf):
        """A garbage ?month= must fall back to all months, not error."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        self._mock_page(cursor)
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/income/?month=2024-13')
        assert response.status_code == 200
        assert not any('date BETWEEN' in c.args[0] for c in cursor.execute.call_args_list)

    def test_dropdown_offers_the_selected_month(self, client_no_csrf, app_no_csrf):
        """An empty month stays selectable so the user can navigate back out."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        self._mock_page(cursor, months=(('2024-03',),))
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/income/?month=2024-01')
        assert response.status_code == 200
        assert b'January 2024' in response.data
        assert b'March 2024' in response.data


class TestAddIncome:
    """Test adding expected income."""

    def test_add_income_page_renders(self, client_no_csrf, app_no_csrf):
        """Add income page should render."""
        login_session(client_no_csrf)
        response = client_no_csrf.get('/income/add')
        assert response.status_code == 200

    def test_add_income_valid(self, client_no_csrf, app_no_csrf):
        """Valid income should be added successfully."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/income/add', data={
            'source': 'Bonus',
            'amount': '2500.00',
            'date': '2024-01-15',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/income' in response.headers.get('Location', '')
        cursor.execute.assert_called()
        conn.commit.assert_called()

        insert = cursor.execute.call_args_list[0]
        assert 'date' in insert.args[0]
        assert '2024-01-15' in insert.args[1]

    def test_add_income_requires_a_date(self, client_no_csrf, app_no_csrf):
        """An undated source would vanish from every month filter."""
        login_session(client_no_csrf)

        response = client_no_csrf.post('/income/add', data={
            'source': 'Bonus',
            'amount': '2500.00',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/income/add' in response.headers.get('Location', '')

    def test_add_income_rejects_a_bad_date(self, client_no_csrf, app_no_csrf):
        """A malformed date should be rejected, not stored."""
        login_session(client_no_csrf)

        response = client_no_csrf.post('/income/add', data={
            'source': 'Bonus',
            'amount': '2500.00',
            'date': '15/01/2024',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/income/add' in response.headers.get('Location', '')

    def test_add_income_negative_amount_rejected(self, client_no_csrf, app_no_csrf):
        """Negative amount should be rejected."""
        login_session(client_no_csrf)

        response = client_no_csrf.post('/income/add', data={
            'source': 'Salary',
            'amount': '-500',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/income/add' in response.headers.get('Location', '')

    def test_add_income_non_numeric_rejected(self, client_no_csrf, app_no_csrf):
        """Non-numeric amount should be rejected."""
        login_session(client_no_csrf)

        response = client_no_csrf.post('/income/add', data={
            'source': 'Salary',
            'amount': 'abc',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/income/add' in response.headers.get('Location', '')

    def test_add_income_source_too_long_rejected(self, client_no_csrf, app_no_csrf):
        """Source > 100 chars should be rejected."""
        login_session(client_no_csrf)

        response = client_no_csrf.post('/income/add', data={
            'source': 'X' * 101,
            'amount': '5000',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/income/add' in response.headers.get('Location', '')

    def test_add_income_empty_source_rejected(self, client_no_csrf, app_no_csrf):
        """Empty source should be rejected."""
        login_session(client_no_csrf)

        response = client_no_csrf.post('/income/add', data={
            'source': '',
            'amount': '5000',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/income/add' in response.headers.get('Location', '')

    def test_add_income_amount_too_large_rejected(self, client_no_csrf, app_no_csrf):
        """Amount > 99999999.99 should be rejected."""
        login_session(client_no_csrf)

        response = client_no_csrf.post('/income/add', data={
            'source': 'Huge Income',
            'amount': '100000000.00',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/income/add' in response.headers.get('Location', '')


class TestEditIncome:
    """Test editing expected income."""

    def test_edit_income_page_renders(self, client_no_csrf, app_no_csrf):
        """Edit income page should render for existing income."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {
            'id': 1,
            'source': 'Salary',
            'amount': Decimal('10000.00'),
            'date': date(2024, 1, 5),
        }
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/income/edit/1')
        assert response.status_code == 200

    def test_edit_income_not_found(self, client_no_csrf, app_no_csrf):
        """Edit income should return 404 for non-existent income."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = None
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/income/edit/999')
        assert response.status_code == 404

    def test_edit_income_valid(self, client_no_csrf, app_no_csrf):
        """Valid edit should update income."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {
            'id': 1,
            'source': 'Salary',
            'amount': Decimal('10000.00'),
            'date': date(2024, 1, 5),
        }
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/income/edit/1', data={
            'source': 'Updated Salary',
            'amount': '12000.00',
            'date': '2024-02-01',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/income' in response.headers.get('Location', '')

        update = next(c for c in cursor.execute.call_args_list if 'UPDATE income' in c.args[0])
        assert 'date=%s' in update.args[0]
        assert '2024-02-01' in update.args[1]

    def test_edit_income_requires_a_date(self, client_no_csrf, app_no_csrf):
        """Clearing the date would drop the row out of every month filter."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {
            'id': 1,
            'source': 'Salary',
            'amount': Decimal('10000.00'),
            'date': date(2024, 1, 5),
        }
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/income/edit/1', data={
            'source': 'Updated Salary',
            'amount': '12000.00',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/income/edit/1' in response.headers.get('Location', '')

    def test_edit_income_invalid_amount_rejected(self, client_no_csrf, app_no_csrf):
        """Invalid amount should be rejected on edit."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {
            'id': 1,
            'source': 'Salary',
            'amount': Decimal('10000.00'),
            'date': date(2024, 1, 5),
        }
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/income/edit/1', data={
            'source': 'Salary',
            'amount': '-500',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/income/edit/1' in response.headers.get('Location', '')


class TestDeleteIncome:
    """Test deleting expected income."""

    def test_delete_income_via_post(self, client_no_csrf, app_no_csrf):
        """Delete income via POST should work."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/income/delete/1', follow_redirects=False)
        assert response.status_code == 302
        assert '/income' in response.headers.get('Location', '')

    def test_delete_income_via_get_rejected(self, client):
        """Delete income via GET should be rejected (405)."""
        login_session(client)
        response = client.get('/income/delete/1')
        assert response.status_code == 405

    def test_delete_income_respects_user_ownership(self, client_no_csrf, app_no_csrf):
        """Delete should only affect current user's income."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        app_no_csrf.db_pool.get_connection.return_value = conn

        client_no_csrf.post('/income/delete/1')

        # Verify user_id is included in DELETE query
        calls = cursor.execute.call_args_list
        assert any('user_id' in str(call) for call in calls)


class TestIncomeCSRF:
    """Test CSRF protection for income endpoints."""

    def test_add_income_without_csrf_rejected(self, client, app):
        """POST to add income without CSRF token should be rejected."""
        login_session(client)
        response = client.post('/income/add', data={
            'source': 'Salary',
            'amount': '5000'
        })
        assert response.status_code == 400

    def test_delete_income_without_csrf_rejected(self, client, app):
        """POST to delete income without CSRF token should be rejected."""
        login_session(client)
        response = client.post('/income/delete/1')
        assert response.status_code == 400
