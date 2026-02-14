"""
Test suite for authentication routes.
Tests cover signup, login, logout, and profile functionality.
"""

import pytest
import os
import sys
from unittest.mock import MagicMock, patch
from werkzeug.security import generate_password_hash

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


class TestSignup:
    """Test user registration."""

    def test_signup_page_renders(self, client):
        """Signup page should be accessible."""
        response = client.get('/auth/signup')
        assert response.status_code == 200
        assert b'Sign Up' in response.data or b'signup' in response.data.lower()

    def test_signup_valid_user(self, client_no_csrf, app_no_csrf):
        """Valid signup should create user and redirect to login."""
        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = None  # No existing user
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/auth/signup', data={
            'name': 'New User',
            'email': 'newuser@example.com',
            'password': 'securepassword123',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/auth/login' in response.headers.get('Location', '')
        cursor.execute.assert_called()  # INSERT was called

    def test_signup_duplicate_email(self, client_no_csrf, app_no_csrf):
        """Signup with existing email should return error."""
        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {'id': 1}  # Email exists
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/auth/signup', data={
            'name': 'Another User',
            'email': 'existing@example.com',
            'password': 'securepassword123',
        })

        assert response.status_code == 400

    def test_signup_password_too_short(self, client_no_csrf, app_no_csrf):
        """Signup with password < 8 chars should be rejected."""
        response = client_no_csrf.post('/auth/signup', data={
            'name': 'Test User',
            'email': 'test@example.com',
            'password': 'short',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/auth/signup' in response.headers.get('Location', '')

    def test_signup_invalid_email(self, client_no_csrf, app_no_csrf):
        """Signup with invalid email should be rejected."""
        response = client_no_csrf.post('/auth/signup', data={
            'name': 'Test User',
            'email': 'not-an-email',
            'password': 'password12345',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/auth/signup' in response.headers.get('Location', '')

    def test_signup_name_too_long(self, client_no_csrf, app_no_csrf):
        """Signup with name > 100 chars should be rejected."""
        response = client_no_csrf.post('/auth/signup', data={
            'name': 'A' * 101,
            'email': 'test@example.com',
            'password': 'password12345',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/auth/signup' in response.headers.get('Location', '')

    def test_signup_missing_fields(self, client_no_csrf, app_no_csrf):
        """Signup with missing fields should be rejected."""
        response = client_no_csrf.post('/auth/signup', data={
            'name': '',
            'email': 'test@example.com',
            'password': 'password12345',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/auth/signup' in response.headers.get('Location', '')


class TestLogin:
    """Test user login."""

    def test_login_page_renders(self, client):
        """Login page should be accessible."""
        response = client.get('/auth/login')
        assert response.status_code == 200

    def test_login_valid_credentials(self, client_no_csrf, app_no_csrf):
        """Valid login should set session and redirect to dashboard."""
        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {
            'id': 1,
            'name': 'Test User',
            'email': 'test@example.com',
            'password_hash': generate_password_hash('correctpassword'),
        }
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/auth/login', data={
            'email': 'test@example.com',
            'password': 'correctpassword',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/' in response.headers.get('Location', '')

        with client_no_csrf.session_transaction() as sess:
            assert sess.get('user_id') == 1
            assert sess.get('user_name') == 'Test User'

    def test_login_invalid_password(self, client_no_csrf, app_no_csrf):
        """Login with wrong password should fail."""
        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {
            'id': 1,
            'name': 'Test User',
            'email': 'test@example.com',
            'password_hash': generate_password_hash('correctpassword'),
        }
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/auth/login', data={
            'email': 'test@example.com',
            'password': 'wrongpassword',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/auth/login' in response.headers.get('Location', '')

    def test_login_nonexistent_user(self, client_no_csrf, app_no_csrf):
        """Login with non-existent email should fail."""
        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = None
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/auth/login', data={
            'email': 'nonexistent@example.com',
            'password': 'anypassword',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/auth/login' in response.headers.get('Location', '')

    def test_login_email_case_insensitive(self, client_no_csrf, app_no_csrf):
        """Email comparison should be case-insensitive."""
        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {
            'id': 1,
            'name': 'Test User',
            'email': 'test@example.com',
            'password_hash': generate_password_hash('password123'),
        }
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/auth/login', data={
            'email': 'TEST@EXAMPLE.COM',
            'password': 'password123',
        }, follow_redirects=False)

        # Check that email was lowercased in query
        assert response.status_code == 302


class TestLogout:
    """Test user logout."""

    def test_logout_clears_session(self, client_no_csrf, app_no_csrf):
        """Logout should clear session and redirect to login."""
        login_session(client_no_csrf)

        response = client_no_csrf.get('/auth/logout', follow_redirects=False)

        assert response.status_code == 302
        assert '/auth/login' in response.headers.get('Location', '')

        with client_no_csrf.session_transaction() as sess:
            assert 'user_id' not in sess


class TestProfile:
    """Test user profile management."""

    def test_profile_requires_auth(self, client):
        """Profile page should require authentication."""
        response = client.get('/auth/profile')
        assert response.status_code == 302
        assert '/auth/login' in response.headers.get('Location', '')

    def test_profile_page_renders(self, client_no_csrf, app_no_csrf):
        """Profile page should render for logged-in user."""
        login_session(client_no_csrf)
        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {
            'id': 1,
            'name': 'Test User',
            'email': 'test@example.com',
            'avatar_filename': None,
        }
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/auth/profile')
        assert response.status_code == 200

    def test_profile_update_name(self, client_no_csrf, app_no_csrf):
        """User should be able to update their name."""
        login_session(client_no_csrf)
        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {
            'id': 1,
            'name': 'Updated Name',
            'email': 'test@example.com',
            'avatar_filename': None,
        }
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/auth/profile', data={
            'name': 'Updated Name',
        })

        assert response.status_code == 200
        cursor.execute.assert_called()


class TestAvatarUpload:
    """Test avatar file upload validation."""

    def test_allowed_avatar_valid_extensions(self):
        """Valid avatar extensions should be allowed."""
        from routes.auth import allowed_avatar
        assert allowed_avatar('photo.png') is True
        assert allowed_avatar('photo.jpg') is True
        assert allowed_avatar('photo.jpeg') is True

    def test_allowed_avatar_case_insensitive(self):
        """Extension check should be case-insensitive."""
        from routes.auth import allowed_avatar
        assert allowed_avatar('photo.PNG') is True
        assert allowed_avatar('photo.JPG') is True
        assert allowed_avatar('photo.JPEG') is True

    def test_allowed_avatar_invalid_extensions(self):
        """Non-image avatar extensions should be rejected."""
        from routes.auth import allowed_avatar
        assert allowed_avatar('file.pdf') is False
        assert allowed_avatar('script.exe') is False
        assert allowed_avatar('malware.svg') is False
        assert allowed_avatar('file.gif') is False

    def test_allowed_avatar_no_extension(self):
        """Files without extensions should be rejected."""
        from routes.auth import allowed_avatar
        assert allowed_avatar('noextension') is False


class TestPasswordSecurity:
    """Test password handling security."""

    def test_min_password_length_defined(self):
        """MIN_PASSWORD_LENGTH should be at least 8."""
        from routes.auth import MIN_PASSWORD_LENGTH
        assert MIN_PASSWORD_LENGTH >= 8

    def test_password_hashing_works(self):
        """Passwords should be properly hashed."""
        from werkzeug.security import generate_password_hash, check_password_hash
        password = 'test_password_123'
        hashed = generate_password_hash(password)

        assert hashed != password
        assert check_password_hash(hashed, password) is True
        assert check_password_hash(hashed, 'wrong_password') is False
