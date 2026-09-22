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
            [],  # category breakdown (top category)
            [],  # category filter options
            [],  # persons
            [],  # month options
            [],  # quick-add category list
            [],  # quick-add top category chips
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
            [{'category': 'Food', 'total': Decimal('100.00')}],  # breakdown
            [{'category': 'Food'}],  # category filter options
            [{'done_by': 'Self'}],
            [{'m': '2024-01'}],  # month options
            [],  # quick-add category list
            [],  # quick-add top category chips
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
            [{'category': 'Food', 'total': Decimal('100.00')}],
            [{'category': 'Food'}],
            [{'done_by': 'Self'}],
            [{'m': '2024-01'}],
            [],  # quick-add category list
            [],  # quick-add top category chips
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
        cursor.fetchall.side_effect = [[], [], [], [], [], [], []]
        cursor.fetchone.side_effect = [
            {'total': Decimal('0'), 'count': 0},
            {'default_done_by': 'Self'},
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/expenses/?person=Self')
        assert response.status_code == 200


class TestExpenseMonthFilter:
    """The month dropdown scopes both the list and the summary cards."""

    def _mock_page(self, cursor):
        cursor.fetchall.side_effect = [[], [], [], [], [{'m': '2024-01'}], [], []]
        cursor.fetchone.side_effect = [
            {'total': Decimal('0'), 'count': 0},
            {'default_done_by': 'Self'},
        ]

    def test_month_narrows_every_query(self, client_no_csrf, app_no_csrf):
        """A selected month bounds the list, the totals and the breakdown."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        self._mock_page(cursor)
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/expenses/?month=2024-01')
        assert response.status_code == 200

        bounded = [
            call for call in cursor.execute.call_args_list
            if 'date BETWEEN' in call.args[0]
        ]
        assert len(bounded) == 3, "list, summary and breakdown must all be scoped"
        for call in bounded:
            assert call.args[1][-2:] == (date(2024, 1, 1), date(2024, 1, 31))

    def test_no_month_leaves_queries_unbounded(self, client_no_csrf, app_no_csrf):
        """Without ?month=, the page still reports every expense."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        self._mock_page(cursor)
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/expenses/')
        assert response.status_code == 200
        assert not any('date BETWEEN' in c.args[0] for c in cursor.execute.call_args_list)

    def test_junk_month_is_ignored(self, client_no_csrf, app_no_csrf):
        """A garbage ?month= must fall back to all months, not error."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        self._mock_page(cursor)
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/expenses/?month=drop-table')
        assert response.status_code == 200
        assert not any('date BETWEEN' in c.args[0] for c in cursor.execute.call_args_list)

    def test_month_combines_with_category(self, client_no_csrf, app_no_csrf):
        """Month and category narrow the list together, not exclusively."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        self._mock_page(cursor)
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/expenses/?month=2024-01&category=Food')
        assert response.status_code == 200

        list_query = cursor.execute.call_args_list[0]
        assert 'category=%s' in list_query.args[0]
        assert 'date BETWEEN' in list_query.args[0]
        assert list_query.args[1] == (1, 'Food', date(2024, 1, 1), date(2024, 1, 31))

    def test_dropdown_offers_the_selected_month(self, client_no_csrf, app_no_csrf):
        """An empty month stays selectable so the user can navigate back out."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        # No rows in January, but March has some -- so the filter bar is shown.
        cursor.fetchall.side_effect = [
            [], [], [{'category': 'Food'}], [], [{'m': '2024-03'}], [], [],
        ]
        cursor.fetchone.side_effect = [
            {'total': Decimal('0'), 'count': 0},
            {'default_done_by': 'Self'},
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/expenses/?month=2024-01')
        assert response.status_code == 200
        assert b'January 2024' in response.data
        assert b'March 2024' in response.data


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


class TestQuickAdd:
    """Test the inline quick-entry endpoint."""

    def _mock_row(self):
        return {
            'id': 42, 'amount': Decimal('300.00'), 'category': 'Grocery',
            'note': None, 'date': date(2026, 9, 21), 'attachment': None,
            'done_by': 'Hassan',
        }

    def test_quick_add_requires_auth(self, client_no_csrf):
        response = client_no_csrf.post('/expenses/quick', data={})
        assert response.status_code in (302, 308)

    def test_quick_add_creates_expense(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.lastrowid = 42
        cursor.fetchone.return_value = self._mock_row()
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/expenses/quick', data={
            'amount': '300', 'category': 'Grocery',
            'date': '2026-09-21', 'done_by': 'Hassan',
        })

        assert response.status_code == 200
        payload = response.get_json()
        assert payload['ok'] is True
        assert payload['id'] == 42
        # Returns the rendered row so the list markup lives in one place.
        assert 'Grocery' in payload['html']
        conn.commit.assert_called()

    def test_quick_add_remembers_date_and_person(self, client_no_csrf, app_no_csrf):
        """Sticky fields are the whole point -- catching up shouldn't mean
        re-picking the same date and person for every entry."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.lastrowid = 42
        cursor.fetchone.return_value = self._mock_row()
        app_no_csrf.db_pool.get_connection.return_value = conn

        client_no_csrf.post('/expenses/quick', data={
            'amount': '300', 'category': 'Grocery',
            'date': '2026-09-18', 'done_by': 'Faran',
        })

        with client_no_csrf.session_transaction() as sess:
            assert sess['last_expense_date'] == '2026-09-18'
            assert sess['last_done_by'] == 'Faran'

    def test_quick_add_rejects_bad_amount(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/expenses/quick', data={
            'amount': 'abc', 'category': 'Grocery',
            'date': '2026-09-21', 'done_by': 'Hassan',
        })

        assert response.status_code == 400
        assert response.get_json()['ok'] is False
        conn.commit.assert_not_called()

    def test_quick_add_rejects_negative_amount(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/expenses/quick', data={
            'amount': '-5', 'category': 'Grocery',
            'date': '2026-09-21', 'done_by': 'Hassan',
        })

        assert response.status_code == 400
        conn.commit.assert_not_called()

    def test_quick_add_rejects_bad_date(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/expenses/quick', data={
            'amount': '300', 'category': 'Grocery',
            'date': 'not-a-date', 'done_by': 'Hassan',
        })

        assert response.status_code == 400
        conn.commit.assert_not_called()

    def test_quick_add_requires_category(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/expenses/quick', data={
            'amount': '300', 'category': '',
            'date': '2026-09-21', 'done_by': 'Hassan',
        })

        assert response.status_code == 400
        conn.commit.assert_not_called()

    def test_quick_add_requires_done_by(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/expenses/quick', data={
            'amount': '300', 'category': 'Grocery',
            'date': '2026-09-21', 'done_by': '',
        })

        assert response.status_code == 400
        conn.commit.assert_not_called()

    def test_quick_add_without_csrf_rejected(self, client):
        login_session(client)
        response = client.post('/expenses/quick', data={
            'amount': '300', 'category': 'Grocery',
            'date': '2026-09-21', 'done_by': 'Hassan',
        })
        assert response.status_code == 400

    def test_quick_add_scopes_insert_to_user(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf, user_id=7)

        conn, cursor = make_mock_connection()
        cursor.lastrowid = 42
        cursor.fetchone.return_value = self._mock_row()
        app_no_csrf.db_pool.get_connection.return_value = conn

        client_no_csrf.post('/expenses/quick', data={
            'amount': '300', 'category': 'Grocery',
            'date': '2026-09-21', 'done_by': 'Hassan',
        })

        insert = cursor.execute.call_args_list[0]
        assert 7 in insert[0][1]


