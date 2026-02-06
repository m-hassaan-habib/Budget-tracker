"""
Security test suite for the Budget Tracker application.
Tests cover CSRF protection, authentication, input validation,
session security, security headers, and access control.
"""

import pytest
import os
import sys
from unittest.mock import MagicMock, patch, PropertyMock
from decimal import Decimal

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestConfig:
    """Test configuration that bypasses MySQL."""
    SECRET_KEY = 'test-secret-key-for-testing-only'
    TESTING = True
    WTF_CSRF_ENABLED = True
    SERVER_NAME = 'localhost'
    UPLOAD_FOLDER = '/tmp/test_uploads'
    AVATAR_FOLDER = '/tmp/test_uploads/avatars'
    RECEIPT_FOLDER = '/tmp/test_uploads/receipts'
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    ALLOWED_ATTACH_EXT = {"pdf", "png", "jpg", "jpeg", "doc"}
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    @staticmethod
    def init_db(app):
        """Mock DB initialization — no real MySQL needed."""
        app.db_pool = MagicMock()


def make_mock_connection():
    """Create a mock MySQL connection with cursor context manager."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor
    return conn, cursor


@pytest.fixture
def app():
    """Create application for testing."""
    with patch('config.Config', TestConfig):
        from app import create_app
        application = create_app(config_class=TestConfig)
        application.config['WTF_CSRF_ENABLED'] = True
        yield application


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def csrf_token(client, app):
    """Get a CSRF token by accessing a page."""
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['user_name'] = 'Test User'

    with app.test_request_context():
        from flask_wtf.csrf import generate_csrf
        token = generate_csrf()
    return token


def login_session(client):
    """Helper to set up a logged-in session."""
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['user_name'] = 'Test User'


# ─────────────────────────────────────────────────────────────
#  1. AUTHENTICATION TESTS
# ─────────────────────────────────────────────────────────────

class TestAuthentication:
    """Test that protected routes require authentication."""

    PROTECTED_ROUTES = [
        ('GET', '/'),
        ('GET', '/expenses/'),
        ('GET', '/income/'),
        ('GET', '/settings/'),
        ('GET', '/history/'),
        ('GET', '/history/compare'),
        ('GET', '/categories/'),
        ('GET', '/auth/profile'),
    ]

    @pytest.mark.parametrize("method,url", PROTECTED_ROUTES)
    def test_protected_routes_redirect_to_login(self, client, method, url):
        """Unauthenticated users should be redirected to login."""
        if method == 'GET':
            response = client.get(url)
        else:
            response = client.post(url)

        assert response.status_code in (302, 308), \
            f"{method} {url} should redirect unauthenticated users"
        assert '/auth/login' in response.headers.get('Location', '')

    def test_login_page_accessible(self, client):
        """Login page should be accessible without auth."""
        response = client.get('/auth/login')
        assert response.status_code == 200

    def test_signup_page_accessible(self, client):
        """Signup page should be accessible without auth."""
        response = client.get('/auth/signup')
        assert response.status_code == 200


# ─────────────────────────────────────────────────────────────
#  2. CSRF PROTECTION TESTS
# ─────────────────────────────────────────────────────────────

class TestCSRFProtection:
    """Test that CSRF tokens are required for all POST endpoints."""

    def test_login_post_without_csrf_rejected(self, client):
        """POST to login without CSRF token should be rejected."""
        response = client.post('/auth/login', data={
            'email': 'test@test.com',
            'password': 'password123'
        })
        assert response.status_code == 400

    def test_signup_post_without_csrf_rejected(self, client):
        """POST to signup without CSRF token should be rejected."""
        response = client.post('/auth/signup', data={
            'name': 'Test',
            'email': 'test@test.com',
            'password': 'password12345'
        })
        assert response.status_code == 400

    def test_add_income_without_csrf_rejected(self, client, app):
        """POST to add income without CSRF token should be rejected."""
        login_session(client)
        response = client.post('/income/add', data={
            'source': 'Salary',
            'amount': '5000'
        })
        assert response.status_code == 400

    def test_add_expense_without_csrf_rejected(self, client, app):
        """POST to add expense without CSRF token should be rejected."""
        login_session(client)
        response = client.post('/expenses/add', data={
            'amount': '100',
            'category': 'Food',
            'date': '2024-01-01',
            'done_by': 'Self'
        })
        assert response.status_code == 400

    def test_settings_update_without_csrf_rejected(self, client, app):
        """POST to update settings without CSRF token should be rejected."""
        login_session(client)
        response = client.post('/settings/update', data={
            'limit': '5000',
            'savings': '1000'
        })
        assert response.status_code == 400

    def test_fresh_start_without_csrf_rejected(self, client, app):
        """POST to fresh start without CSRF token should be rejected."""
        login_session(client)
        response = client.post('/settings/fresh-start')
        assert response.status_code == 400

    def test_end_month_without_csrf_rejected(self, client, app):
        """POST to end month without CSRF token should be rejected."""
        login_session(client)
        response = client.post('/settings/end-month')
        assert response.status_code == 400


# ─────────────────────────────────────────────────────────────
#  3. DELETE VIA GET PREVENTION TESTS
# ─────────────────────────────────────────────────────────────

class TestDeleteViaGetPrevention:
    """Test that delete operations only accept POST, not GET."""

    def test_expense_delete_via_get_rejected(self, client, app):
        """GET to delete expense should return 405 Method Not Allowed."""
        login_session(client)
        response = client.get('/expenses/delete/1')
        assert response.status_code == 405

    def test_income_delete_via_get_rejected(self, client, app):
        """GET to delete income should return 405 Method Not Allowed."""
        login_session(client)
        response = client.get('/income/delete/1')
        assert response.status_code == 405

    def test_category_delete_via_get_rejected(self, client, app):
        """GET to delete category should return 405 Method Not Allowed."""
        login_session(client)
        response = client.get('/categories/delete/1')
        assert response.status_code == 405


# ─────────────────────────────────────────────────────────────
#  4. INPUT VALIDATION TESTS
# ─────────────────────────────────────────────────────────────

class TestInputValidation:
    """Test server-side input validation for all forms."""

    def _get_csrf_token(self, app):
        """Generate a valid CSRF token."""
        with app.test_request_context():
            from flask_wtf.csrf import generate_csrf
            return generate_csrf()

    def test_signup_password_too_short(self, client, app):
        """Signup with password < 8 chars should be rejected."""
        login_session(client)
        app.config['WTF_CSRF_ENABLED'] = False
        try:
            conn, cursor = make_mock_connection()
            cursor.fetchone.return_value = None
            app.db_pool.get_connection.return_value = conn

            response = client.post('/auth/signup', data={
                'name': 'Test User',
                'email': 'test@example.com',
                'password': 'short',
            }, follow_redirects=False)
            assert response.status_code == 302
            assert '/auth/signup' in response.headers.get('Location', '')
        finally:
            app.config['WTF_CSRF_ENABLED'] = True

    def test_signup_invalid_email(self, client, app):
        """Signup with invalid email should be rejected."""
        app.config['WTF_CSRF_ENABLED'] = False
        try:
            response = client.post('/auth/signup', data={
                'name': 'Test User',
                'email': 'not-an-email',
                'password': 'password12345',
            }, follow_redirects=False)
            assert response.status_code == 302
            assert '/auth/signup' in response.headers.get('Location', '')
        finally:
            app.config['WTF_CSRF_ENABLED'] = True

    def test_signup_name_too_long(self, client, app):
        """Signup with name > 100 chars should be rejected."""
        app.config['WTF_CSRF_ENABLED'] = False
        try:
            response = client.post('/auth/signup', data={
                'name': 'A' * 101,
                'email': 'test@example.com',
                'password': 'password12345',
            }, follow_redirects=False)
            assert response.status_code == 302
            assert '/auth/signup' in response.headers.get('Location', '')
        finally:
            app.config['WTF_CSRF_ENABLED'] = True

    def test_income_negative_amount_rejected(self, client, app):
        """Adding income with negative amount should be rejected."""
        login_session(client)
        app.config['WTF_CSRF_ENABLED'] = False
        try:
            response = client.post('/income/add', data={
                'source': 'Salary',
                'amount': '-500',
            }, follow_redirects=False)
            assert response.status_code == 302
            assert '/income/add' in response.headers.get('Location', '')
        finally:
            app.config['WTF_CSRF_ENABLED'] = True

    def test_income_non_numeric_amount_rejected(self, client, app):
        """Adding income with non-numeric amount should be rejected."""
        login_session(client)
        app.config['WTF_CSRF_ENABLED'] = False
        try:
            response = client.post('/income/add', data={
                'source': 'Salary',
                'amount': 'abc',
            }, follow_redirects=False)
            assert response.status_code == 302
            assert '/income/add' in response.headers.get('Location', '')
        finally:
            app.config['WTF_CSRF_ENABLED'] = True

    def test_income_source_too_long_rejected(self, client, app):
        """Adding income with source > 100 chars should be rejected."""
        login_session(client)
        app.config['WTF_CSRF_ENABLED'] = False
        try:
            response = client.post('/income/add', data={
                'source': 'X' * 101,
                'amount': '5000',
            }, follow_redirects=False)
            assert response.status_code == 302
            assert '/income/add' in response.headers.get('Location', '')
        finally:
            app.config['WTF_CSRF_ENABLED'] = True

    def test_expense_invalid_date_rejected(self, client, app):
        """Adding expense with invalid date should be rejected."""
        login_session(client)
        app.config['WTF_CSRF_ENABLED'] = False
        try:
            response = client.post('/expenses/add', data={
                'amount': '100',
                'category': 'Food',
                'date': 'not-a-date',
                'done_by': 'Self',
            }, follow_redirects=False)
            assert response.status_code == 302
            assert '/expenses/add' in response.headers.get('Location', '')
        finally:
            app.config['WTF_CSRF_ENABLED'] = True

    def test_expense_negative_amount_rejected(self, client, app):
        """Adding expense with negative amount should be rejected."""
        login_session(client)
        app.config['WTF_CSRF_ENABLED'] = False
        try:
            response = client.post('/expenses/add', data={
                'amount': '-100',
                'category': 'Food',
                'date': '2024-01-01',
                'done_by': 'Self',
            }, follow_redirects=False)
            assert response.status_code == 302
            assert '/expenses/add' in response.headers.get('Location', '')
        finally:
            app.config['WTF_CSRF_ENABLED'] = True

    def test_expense_missing_category_rejected(self, client, app):
        """Adding expense without category should be rejected."""
        login_session(client)
        app.config['WTF_CSRF_ENABLED'] = False
        try:
            response = client.post('/expenses/add', data={
                'amount': '100',
                'category': '',
                'date': '2024-01-01',
                'done_by': 'Self',
            }, follow_redirects=False)
            assert response.status_code == 302
            assert '/expenses/add' in response.headers.get('Location', '')
        finally:
            app.config['WTF_CSRF_ENABLED'] = True

    def test_settings_invalid_limit_rejected(self, client, app):
        """Updating settings with non-numeric limit should be rejected."""
        login_session(client)
        app.config['WTF_CSRF_ENABLED'] = False
        try:
            response = client.post('/settings/update', data={
                'limit': 'abc',
                'savings': '1000',
            }, follow_redirects=False)
            assert response.status_code == 302
            assert '/settings' in response.headers.get('Location', '')
        finally:
            app.config['WTF_CSRF_ENABLED'] = True


# ─────────────────────────────────────────────────────────────
#  5. SECURITY HEADERS TESTS
# ─────────────────────────────────────────────────────────────

class TestSecurityHeaders:
    """Test that security headers are set on responses."""

    def test_x_content_type_options(self, client):
        """X-Content-Type-Options header should be set."""
        response = client.get('/auth/login')
        assert response.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_x_frame_options(self, client):
        """X-Frame-Options header should be set."""
        response = client.get('/auth/login')
        assert response.headers.get('X-Frame-Options') == 'SAMEORIGIN'

    def test_x_xss_protection(self, client):
        """X-XSS-Protection header should be set."""
        response = client.get('/auth/login')
        assert response.headers.get('X-XSS-Protection') == '1; mode=block'

    def test_referrer_policy(self, client):
        """Referrer-Policy header should be set."""
        response = client.get('/auth/login')
        assert response.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'


# ─────────────────────────────────────────────────────────────
#  6. SESSION SECURITY TESTS
# ─────────────────────────────────────────────────────────────

class TestSessionSecurity:
    """Test session cookie security configuration."""

    def test_session_cookie_httponly(self, app):
        """SESSION_COOKIE_HTTPONLY should be True."""
        assert app.config.get('SESSION_COOKIE_HTTPONLY') is True

    def test_session_cookie_samesite(self, app):
        """SESSION_COOKIE_SAMESITE should be Lax."""
        assert app.config.get('SESSION_COOKIE_SAMESITE') == 'Lax'

    def test_secret_key_not_default(self, app):
        """SECRET_KEY should not be the insecure default."""
        assert app.config['SECRET_KEY'] != 'your-secret-key'
        assert len(app.config['SECRET_KEY']) >= 16


# ─────────────────────────────────────────────────────────────
#  7. FILE ACCESS CONTROL TESTS
# ─────────────────────────────────────────────────────────────

class TestFileAccessControl:
    """Test that uploaded files require authentication to access."""

    def test_avatar_unauthenticated_redirects(self, client):
        """Accessing avatar files without login should redirect."""
        response = client.get('/uploads/avatars/test.png')
        assert response.status_code == 302
        assert '/auth/login' in response.headers.get('Location', '')

    def test_receipt_unauthenticated_redirects(self, client):
        """Accessing receipt files without login should redirect."""
        response = client.get('/uploads/receipts/test.pdf')
        assert response.status_code == 302
        assert '/auth/login' in response.headers.get('Location', '')


# ─────────────────────────────────────────────────────────────
#  8. FILE UPLOAD VALIDATION TESTS
# ─────────────────────────────────────────────────────────────

class TestFileUploadValidation:
    """Test file extension validation."""

    def test_allowed_attachment_valid(self):
        """Valid extensions should be allowed."""
        from routes.expenses import allowed_attachment
        assert allowed_attachment('receipt.pdf') is True
        assert allowed_attachment('receipt.png') is True
        assert allowed_attachment('receipt.jpg') is True
        assert allowed_attachment('receipt.jpeg') is True

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

    def test_allowed_avatar_valid(self):
        """Valid avatar extensions should be allowed."""
        from routes.auth import allowed_avatar
        assert allowed_avatar('photo.png') is True
        assert allowed_avatar('photo.jpg') is True
        assert allowed_avatar('photo.jpeg') is True

    def test_allowed_avatar_invalid_rejected(self):
        """Non-image avatar extensions should be rejected."""
        from routes.auth import allowed_avatar
        assert allowed_avatar('file.pdf') is False
        assert allowed_avatar('script.exe') is False
        assert allowed_avatar('malware.svg') is False


# ─────────────────────────────────────────────────────────────
#  9. PASSWORD SECURITY TESTS
# ─────────────────────────────────────────────────────────────

class TestPasswordSecurity:
    """Test password hashing and validation."""

    def test_password_hashing(self):
        """Passwords should be properly hashed."""
        from werkzeug.security import generate_password_hash, check_password_hash
        pw = 'test_password_123'
        hashed = generate_password_hash(pw)
        assert hashed != pw
        assert check_password_hash(hashed, pw) is True
        assert check_password_hash(hashed, 'wrong_password') is False

    def test_min_password_length_constant(self):
        """MIN_PASSWORD_LENGTH should be at least 8."""
        from routes.auth import MIN_PASSWORD_LENGTH
        assert MIN_PASSWORD_LENGTH >= 8
