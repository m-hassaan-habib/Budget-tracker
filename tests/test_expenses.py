"""
Test suite for expense routes.
Tests cover expense CRUD operations and file attachments.
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


class TestExpenseAccess:
    """Test expense page access control."""

    def test_expense_requires_auth(self, client):
        """Expense page should require authentication."""
        response = client.get('/expenses/')
        assert response.status_code in (302, 308)
        assert '/auth/login' in response.headers.get('Location', '')

    def test_expense_accessible_when_logged_in(self, client_no_csrf, app_no_csrf):
        """Expense page should be accessible for logged-in users."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.side_effect = [
            [],  # expenses
            [],  # categories
            [],  # persons
        ]
        cursor.fetchone.side_effect = [
            {'total': Decimal('0'), 'count': 0},  # summary
            {'default_done_by': 'Self'},  # default done_by
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/expenses/')
        assert response.status_code == 200


class TestExpenseList:
    """Test expense listing and filtering."""

    def test_expense_list_shows_expenses(self, client_no_csrf, app_no_csrf):
        """Expense list should display expenses."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.side_effect = [
            [
                {'id': 1, 'amount': Decimal('100.00'), 'category': 'Food', 'note': 'Lunch', 'date': date(2024, 1, 15), 'attachment': None, 'done_by': 'Self'},
                {'id': 2, 'amount': Decimal('50.00'), 'category': 'Transport', 'note': 'Bus', 'date': date(2024, 1, 14), 'attachment': None, 'done_by': 'Self'},
            ],
            [{'category': 'Food', 'total': Decimal('100.00'), 'count': 1}],
            [{'done_by': 'Self'}],
        ]
        cursor.fetchone.side_effect = [
            {'total': Decimal('150.00'), 'count': 2},
            {'default_done_by': 'Self'},
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/expenses/')
        assert response.status_code == 200
        assert b'Food' in response.data

    def test_expense_list_category_filter(self, client_no_csrf, app_no_csrf):
        """Expense list should filter by category."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.side_effect = [
            [{'id': 1, 'amount': Decimal('100.00'), 'category': 'Food', 'note': 'Lunch', 'date': date(2024, 1, 15), 'attachment': None, 'done_by': 'Self'}],
            [{'category': 'Food', 'total': Decimal('100.00'), 'count': 1}],
            [{'done_by': 'Self'}],
        ]
        cursor.fetchone.side_effect = [
            {'total': Decimal('100.00'), 'count': 1},
            {'default_done_by': 'Self'},
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/expenses/?category=Food')
        assert response.status_code == 200

    def test_expense_list_person_filter(self, client_no_csrf, app_no_csrf):
        """Expense list should filter by person (done_by)."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.side_effect = [[], [], []]
        cursor.fetchone.side_effect = [
            {'total': Decimal('0'), 'count': 0},
            {'default_done_by': 'Self'},
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/expenses/?person=Self')
        assert response.status_code == 200


class TestAddExpense:
    """Test adding expenses."""

    def test_add_expense_page_renders(self, client_no_csrf, app_no_csrf):
        """Add expense page should render."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {'default_done_by': 'Self'}
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/expenses/add')
        assert response.status_code == 200

    def test_add_expense_valid(self, client_no_csrf, app_no_csrf):
        """Valid expense should be added."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/expenses/add', data={
            'amount': '75.50',
            'category': 'Food',
            'note': 'Dinner',
            'date': '2024-01-15',
            'done_by': 'Self',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/expenses' in response.headers.get('Location', '')

    def test_add_expense_negative_amount_rejected(self, client_no_csrf, app_no_csrf):
        """Negative amount should be rejected."""
        login_session(client_no_csrf)

        response = client_no_csrf.post('/expenses/add', data={
            'amount': '-100',
            'category': 'Food',
            'date': '2024-01-01',
            'done_by': 'Self',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/expenses/add' in response.headers.get('Location', '')

    def test_add_expense_invalid_date_rejected(self, client_no_csrf, app_no_csrf):
        """Invalid date should be rejected."""
        login_session(client_no_csrf)

        response = client_no_csrf.post('/expenses/add', data={
            'amount': '100',
            'category': 'Food',
            'date': 'not-a-date',
            'done_by': 'Self',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/expenses/add' in response.headers.get('Location', '')

    def test_add_expense_missing_category_rejected(self, client_no_csrf, app_no_csrf):
        """Missing category should be rejected."""
        login_session(client_no_csrf)

        response = client_no_csrf.post('/expenses/add', data={
            'amount': '100',
            'category': '',
            'date': '2024-01-01',
            'done_by': 'Self',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/expenses/add' in response.headers.get('Location', '')

    def test_add_expense_missing_done_by_rejected(self, client_no_csrf, app_no_csrf):
        """Missing done_by should be rejected."""
        login_session(client_no_csrf)

        response = client_no_csrf.post('/expenses/add', data={
            'amount': '100',
            'category': 'Food',
            'date': '2024-01-01',
            'done_by': '',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/expenses/add' in response.headers.get('Location', '')

    def test_add_expense_category_too_long_rejected(self, client_no_csrf, app_no_csrf):
        """Category > 50 chars should be rejected."""
        login_session(client_no_csrf)

        response = client_no_csrf.post('/expenses/add', data={
            'amount': '100',
            'category': 'X' * 51,
            'date': '2024-01-01',
            'done_by': 'Self',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/expenses/add' in response.headers.get('Location', '')

    def test_add_expense_note_too_long_rejected(self, client_no_csrf, app_no_csrf):
        """Note > 1000 chars should be rejected."""
        login_session(client_no_csrf)

        response = client_no_csrf.post('/expenses/add', data={
            'amount': '100',
            'category': 'Food',
            'date': '2024-01-01',
            'done_by': 'Self',
            'note': 'X' * 1001,
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/expenses/add' in response.headers.get('Location', '')


class TestEditExpense:
    """Test editing expenses."""

    def test_edit_expense_page_renders(self, client_no_csrf, app_no_csrf):
        """Edit expense page should render."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {
            'id': 1,
            'amount': Decimal('100.00'),
            'category': 'Food',
            'note': 'Lunch',
            'date': date(2024, 1, 15),
            'attachment': None,
            'done_by': 'Self',
        }
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/expenses/edit/1')
        assert response.status_code == 200

    def test_edit_expense_not_found(self, client_no_csrf, app_no_csrf):
        """Edit non-existent expense should return 404."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = None
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/expenses/edit/999')
        assert response.status_code == 404

    def test_edit_expense_valid(self, client_no_csrf, app_no_csrf):
        """Valid edit should update expense."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {
            'id': 1,
            'amount': Decimal('100.00'),
            'category': 'Food',
            'note': 'Lunch',
            'date': date(2024, 1, 15),
            'attachment': None,
            'done_by': 'Self',
        }
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/expenses/edit/1', data={
            'amount': '150.00',
            'category': 'Food',
            'note': 'Dinner',
            'date': '2024-01-15',
            'done_by': 'Self',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/expenses' in response.headers.get('Location', '')


