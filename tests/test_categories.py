"""
Test suite for category routes.
Tests cover category CRUD operations.
"""

import pytest
import os
import sys
from unittest.mock import MagicMock

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


class TestCategoryAccess:
    """Test category page access control."""

    def test_categories_requires_auth(self, client):
        """Categories page should require authentication."""
        response = client.get('/categories/')
        assert response.status_code in (302, 308)
        assert '/auth/login' in response.headers.get('Location', '')

    def test_categories_accessible_when_logged_in(self, client_no_csrf, app_no_csrf):
        """Categories page should be accessible for logged-in users."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = []
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/categories/')
        assert response.status_code == 200


class TestCategoryList:
    """Test category listing."""

    def test_categories_empty_state(self, client_no_csrf, app_no_csrf):
        """Categories page should handle empty state."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = []
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/categories/')
        assert response.status_code == 200

    def test_categories_shows_list(self, client_no_csrf, app_no_csrf):
        """Categories page should display categories."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = [
            {'id': 1, 'name': 'Food'},
            {'id': 2, 'name': 'Transport'},
            {'id': 3, 'name': 'Entertainment'},
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/categories/')
        assert response.status_code == 200
        assert b'Food' in response.data
        assert b'Transport' in response.data


class TestAddCategory:
    """Test adding categories."""

    def test_add_category_valid(self, client_no_csrf, app_no_csrf):
        """Valid category should be added."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = [{'id': 1, 'name': 'NewCategory'}]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/categories/', data={
            'name': 'NewCategory',
        })

        assert response.status_code == 200
        cursor.execute.assert_called()
        conn.commit.assert_called()

    def test_add_category_empty_name_ignored(self, client_no_csrf, app_no_csrf):
        """Empty category name should be ignored."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = []
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/categories/', data={
            'name': '',
        })

        assert response.status_code == 200

    def test_add_category_whitespace_stripped(self, client_no_csrf, app_no_csrf):
        """Category name should have whitespace stripped."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = [{'id': 1, 'name': 'Groceries'}]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/categories/', data={
            'name': '  Groceries  ',
        })

        assert response.status_code == 200

    def test_add_duplicate_category_handled(self, client_no_csrf, app_no_csrf):
        """Duplicate category should be handled (INSERT IGNORE)."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = [{'id': 1, 'name': 'Food'}]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/categories/', data={
            'name': 'Food',  # Assuming Food already exists
        })

        # Should not crash due to INSERT IGNORE
        assert response.status_code == 200


class TestDeleteCategory:
    """Test deleting categories."""

    def test_delete_category_via_post(self, client_no_csrf, app_no_csrf):
        """Delete category via POST should work."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/categories/delete/1', follow_redirects=False)
        assert response.status_code == 302
        assert '/categories' in response.headers.get('Location', '')
        conn.commit.assert_called()

    def test_delete_category_via_get_rejected(self, client):
        """Delete category via GET should be rejected (405)."""
        login_session(client)
        response = client.get('/categories/delete/1')
        assert response.status_code == 405

    def test_delete_category_respects_user_ownership(self, client_no_csrf, app_no_csrf):
        """Delete should only affect current user's categories."""
        login_session(client_no_csrf, user_id=1)

        conn, cursor = make_mock_connection()
        app_no_csrf.db_pool.get_connection.return_value = conn

        client_no_csrf.post('/categories/delete/1')

        # Verify user_id is included in DELETE query
        calls = cursor.execute.call_args_list
        assert any('user_id' in str(call) for call in calls)


class TestCategoryCSRF:
    """Test CSRF protection for category endpoints."""

    def test_add_category_without_csrf_rejected(self, client, app):
        """POST to add category without CSRF token should be rejected."""
        login_session(client)
        response = client.post('/categories/', data={
            'name': 'Test Category',
        })
        assert response.status_code == 400

    def test_delete_category_without_csrf_rejected(self, client, app):
        """POST to delete category without CSRF token should be rejected."""
        login_session(client)
        response = client.post('/categories/delete/1')
        assert response.status_code == 400


class TestCategoryIsolation:
    """Test user data isolation for categories."""

    def test_categories_isolated_per_user(self, client_no_csrf, app_no_csrf):
        """Each user should only see their own categories."""
        login_session(client_no_csrf, user_id=1)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = [{'id': 1, 'name': 'User1Category'}]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/categories/')
        assert response.status_code == 200

        # Verify user_id filter in query
        calls = cursor.execute.call_args_list
        assert any('user_id' in str(call) for call in calls)
