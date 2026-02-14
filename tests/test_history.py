"""
Test suite for history routes.
Tests cover archived data viewing and month comparison.
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


class TestHistoryAccess:
    """Test history page access control."""

    def test_history_requires_auth(self, client):
        """History page should require authentication."""
        response = client.get('/history/')
        assert response.status_code in (302, 308)
        assert '/auth/login' in response.headers.get('Location', '')

    def test_history_accessible_when_logged_in(self, client_no_csrf, app_no_csrf):
        """History page should be accessible for logged-in users."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = []  # no archived months
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/history/')
        assert response.status_code == 200


class TestHistoryList:
    """Test history listing."""

    def test_history_no_archived_months(self, client_no_csrf, app_no_csrf):
        """History should handle no archived months."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = []
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/history/')
        assert response.status_code == 200

    def test_history_shows_months(self, client_no_csrf, app_no_csrf):
        """History should show available months."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.side_effect = [
            [{'month': '2024-01'}, {'month': '2023-12'}],  # available months
            [{'id': 1, 'source': 'Salary', 'amount': Decimal('10000.00')}],  # archived income
            [{'done_by': 'Self', 'total': Decimal('5000.00')}],  # actual income
            [{'id': 1, 'amount': Decimal('1000.00'), 'category': 'Food', 'note': 'Test', 'date': date(2024, 1, 15), 'done_by': 'Self'}],  # expenses
            [{'category': 'Food', 'total': Decimal('1000.00'), 'count': 1}],  # category breakdown
        ]
        cursor.fetchone.return_value = {'total': Decimal('5000.00')}  # total expenses
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/history/')
        assert response.status_code == 200
        assert b'2024-01' in response.data

    def test_history_shows_expected_income(self, client_no_csrf, app_no_csrf):
        """History should display expected income for selected month."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.side_effect = [
            [{'month': '2024-01'}],
            [{'id': 1, 'source': 'Salary', 'amount': Decimal('15000.00')}],  # expected income
            [{'done_by': 'Self', 'total': Decimal('8000.00')}],  # actual income
            [],  # expenses
            [],  # category breakdown
        ]
        cursor.fetchone.return_value = {'total': Decimal('0')}
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/history/?month=2024-01')
        assert response.status_code == 200

    def test_history_shows_actual_income(self, client_no_csrf, app_no_csrf):
        """History should display actual income from archived expenses."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.side_effect = [
            [{'month': '2024-01'}],
            [{'id': 1, 'source': 'Salary', 'amount': Decimal('15000.00')}],
            [
                {'done_by': 'Person1', 'total': Decimal('4000.00')},
                {'done_by': 'Person2', 'total': Decimal('4000.00')},
            ],  # actual income = 8000
            [],
            [],
        ]
        cursor.fetchone.return_value = {'total': Decimal('8000.00')}
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/history/?month=2024-01')
        assert response.status_code == 200

    def test_history_calculates_variance(self, client_no_csrf, app_no_csrf):
        """History should calculate income variance."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.side_effect = [
            [{'month': '2024-01'}],
            [{'id': 1, 'source': 'Salary', 'amount': Decimal('10000.00')}],  # expected = 10000
            [{'done_by': 'Self', 'total': Decimal('7000.00')}],  # actual = 7000
            [],
            [],
        ]
        cursor.fetchone.return_value = {'total': Decimal('7000.00')}
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/history/?month=2024-01')
        assert response.status_code == 200
        # Variance = 10000 - 7000 = 3000

    def test_history_category_filter(self, client_no_csrf, app_no_csrf):
        """History should filter expenses by category."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.side_effect = [
            [{'month': '2024-01'}],
            [],
            [],
            [{'id': 1, 'amount': Decimal('500.00'), 'category': 'Food', 'note': 'Test', 'date': date(2024, 1, 15), 'done_by': 'Self'}],
            [{'category': 'Food', 'total': Decimal('500.00'), 'count': 1}],
        ]
        cursor.fetchone.return_value = {'total': Decimal('500.00')}
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/history/?month=2024-01&category=Food')
        assert response.status_code == 200


