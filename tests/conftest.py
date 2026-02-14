"""
Shared pytest fixtures for Budget Tracker tests.
"""

import pytest
import os
import sys
from unittest.mock import MagicMock, patch
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
        """Mock DB initialization - no real MySQL needed."""
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
def app_no_csrf():
    """Create application for testing without CSRF protection."""
    with patch('config.Config', TestConfig):
        from app import create_app
        application = create_app(config_class=TestConfig)
        application.config['WTF_CSRF_ENABLED'] = False
        yield application


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def client_no_csrf(app_no_csrf):
    """Create test client without CSRF."""
    return app_no_csrf.test_client()


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


def login_session(client, user_id=1, user_name='Test User'):
    """Helper to set up a logged-in session."""
    with client.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['user_name'] = user_name


@pytest.fixture
def logged_in_client(client_no_csrf, app_no_csrf):
    """Client with logged-in session and mocked DB."""
    login_session(client_no_csrf)
    return client_no_csrf


@pytest.fixture
def mock_db(app_no_csrf):
    """Provide mock database connection and cursor."""
    conn, cursor = make_mock_connection()
    app_no_csrf.db_pool.get_connection.return_value = conn
    return conn, cursor