class TestDeleteExpense:
    """Test deleting expenses."""

    def test_delete_expense_via_post(self, client_no_csrf, app_no_csrf):
        """Delete expense via POST should work."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/expenses/delete/1', follow_redirects=False)
        assert response.status_code == 302
        assert '/expenses' in response.headers.get('Location', '')

    def test_delete_expense_via_get_rejected(self, client):
        """Delete expense via GET should be rejected (405)."""
        login_session(client)
        response = client.get('/expenses/delete/1')
        assert response.status_code == 405


class TestViewExpense:
    """Test viewing single expense."""

    def test_view_expense_renders(self, client_no_csrf, app_no_csrf):
        """View expense should render details."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {
            'id': 1,
            'amount': Decimal('100.00'),
            'category': 'Food',
            'note': 'Lunch',
            'date': date(2024, 1, 15),
            'attachment': None,
            'done_by': 'Self',
        }
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/expenses/view/1')
        assert response.status_code == 200

    def test_view_expense_not_found(self, client_no_csrf, app_no_csrf):
        """View non-existent expense should return 404."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = None
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/expenses/view/999')
        assert response.status_code == 404


class TestAttachmentValidation:
    """Test expense attachment file validation."""

    def test_allowed_attachment_valid_extensions(self):
        """Valid extensions should be allowed."""
        from routes.expenses import allowed_attachment
        assert allowed_attachment('receipt.pdf') is True
        assert allowed_attachment('receipt.png') is True
        assert allowed_attachment('receipt.jpg') is True
        assert allowed_attachment('receipt.jpeg') is True
        assert allowed_attachment('receipt.doc') is True

    def test_allowed_attachment_case_insensitive(self):
        """Extension check should be case-insensitive."""
        from routes.expenses import allowed_attachment
        assert allowed_attachment('receipt.PDF') is True
        assert allowed_attachment('receipt.JPG') is True
        assert allowed_attachment('receipt.Png') is True

    def test_allowed_attachment_invalid_rejected(self):
        """Invalid extensions should be rejected."""
        from routes.expenses import allowed_attachment
        assert allowed_attachment('malware.exe') is False
        assert allowed_attachment('script.js') is False
        assert allowed_attachment('hack.php') is False
        assert allowed_attachment('shell.sh') is False

    def test_allowed_attachment_no_extension_rejected(self):
        """Files without extensions should be rejected."""
        from routes.expenses import allowed_attachment
        assert allowed_attachment('noextension') is False


class TestExpenseCSRF:
    """Test CSRF protection for expense endpoints."""

    def test_add_expense_without_csrf_rejected(self, client, app):
        """POST to add expense without CSRF token should be rejected."""
        login_session(client)
        response = client.post('/expenses/add', data={
            'amount': '100',
            'category': 'Food',
            'date': '2024-01-01',
            'done_by': 'Self',
        })
        assert response.status_code == 400

    def test_delete_expense_without_csrf_rejected(self, client, app):
        """POST to delete expense without CSRF token should be rejected."""
        login_session(client)
        response = client.post('/expenses/delete/1')
        assert response.status_code == 400
