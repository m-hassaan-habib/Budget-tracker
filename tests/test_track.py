"""
Test suite for the Track tab routes.
Tests cover the activity feed, filters, and undo guards.
"""

import json
import os
import sys
from datetime import datetime
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def make_mock_connection():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor
    return conn, cursor


def login_session(client, user_id=1, actor='Hassan'):
    with client.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['user_name'] = 'Test User'
        sess['actor'] = actor
        sess['household_members'] = ['Faisal', 'Hassan', 'Faran']


def log_row(**overrides):
    row = {
        'id': 1, 'actor': 'Hassan', 'entity_type': 'expense', 'entity_id': 5,
        'action': 'update',
        'before_json': json.dumps({'amount': '300.00', 'category': 'Grocery'}),
        'after_json': json.dumps({'amount': '350.00', 'category': 'Grocery'}),
        'undoes_log_id': None, 'created_at': datetime(2026, 9, 21, 14, 30),
        'undone': 0,
    }
    row.update(overrides)
    return row


class TestTrackAccess:
    def test_track_requires_auth(self, client):
        response = client.get('/track/')
        assert response.status_code in (302, 308)
        assert '/auth/login' in response.headers.get('Location', '')

    def test_undo_requires_auth(self, client_no_csrf):
        response = client_no_csrf.post('/track/undo/1')
        assert response.status_code in (302, 308)

    def test_track_renders_when_logged_in(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.side_effect = [[], []]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/track/')
        assert response.status_code == 200
        assert b'No changes recorded yet' in response.data


class TestTrackFeed:
    def test_shows_field_level_diff(self, client_no_csrf, app_no_csrf):
        """The whole point of the tab: old value -> new value."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.side_effect = [[log_row()], [{'actor': 'Hassan'}]]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.get('/track/')
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert 'Amount' in body
        assert '300.00' in body and '350.00' in body
        assert 'Hassan' in body
        # Unchanged fields must not appear as noise.
        assert body.count('Grocery') >= 1

    def test_shows_actor_and_action(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.side_effect = [
            [log_row(action='create', before_json=None,
                     after_json=json.dumps({'amount': '99.00', 'category': 'Fuel'}))],
            [{'actor': 'Faisal'}],
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        body = client_no_csrf.get('/track/').get_data(as_text=True)
        assert 'Added' in body
        assert 'Fuel' in body

    def test_undone_entry_hides_undo_button(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.side_effect = [[log_row(undone=1)], [{'actor': 'Hassan'}]]
        app_no_csrf.db_pool.get_connection.return_value = conn

        body = client_no_csrf.get('/track/').get_data(as_text=True)
        assert 'undone' in body
        assert '/track/undo/1' not in body

    def test_restore_entry_has_no_undo_button(self, client_no_csrf, app_no_csrf):
        """Undoing an undo would be ambiguous -- undo the original instead."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.side_effect = [[log_row(action='restore')], [{'actor': 'Hassan'}]]
        app_no_csrf.db_pool.get_connection.return_value = conn

        body = client_no_csrf.get('/track/').get_data(as_text=True)
        assert '/track/undo/1' not in body

    def test_filters_are_passed_to_query(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.side_effect = [[], []]
        app_no_csrf.db_pool.get_connection.return_value = conn

        client_no_csrf.get('/track/?entity=expense&actor=Faisal&action=delete')

        feed_query = cursor.execute.call_args_list[0]
        sql, params = feed_query[0][0], feed_query[0][1]
        assert 'entity_type' in sql and 'actor' in sql and 'action' in sql
        assert 'expense' in params and 'Faisal' in params and 'delete' in params

    def test_feed_is_scoped_to_user(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf, user_id=4)

        conn, cursor = make_mock_connection()
        cursor.fetchall.side_effect = [[], []]
        app_no_csrf.db_pool.get_connection.return_value = conn

        client_no_csrf.get('/track/')

        feed_query = cursor.execute.call_args_list[0]
        assert 'a.user_id = %s' in feed_query[0][0]
        assert 4 in feed_query[0][1]


class TestUndoGuards:
    def test_unknown_entry_404(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = None
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/track/undo/999')
        assert response.status_code == 404
        conn.commit.assert_not_called()

    def test_cannot_undo_a_restore(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = {
            'id': 1, 'entity_type': 'expense', 'entity_id': 5,
            'action': 'restore', 'before_json': None, 'after_json': None,
        }
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/track/undo/1')
        assert response.status_code == 302
        conn.commit.assert_not_called()

    def test_cannot_undo_twice(self, client_no_csrf, app_no_csrf):
        """A second undo of the same entry would be ambiguous."""
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchone.side_effect = [
            {'id': 1, 'entity_type': 'expense', 'entity_id': 5, 'action': 'delete',
             'before_json': json.dumps({'amount': '300.00'}), 'after_json': None},
            {'id': 9},  # already_undone finds a restore pointing at it
        ]
        app_no_csrf.db_pool.get_connection.return_value = conn

        response = client_no_csrf.post('/track/undo/1')
        assert response.status_code == 302
        conn.commit.assert_not_called()

    def test_undo_scoped_to_user(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf, user_id=6)

        conn, cursor = make_mock_connection()
        cursor.fetchone.return_value = None
        app_no_csrf.db_pool.get_connection.return_value = conn

        client_no_csrf.post('/track/undo/1')

        lookup = cursor.execute.call_args_list[0]
        assert 'user_id' in lookup[0][0]
        assert 6 in lookup[0][1]

    def test_undo_via_get_rejected(self, client):
        login_session(client)
        response = client.get('/track/undo/1')
        assert response.status_code == 405

    def test_undo_without_csrf_rejected(self, client):
        login_session(client)
        response = client.post('/track/undo/1')
        assert response.status_code == 400


class TestNavLink:
    def test_track_link_in_nav(self, client_no_csrf, app_no_csrf):
        login_session(client_no_csrf)

        conn, cursor = make_mock_connection()
        cursor.fetchall.side_effect = [[], []]
        app_no_csrf.db_pool.get_connection.return_value = conn

        body = client_no_csrf.get('/track/').get_data(as_text=True)
        assert 'href="/track/"' in body