class TestRepeatExpense:
    """Test cloning an expense onto today."""

    def test_repeat_requires_auth(self, client_no_csrf):
        response = client_no_csrf.post('/expenses/repeat/1')
        assert response.status_code in (302, 308)

    def test_repeat_clones_with_today(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {
            'amount': Decimal('450.00'), 'category': 'Grocery',
            'note': 'Milk', 'done_by': 'Faisal',
        }
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/expenses/repeat/1')
        assert response.status_code == 302
        conn.commit.assert_called()

        insert = next(c for c in cursor.execute.call_args_list
                      if 'INSERT INTO expense' in c[0][0])
        assert date.today().isoformat() in insert[0][1]
        assert 'Grocery' in insert[0][1]

    def test_repeat_unknown_expense_404(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = None
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/expenses/repeat/999')
        assert response.status_code == 404
        conn.commit.assert_not_called()

    def test_repeat_respects_user_ownership(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf, user_id=3)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = None
        app_no_csrf.db_pool.get_connection.return_value = conn

        client_no_csrf.post('/expenses/repeat/1')

        select = cursor.execute.call_args_list[0]
        assert 'user_id' in select[0][0]
        assert 3 in select[0][1]

    def test_repeat_via_get_rejected(self, client):
        login_session(client)
        response = client.get('/expenses/repeat/1')
        assert response.status_code == 405

    def test_repeat_without_csrf_rejected(self, client):
        login_session(client)
        response = client.post('/expenses/repeat/1')
        assert response.status_code == 400


class TestExpenseTrail:
    """The per-record history shown on the expense detail page."""

    def test_view_shows_record_history(self, client_no_csrf, app_no_csrf):
        import json
        from datetime import datetime

        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {
            'id': 1, 'amount': Decimal('350.00'), 'category': 'Grocery',
            'note': 'Milk', 'date': date(2026, 9, 20), 'attachment': None,
            'done_by': 'Faisal',
        }
        cursor.fetchall.return_value = [{
            'id': 3, 'actor': 'Hassan', 'entity_type': 'expense', 'entity_id': 1,
            'action': 'update',
            'before_json': json.dumps({'amount': '300.00'}),
            'after_json': json.dumps({'amount': '350.00'}),
            'undoes_log_id': None, 'created_at': datetime(2026, 9, 21, 9, 5),
            'undone': 0,
        }]
        app_no_csrf.db_pool.get_connection.return_value = conn

        body = client_no_csrf.get('/expenses/view/1').get_data(as_text=True)

        assert 'History' in body
        assert 'Hassan' in body
        assert '300.00' in body and '350.00' in body

    def test_view_without_history_omits_section(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {
            'id': 1, 'amount': Decimal('350.00'), 'category': 'Grocery',
            'note': None, 'date': date(2026, 9, 20), 'attachment': None,
            'done_by': 'Faisal',
        }
        cursor.fetchall.return_value = []
        app_no_csrf.db_pool.get_connection.return_value = conn

        body = client_no_csrf.get('/expenses/view/1').get_data(as_text=True)
        assert 'See all changes' not in body
