"""
Test suite for settings routes.
Tests cover settings update, end-month archive, and fresh start.
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


class TestSettingsAccess:
    """Test settings page access control."""

    def test_settings_requires_auth(self, client):
        """Settings page should require authentication."""
        response = client.get('/settings/')
        assert response.status_code in (302, 308)
        assert '/auth/login' in response.headers.get('Location', '')

    def test_settings_accessible_when_logged_in(self, client_no_csrf, app_no_csrf):
        """Settings page should be accessible for logged-in users."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        # New query order: settings, manual income, expenses, automated income, archived months
        cursor.fetchone.side_effect = [
            {'monthly_limit': Decimal('10000.00'), 'total_savings': Decimal('5000.00'), 'default_done_by': 'Self', 'use_automated_income': 0},
            {'total': Decimal('8000.00'), 'count': 3},  # manual income
            {'total': Decimal('5000.00'), 'count': 10},  # expenses
            {'cnt': 2},  # archived months
        ]
        cursor.fetchall.side_effect = [
            [{'done_by': 'Self', 'total': Decimal('5000.00')}],  # automated income
            [],  # available months
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/settings/')
        assert response.status_code == 200


class TestSettingsDisplay:
    """Test settings page display."""

    def test_settings_shows_expected_income(self, client_no_csrf, app_no_csrf):
        """Settings should display manual income in snapshot when toggle is off."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.side_effect = [
            {'monthly_limit': Decimal('10000.00'), 'total_savings': Decimal('5000.00'), 'default_done_by': 'Self', 'use_automated_income': 0},
            {'total': Decimal('15000.00'), 'count': 2},  # manual income
            {'total': Decimal('8000.00'), 'count': 15},  # expenses
            {'cnt': 3},
        ]
        cursor.fetchall.side_effect = [
            [{'done_by': 'Self', 'total': Decimal('8000.00')}],  # automated income
            [],  # available months
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/settings/')
        assert response.status_code == 200

    def test_settings_shows_actual_income(self, client_no_csrf, app_no_csrf):
        """Settings should display automated income in snapshot when toggle is on."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.side_effect = [
            {'monthly_limit': Decimal('10000.00'), 'total_savings': Decimal('5000.00'), 'default_done_by': 'Self', 'use_automated_income': 1},
            {'total': Decimal('15000.00'), 'count': 2},  # manual income
            {'total': Decimal('8000.00'), 'count': 15},  # expenses
            {'cnt': 3},
        ]
        cursor.fetchall.side_effect = [
            [
                {'done_by': 'Person1', 'total': Decimal('4000.00')},
                {'done_by': 'Person2', 'total': Decimal('4000.00')},
            ],  # automated income = 8000
            [],  # available months
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/settings/')
        assert response.status_code == 200

    def test_settings_handles_no_settings(self, client_no_csrf, app_no_csrf):
        """Settings should handle missing settings gracefully."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.side_effect = [
            None,  # no settings
            {'total': Decimal('0'), 'count': 0},
            {'total': Decimal('0'), 'count': 0},
            {'cnt': 0},
        ]
        cursor.fetchall.return_value = []
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/settings/')
        assert response.status_code == 200


class TestUpdateSettings:
    """Test settings update."""

    def test_update_settings_valid(self, client_no_csrf, app_no_csrf):
        """Valid settings update should work."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {'id': 1}  # existing settings
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/settings/update', data={
            'limit': '15000',
            'savings': '8000',
            'default_done_by': 'Self',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/settings' in response.headers.get('Location', '')

    def test_update_settings_creates_new(self, client_no_csrf, app_no_csrf):
        """Settings update should create new if none exist."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = None  # no existing settings
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/settings/update', data={
            'limit': '10000',
            'savings': '5000',
            'default_done_by': 'Self',
        }, follow_redirects=False)

        assert response.status_code == 302

    def test_update_settings_invalid_limit_rejected(self, client_no_csrf, app_no_csrf):
        """Non-numeric limit should be rejected."""
        login_session(client_no_csrf)

        response = client_no_csrf.post('/settings/update', data={
            'limit': 'abc',
            'savings': '1000',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/settings' in response.headers.get('Location', '')

    def test_update_settings_invalid_savings_rejected(self, client_no_csrf, app_no_csrf):
        """Non-numeric savings should be rejected."""
        login_session(client_no_csrf)

        response = client_no_csrf.post('/settings/update', data={
            'limit': '10000',
            'savings': 'xyz',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/settings' in response.headers.get('Location', '')

    def test_update_settings_negative_limit_rejected(self, client_no_csrf, app_no_csrf):
        """Negative limit should be rejected."""
        login_session(client_no_csrf)

        response = client_no_csrf.post('/settings/update', data={
            'limit': '-5000',
            'savings': '1000',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/settings' in response.headers.get('Location', '')

    def test_update_settings_done_by_too_long_rejected(self, client_no_csrf, app_no_csrf):
        """Default done_by > 50 chars should be rejected."""
        login_session(client_no_csrf)

        response = client_no_csrf.post('/settings/update', data={
            'limit': '10000',
            'savings': '1000',
            'default_done_by': 'X' * 51,
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/settings' in response.headers.get('Location', '')


class TestMonthRollover:
    """End Month is gone: months are derived from each entry's date."""

    def test_end_month_route_removed(self, client_no_csrf):
        """Forgetting to click a button can no longer misfile a month."""
        login_session(client_no_csrf)
        response = client_no_csrf.post('/settings/end-month')
        assert response.status_code == 404

    def test_settings_page_explains_rollover(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.side_effect = [
            {'monthly_limit': Decimal('50000.00'), 'total_savings': Decimal('10000.00'),
             'default_done_by': 'Self', 'use_automated_income': 0},
            {'total': Decimal('10000.00'), 'count': 1},
            {'total': Decimal('5000.00'), 'count': 2},
        ]
        cursor.fetchall.side_effect = [[{'done_by': 'Self', 'total': Decimal('5000.00')}], []]
        app_no_csrf.db_pool.get_connection.return_value = conn

        body = client_no_csrf.get('/settings/').get_data(as_text=True)
        assert 'Months look after themselves' in body
        assert 'end-month' not in body


class TestFreshStart:
    """Test fresh start (delete all) functionality."""

    def test_fresh_start_deletes_all(self, client_no_csrf, app_no_csrf):
        """Fresh start should delete all user data."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/settings/fresh-start', follow_redirects=False)
        assert response.status_code == 302
        assert '/settings' in response.headers.get('Location', '')

        # Verify all DELETE queries
        calls = [str(call) for call in cursor.execute.call_args_list]
        assert any('DELETE FROM archived_income' in call for call in calls)
        assert any('DELETE FROM archived_expense' in call for call in calls)
        assert any('DELETE FROM income' in call for call in calls)
        assert any('DELETE FROM expense' in call for call in calls)
        assert any('DELETE FROM setting' in call for call in calls)


class TestSettingsCSRF:
    """Test CSRF protection for settings endpoints."""

    def test_update_settings_without_csrf_rejected(self, client, app):
        """POST to update settings without CSRF should be rejected."""
        login_session(client)
        response = client.post('/settings/update', data={
            'limit': '5000',
            'savings': '1000',
        })
        assert response.status_code == 400


    def test_fresh_start_without_csrf_rejected(self, client, app):
        """POST to fresh start without CSRF should be rejected."""
        login_session(client)
        response = client.post('/settings/fresh-start')
        assert response.status_code == 400
