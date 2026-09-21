"""
Test suite for change tracking (the Track tab).

The rest of the suite mocks the database, which cannot show whether undo
actually puts a row back. These tests run activity.py's real SQL against an
in-memory SQLite database so the round-trip is genuinely exercised.
"""

import os
import sqlite3
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import activity


class SqliteCursor:
    """Adapts a sqlite3 cursor to the mysql-connector interface activity.py
    expects: %s placeholders and dict rows."""

    def __init__(self, cursor):
        self._c = cursor

    def execute(self, sql, params=()):
        self._c.execute(sql.replace('%s', '?'), params)
        return self

    def fetchone(self):
        row = self._c.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        return [dict(r) for r in self._c.fetchall()]

    @property
    def lastrowid(self):
        return self._c.lastrowid

    @property
    def rowcount(self):
        return self._c.rowcount


@pytest.fixture
def cur():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE expense (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount TEXT, category TEXT, note TEXT,
            date TEXT, attachment TEXT, done_by TEXT
        );
        CREATE TABLE income (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            source TEXT, amount TEXT
        );
        CREATE TABLE activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, actor TEXT NOT NULL,
            entity_type TEXT NOT NULL, entity_id INTEGER,
            action TEXT NOT NULL, before_json TEXT, after_json TEXT,
            undoes_log_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    yield SqliteCursor(conn.cursor())
    conn.close()


def make_expense(cur, **overrides):
    values = {
        'amount': '300.00', 'category': 'Grocery', 'note': 'Milk',
        'date': '2026-09-20', 'attachment': None, 'done_by': 'Faisal',
    }
    values.update(overrides)
    cur.execute(
        "INSERT INTO expense (amount, category, note, date, attachment, done_by, user_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (values['amount'], values['category'], values['note'], values['date'],
         values['attachment'], values['done_by'], 1)
    )
    return cur.lastrowid


class TestSnapshot:
    def test_snapshot_captures_declared_columns(self, cur):
        expense_id = make_expense(cur)
        snap = activity.snapshot(cur, 'expense', expense_id, 1)

        assert snap['category'] == 'Grocery'
        assert snap['done_by'] == 'Faisal'
        # Explicit column list, not SELECT *, so id/user_id stay out.
        assert 'id' not in snap and 'user_id' not in snap

    def test_snapshot_scoped_to_user(self, cur):
        expense_id = make_expense(cur)
        assert activity.snapshot(cur, 'expense', expense_id, 999) is None


class TestDiff:
    def test_reports_only_changed_fields(self):
        before = {'amount': '300.00', 'category': 'Grocery', 'note': 'Milk'}
        after = {'amount': '350.00', 'category': 'Grocery', 'note': 'Milk'}

        changes = activity.diff(before, after)
        assert changes == [('Amount', '300.00', '350.00')]

    def test_decimal_and_string_compare_equal(self):
        """A snapshot round-trips through JSON, so an unchanged Decimal must
        not show up as a change."""
        assert activity.diff({'amount': Decimal('300.00')}, {'amount': '300.00'}) == []

    def test_none_renders_as_dash(self):
        changes = activity.diff({'note': None}, {'note': 'Milk'})
        assert changes == [('Note', '—', 'Milk')]

    def test_uses_friendly_field_labels(self):
        changes = activity.diff({'done_by': 'Faisal'}, {'done_by': 'Hassan'})
        assert changes[0][0] == 'Done by'

    def test_handles_empty_snapshots(self):
        assert activity.diff(None, None) == []


class TestLoads:
    def test_parses_json_string(self):
        assert activity.loads('{"a": 1}') == {'a': 1}

    def test_passes_through_dict(self):
        assert activity.loads({'a': 1}) == {'a': 1}

    def test_none_and_garbage_are_safe(self):
        assert activity.loads(None) is None
        assert activity.loads('not json') is None


