"""
Test suite for household member routes and the profile switcher.
Tests cover member CRUD, actor switching, and session cache behaviour.
"""

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


def login_session(client, user_id=1, user_name='Test User', members=None, actor=None):
    """Helper to set up a logged-in session, optionally with a warm roster."""
    with client.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['user_name'] = user_name
        if members is not None:
            sess['household_members'] = members
        if actor is not None:
            sess['actor'] = actor


class TestMemberAccess:
    """Test member page access control."""

    def test_members_requires_auth(self, client):
        response = client.get('/members/')
        assert response.status_code in (302, 308)
        assert '/auth/login' in response.headers.get('Location', '')

    def test_switch_requires_auth(self, client_no_csrf):
        response = client_no_csrf.post('/members/switch', data={'name': 'Hassan'})
        assert response.status_code in (302, 308)
        assert '/auth/login' in response.headers.get('Location', '')

    def test_members_accessible_when_logged_in(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = []
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/members/')
        assert response.status_code == 200


class TestMemberList:
    """Test member listing."""

    def test_members_shows_list(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = [
            {'id': 1, 'name': 'Faisal'},
            {'id': 2, 'name': 'Hassan'},
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/members/')
        assert response.status_code == 200
        assert b'Faisal' in response.data
        assert b'Hassan' in response.data

    def test_members_empty_state(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = []
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/members/')
        assert response.status_code == 200
        assert b'No members yet' in response.data

    def test_members_isolated_per_user(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf, user_id=1)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = []
        app_no_csrf.db_pool.get_connection.return_value = conn

        client_no_csrf.get('/members/')

        calls = cursor.execute.call_args_list
        assert any('user_id' in str(call) for call in calls)


class TestAddMember:
    """Test adding household members."""

    def test_add_member_valid(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = [{'id': 1, 'name': 'Faran'}]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/members/', data={'name': 'Faran'})

        assert response.status_code == 200
        conn.commit.assert_called()

    def test_add_member_empty_name_rejected(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = []
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/members/', data={'name': '   '})

        assert response.status_code == 200
        conn.commit.assert_not_called()

    def test_add_member_too_long_rejected(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = []
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/members/', data={'name': 'x' * 51})

        assert response.status_code == 200
        conn.commit.assert_not_called()


class TestDeleteMember:
    """Test deleting household members."""

    def test_delete_member_via_post(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = []
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/members/delete/1', follow_redirects=False)
        assert response.status_code == 302
        assert '/members' in response.headers.get('Location', '')
        conn.commit.assert_called()

    def test_delete_member_via_get_rejected(self, client):
        login_session(client)
        response = client.get('/members/delete/1')
        assert response.status_code == 405

    def test_delete_member_respects_user_ownership(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf, user_id=1)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = []
        app_no_csrf.db_pool.get_connection.return_value = conn

        client_no_csrf.post('/members/delete/1')

        calls = cursor.execute.call_args_list
        assert any('user_id' in str(call) for call in calls)

    def test_deleting_active_member_clears_actor(self, client_no_csrf, app_no_csrf):
        """Removing whoever is selected must not leave a dangling actor."""
        login_session(client_no_csrf, members=['Hassan'], actor='Hassan')

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = []  # roster is empty after the delete
        app_no_csrf.db_pool.get_connection.return_value = conn

        client_no_csrf.post('/members/delete/1')

        with client_no_csrf.session_transaction() as sess:
            assert 'actor' not in sess


class TestSwitchActor:
    """Test the 'who is using this' profile switcher."""

    def test_switch_to_known_member(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = [{'id': 1, 'name': 'Faisal'}, {'id': 2, 'name': 'Hassan'}]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/members/switch', data={'name': 'Hassan'})
        assert response.status_code == 302

        with client_no_csrf.session_transaction() as sess:
            assert sess['actor'] == 'Hassan'

    def test_switch_to_unknown_member_rejected(self, client_no_csrf, app_no_csrf):
        """The actor is stamped on the activity log, so it must not be
        attacker-chosen -- only names really in the household are accepted."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = [{'id': 1, 'name': 'Faisal'}]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/members/switch', data={'name': 'Mallory'})
        assert response.status_code == 302

        with client_no_csrf.session_transaction() as sess:
            assert 'actor' not in sess

    def test_switch_redirects_back_to_referrer(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = [{'id': 1, 'name': 'Faisal'}]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post(
            '/members/switch',
            data={'name': 'Faisal'},
            headers={'Referer': 'http://localhost/expenses/'},
        )
        assert '/expenses/' in response.headers.get('Location', '')


class TestMemberCSRF:
    """Test CSRF protection for member endpoints."""

    def test_add_member_without_csrf_rejected(self, client):
        login_session(client)
        response = client.post('/members/', data={'name': 'Test'})
        assert response.status_code == 400

    def test_delete_member_without_csrf_rejected(self, client):
        login_session(client)
        response = client.post('/members/delete/1')
        assert response.status_code == 400

    def test_switch_without_csrf_rejected(self, client):
        login_session(client)
        response = client.post('/members/switch', data={'name': 'Faisal'})
        assert response.status_code == 400


class TestNavSwitcher:
    """Test the nav renders the switcher from the session cache."""

    def test_nav_shows_members_from_session(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf, members=['Faisal', 'Hassan'], actor='Faisal')

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = None
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/categories/')
        assert response.status_code == 200
        assert b'members/switch' in response.data
        # No "pick someone" placeholder once an actor is chosen.
        assert b'selected disabled' not in response.data
        assert b'<option value="Faisal" selected>' in response.data

    def test_nav_prompts_when_no_actor_selected(self, client_no_csrf, app_no_csrf):
        """An unattributed trail is worse than none -- prompt for a name."""
        login_session(client_no_csrf, members=['Faisal', 'Hassan'])

        conn, cursor = make_mock_connection()
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = None
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/categories/')
        assert response.status_code == 200
        assert b'selected disabled' in response.data