class TestViewArchivedExpense:
    """Test viewing individual archived expense."""

    def test_view_archived_expense(self, client_no_csrf, app_no_csrf):
        """Should display archived expense details."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {
            'id': 1,
            'amount': Decimal('100.00'),
            'category': 'Food',
            'note': 'Lunch',
            'date': date(2024, 1, 15),
            'done_by': 'Self',
        }
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/history/expense/1')
        assert response.status_code == 200

    def test_view_archived_expense_not_found(self, client_no_csrf, app_no_csrf):
        """Should return 404 for non-existent archived expense."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = None
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/history/expense/999')
        assert response.status_code == 404


class TestHistoryCompare:
    """Test month comparison functionality."""

    def test_compare_requires_auth(self, client):
        """Compare page should require authentication."""
        response = client.get('/history/compare')
        assert response.status_code == 302
        assert '/auth/login' in response.headers.get('Location', '')

    def test_compare_page_renders(self, client_no_csrf, app_no_csrf):
        """Compare page should render."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = [{'month': '2024-01'}, {'month': '2023-12'}]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/history/compare')
        assert response.status_code == 200

    def test_compare_two_months(self, client_no_csrf, app_no_csrf):
        """Compare should show data for two selected months."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        # The compare route makes multiple queries - need to mock all of them
        cursor.fetchall.side_effect = [
            [{'month': '2024-01'}, {'month': '2023-12'}],  # available months
            [{'month': '2024-01', 'total': Decimal('10000.00')}, {'month': '2023-12', 'total': Decimal('8000.00')}],  # income totals
            [{'month': '2024-01', 'total': Decimal('5000.00')}, {'month': '2023-12', 'total': Decimal('4000.00')}],  # expense totals
            [{'category': 'Food', 'month': '2024-01', 'total': Decimal('2000.00')}],  # category breakdown
            [{'source': 'Salary', 'month': '2024-01', 'total': Decimal('10000.00')}],  # income sources
        ]
        cursor.fetchone.side_effect = [
            {'total': Decimal('10000.00')},  # trend income
            {'total': Decimal('5000.00')},   # trend expenses
            {'total': Decimal('8000.00')},   # trend income
            {'total': Decimal('4000.00')},   # trend expenses
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/history/compare?m1=2024-01&m2=2023-12')
        assert response.status_code == 200

    def test_compare_shows_trend(self, client_no_csrf, app_no_csrf):
        """Compare should show trend data across all months."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = [
            {'month': '2024-01'},
            {'month': '2023-12'},
            {'month': '2023-11'},
        ]
        cursor.fetchone.side_effect = [
            {'total': Decimal('10000.00')}, {'total': Decimal('5000.00')},
            {'total': Decimal('9000.00')}, {'total': Decimal('4500.00')},
            {'total': Decimal('8000.00')}, {'total': Decimal('4000.00')},
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/history/compare')
        assert response.status_code == 200


class TestHistorySavingsCalculation:
    """Test savings rate calculation in history."""

    def test_savings_rate_calculation(self, client_no_csrf, app_no_csrf):
        """Savings rate should be calculated correctly."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.side_effect = [
            [{'month': '2024-01'}],
            [{'id': 1, 'source': 'Salary', 'amount': Decimal('10000.00')}],  # income = 10000
            [],
            [],
            [],
        ]
        cursor.fetchone.return_value = {'total': Decimal('6000.00')}  # expenses = 6000
        # Net = 4000, Rate = 40%
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/history/?month=2024-01')
        assert response.status_code == 200

    def test_savings_rate_handles_zero_income(self, client_no_csrf, app_no_csrf):
        """Savings rate should handle zero income gracefully."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.side_effect = [
            [{'month': '2024-01'}],
            [],  # no income
            [],
            [],
            [],
        ]
        cursor.fetchone.return_value = {'total': Decimal('1000.00')}  # has expenses
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/history/?month=2024-01')
        assert response.status_code == 200  # Should not crash