class TestUndo:
    def _log(self, cur, entity_id, action, before=None, after=None):
        return activity.log_change(cur, 1, 'Hassan', 'expense', entity_id,
                                   action, before=before, after=after)

    def test_undo_delete_restores_the_row(self, cur):
        expense_id = make_expense(cur)
        before = activity.snapshot(cur, 'expense', expense_id, 1)
        cur.execute("DELETE FROM expense WHERE id=%s AND user_id=%s", (expense_id, 1))
        log_id = self._log(cur, expense_id, activity.DELETE, before=before)

        cur.execute(
            "SELECT id, entity_type, entity_id, action, before_json, after_json "
            "FROM activity_log WHERE id=%s", (log_id,)
        )
        entry = cur.fetchone()

        new_id, note = activity.apply_undo(cur, 1, entry)

        assert note is None
        restored = activity.snapshot(cur, 'expense', new_id, 1)
        assert restored['category'] == 'Grocery'
        assert restored['amount'] == '300.00'
        assert restored['done_by'] == 'Faisal'

    def test_undo_update_writes_old_values_back(self, cur):
        expense_id = make_expense(cur)
        before = activity.snapshot(cur, 'expense', expense_id, 1)
        cur.execute(
            "UPDATE expense SET amount=%s, category=%s WHERE id=%s AND user_id=%s",
            ('999.00', 'Fuel', expense_id, 1)
        )
        after = activity.snapshot(cur, 'expense', expense_id, 1)
        log_id = self._log(cur, expense_id, activity.UPDATE, before=before, after=after)

        cur.execute(
            "SELECT id, entity_type, entity_id, action, before_json, after_json "
            "FROM activity_log WHERE id=%s", (log_id,)
        )
        activity.apply_undo(cur, 1, cur.fetchone())

        restored = activity.snapshot(cur, 'expense', expense_id, 1)
        assert restored['amount'] == '300.00'
        assert restored['category'] == 'Grocery'

    def test_undo_create_removes_the_row(self, cur):
        expense_id = make_expense(cur)
        after = activity.snapshot(cur, 'expense', expense_id, 1)
        log_id = self._log(cur, expense_id, activity.CREATE, after=after)

        cur.execute(
            "SELECT id, entity_type, entity_id, action, before_json, after_json "
            "FROM activity_log WHERE id=%s", (log_id,)
        )
        activity.apply_undo(cur, 1, cur.fetchone())

        assert activity.snapshot(cur, 'expense', expense_id, 1) is None

    def test_already_undone_detects_a_restore(self, cur):
        expense_id = make_expense(cur)
        log_id = self._log(cur, expense_id, activity.DELETE, before={'category': 'Grocery'})

        assert activity.already_undone(cur, log_id) is False

        activity.log_change(cur, 1, 'Hassan', 'expense', expense_id,
                            activity.RESTORE, undoes_log_id=log_id)

        # An entry can only be undone once; a second undo would be ambiguous.
        assert activity.already_undone(cur, log_id) is True

    def test_undo_is_scoped_to_the_user(self, cur):
        expense_id = make_expense(cur)
        after = activity.snapshot(cur, 'expense', expense_id, 1)
        log_id = self._log(cur, expense_id, activity.CREATE, after=after)

        cur.execute(
            "SELECT id, entity_type, entity_id, action, before_json, after_json "
            "FROM activity_log WHERE id=%s", (log_id,)
        )
        activity.apply_undo(cur, 999, cur.fetchone())

        # Another account's undo must not delete this household's row.
        assert activity.snapshot(cur, 'expense', expense_id, 1) is not None

    def test_undo_delete_with_missing_receipt_reports_it(self, cur, app):
        """A restored expense must not link to a receipt that is gone."""
        expense_id = make_expense(cur, attachment='user1_gone.pdf')
        before = activity.snapshot(cur, 'expense', expense_id, 1)
        cur.execute("DELETE FROM expense WHERE id=%s AND user_id=%s", (expense_id, 1))
        log_id = self._log(cur, expense_id, activity.DELETE, before=before)

        cur.execute(
            "SELECT id, entity_type, entity_id, action, before_json, after_json "
            "FROM activity_log WHERE id=%s", (log_id,)
        )
        entry = cur.fetchone()

        with app.app_context():
            new_id, note = activity.apply_undo(cur, 1, entry)

        assert note is not None and 'receipt' in note.lower()
        restored = activity.snapshot(cur, 'expense', new_id, 1)
        assert restored['attachment'] is None


class TestLogChange:
    def test_serialises_decimal_and_date(self, cur):
        """Decimals must keep their precision and dates must not blow up
        json.dumps."""
        from datetime import date as date_cls

        log_id = activity.log_change(
            cur, 1, 'Hassan', 'expense', 5, activity.CREATE,
            after={'amount': Decimal('1234.56'), 'date': date_cls(2026, 9, 21)}
        )

        cur.execute("SELECT after_json FROM activity_log WHERE id=%s", (log_id,))
        snap = activity.loads(cur.fetchone()['after_json'])

        assert snap['amount'] == '1234.56'
        assert snap['date'] == '2026-09-21'

    def test_missing_actor_is_recorded_not_dropped(self, cur):
        log_id = activity.log_change(cur, 1, None, 'expense', 5, activity.CREATE, after={})
        cur.execute("SELECT actor FROM activity_log WHERE id=%s", (log_id,))
        assert cur.fetchone()['actor'] == 'Unknown'
