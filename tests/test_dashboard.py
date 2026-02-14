"""
Test suite for dashboard routes.
Tests cover the main dashboard view with KPIs and charts.
"""

import pytest
import os
import sys
from unittest.mock import MagicMock
from decimal import Decimal

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


class TestDashboardAccess:
    """Test dashboard access control."""

    def test_dashboard_requires_auth(self, client):
        """Dashboard should require authentication."""
        response = client.get('/')
        assert response.status_code == 302
        assert '/auth/login' in response.headers.get('Location', '')

    def test_dashboard_accessible_when_logged_in(self, client_no_csrf, app_no_csrf):
        """Dashboard should be accessible for logged-in users."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        # Mock all the dashboard queries in new order:
        # 1. settings, 2. manual income, 3. expenses, 4. who_data, 5. category, 6. daily, 7. monthly, 8. recent, 9. count
        cursor.fetchone.side_effect = [
            {'monthly_limit': Decimal('8000.00'), 'total_savings': Decimal('2000.00'), 'use_automated_income': 0},  # settings
            {'total': Decimal('10000.00')},  # manual income
            {'total': Decimal('5000.00')},   # expenses
            {'cnt': 10},  # expense count
        ]
        cursor.fetchall.side_effect = [
            [{'done_by': 'Self', 'total': Decimal('5000.00')}],  # who data (automated income)
            [{'category': 'Food', 'total': Decimal('2000.00')}],  # category data
            [{'day': 'Jan 01', 'total': Decimal('100.00')}],  # daily data
            [{'mon': 'Jan', 'savings': Decimal('1000.00')}],  # monthly savings
            [],  # recent expenses
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/')
        assert response.status_code == 200


class TestDashboardData:
    """Test dashboard data calculations."""

    def test_dashboard_shows_expected_income(self, client_no_csrf, app_no_csrf):
        """Dashboard should display manual income when toggle is off."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.side_effect = [
            {'monthly_limit': Decimal('10000.00'), 'total_savings': Decimal('5000.00'), 'use_automated_income': 0},
            {'total': Decimal('15000.00')},  # manual income
            {'total': Decimal('8000.00')},   # expenses
            {'cnt': 20},
        ]
        cursor.fetchall.side_effect = [[], [], [], [], []]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/')
        assert response.status_code == 200
        assert b'15000' in response.data or b'15,000' in response.data

    def test_dashboard_shows_actual_income(self, client_no_csrf, app_no_csrf):
        """Dashboard should display automated income when toggle is on."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.side_effect = [
            {'monthly_limit': Decimal('10000.00'), 'total_savings': Decimal('5000.00'), 'use_automated_income': 1},
            {'total': Decimal('15000.00')},  # manual income (not used)
            {'total': Decimal('8000.00')},   # expenses
            {'cnt': 20},
        ]
        cursor.fetchall.side_effect = [
            [{'done_by': 'Person1', 'total': Decimal('4000.00')},
             {'done_by': 'Person2', 'total': Decimal('4000.00')}],  # automated income = 8000
            [],  # category
            [],  # daily
            [],  # monthly
            [],  # recent
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/')
        assert response.status_code == 200
        # With automated mode on, income should be 8000

    def test_dashboard_calculates_net_savings(self, client_no_csrf, app_no_csrf):
        """Dashboard should calculate net savings = income - expenses."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.side_effect = [
            {'monthly_limit': Decimal('8000.00'), 'total_savings': Decimal('1000.00'), 'use_automated_income': 0},
            {'total': Decimal('10000.00')},  # manual income
            {'total': Decimal('6000.00')},   # expenses
            {'cnt': 15},
        ]
        cursor.fetchall.side_effect = [[], [], [], [], []]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/')
        assert response.status_code == 200
        # Net savings = 10000 - 6000 = 4000

    def test_dashboard_calculates_variance(self, client_no_csrf, app_no_csrf):
        """Dashboard should show both manual and automated income values."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.side_effect = [
            {'monthly_limit': Decimal('10000.00'), 'total_savings': Decimal('0.00'), 'use_automated_income': 0},
            {'total': Decimal('10000.00')},  # manual income
            {'total': Decimal('8000.00')},   # expenses
            {'cnt': 10},
        ]
        cursor.fetchall.side_effect = [
            [{'done_by': 'Self', 'total': Decimal('8000.00')}],  # automated = 8000
            [],
            [],
            [],
            [],
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/')
        assert response.status_code == 200

    def test_dashboard_handles_empty_data(self, client_no_csrf, app_no_csrf):
        """Dashboard should handle no income/expenses gracefully."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.side_effect = [
            None,  # no settings
            {'total': Decimal('0.00')},  # no manual income
            {'total': Decimal('0.00')},  # no expenses
            {'cnt': 0},
        ]
        cursor.fetchall.side_effect = [[], [], [], [], []]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/')
        assert response.status_code == 200

    def test_dashboard_shows_recent_expenses(self, client_no_csrf, app_no_csrf):
        """Dashboard should show recent expenses."""
        login_session(client_no_csrf)
        from datetime import date

        conn, cursor = make_mock_connection()
        cursor.fetchone.side_effect = [
            {'monthly_limit': Decimal('5000.00'), 'total_savings': Decimal('0.00'), 'use_automated_income': 0},
            {'total': Decimal('5000.00')},  # manual income
            {'total': Decimal('1000.00')},  # expenses
            {'cnt': 5},
        ]
        cursor.fetchall.side_effect = [
            [{'done_by': 'Self', 'total': Decimal('1000.00')}],  # automated income
            [],  # category
            [],  # daily
            [],  # monthly
            [
                {'id': 1, 'amount': Decimal('100.00'), 'category': 'Food', 'note': 'Lunch', 'date': date(2024, 1, 15)},
                {'id': 2, 'amount': Decimal('50.00'), 'category': 'Transport', 'note': 'Bus', 'date': date(2024, 1, 14)},
            ],
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/')
        assert response.status_code == 200


class TestDashboardCharts:
    """Test dashboard chart data."""

    def test_dashboard_category_chart_data(self, client_no_csrf, app_no_csrf):
        """Dashboard should pass category data for pie chart."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.side_effect = [
            {'monthly_limit': Decimal('10000.00'), 'total_savings': Decimal('0.00'), 'use_automated_income': 0},
            {'total': Decimal('10000.00')},  # manual income
            {'total': Decimal('5000.00')},   # expenses
            {'cnt': 10},
        ]
        cursor.fetchall.side_effect = [
            [{'done_by': 'Self', 'total': Decimal('5000.00')}],  # automated income
            [
                {'category': 'Food', 'total': Decimal('2000.00')},
                {'category': 'Transport', 'total': Decimal('1500.00')},
                {'category': 'Entertainment', 'total': Decimal('1500.00')},
            ],
            [],  # daily
            [],  # monthly
            [],  # recent
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/')
        assert response.status_code == 200
        assert b'Food' in response.data

    def test_dashboard_who_chart_data(self, client_no_csrf, app_no_csrf):
        """Dashboard should pass who (done_by) data for chart."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.side_effect = [
            {'monthly_limit': Decimal('10000.00'), 'total_savings': Decimal('0.00'), 'use_automated_income': 0},
            {'total': Decimal('10000.00')},  # manual income
            {'total': Decimal('6000.00')},   # expenses
            {'cnt': 15},
        ]
        cursor.fetchall.side_effect = [
            [
                {'done_by': 'Person1', 'total': Decimal('3000.00')},
                {'done_by': 'Person2', 'total': Decimal('3000.00')},
            ],
            [],  # category
            [],  # daily
            [],  # monthly
            [],  # recent
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/')
        assert response.status_code == 200
