"""Change tracking: who changed what, when, and how to put it back.

Every mutation stores a full before/after snapshot of the row rather than a
computed diff. Diffs are derived at read time by comparing the two, and undo
works because the whole row is still there -- which a stored diff alone could
never give you for a delete.

The one rule that matters: `log_change` takes the *caller's cursor*, so the log
entry commits or rolls back in the same transaction as the change it describes.
Write it on a separate connection and you eventually get an edit with no log
entry, and a trail you cannot trust is worse than no trail at all.
"""

import json
from datetime import date, datetime
from decimal import Decimal

CREATE = 'create'
UPDATE = 'update'
DELETE = 'delete'
RESTORE = 'restore'

# Which columns make up a snapshot, and where to put them back on an undo.
# `columns` is deliberately explicit rather than SELECT * so that adding a
# column to a table can't silently change what undo writes.
ENTITIES = {
    'expense': {
        'table': 'expense',
        'columns': ('amount', 'category', 'note', 'date', 'attachment', 'done_by'),
        'label': 'Expense',
    },
    'income': {
        'table': 'income',
        'columns': ('source', 'amount'),
        'label': 'Income',
    },
    'setting': {
        'table': 'setting',
        'columns': ('monthly_limit', 'total_savings', 'default_done_by', 'use_automated_income'),
        'label': 'Settings',
    },
    'category': {
        'table': 'categories',
        'columns': ('name', 'icon', 'color'),
        'label': 'Category',
    },
}

# Friendlier field names for the feed.
FIELD_LABELS = {
    'amount': 'Amount',
    'category': 'Category',
    'note': 'Note',
    'date': 'Date',
    'attachment': 'Receipt',
    'done_by': 'Done by',
    'source': 'Source',
    'monthly_limit': 'Monthly limit',
    'total_savings': 'Savings',
    'default_done_by': 'Default person',
    'use_automated_income': 'Automated income',
    'name': 'Name',
    'icon': 'Icon',
    'color': 'Colour',
}


def _encode(value):
    """Make a database row JSON-safe without losing precision."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _dumps(snapshot):
    if snapshot is None:
        return None
    return json.dumps({k: _encode(v) for k, v in snapshot.items()})


def loads(raw):
    """Read a snapshot back. MySQL drivers hand JSON columns back as either
    a str or an already-decoded dict depending on version."""
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode('utf-8')
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def snapshot(cur, entity_type, entity_id, user_id):
    """Capture a row exactly as it stands right now."""
    spec = ENTITIES[entity_type]
    columns = ', '.join(spec['columns'])
    cur.execute(
        f"SELECT {columns} FROM {spec['table']} WHERE id=%s AND user_id=%s",
        (entity_id, user_id)
    )
    return cur.fetchone()


def log_change(cur, user_id, actor, entity_type, entity_id, action,
               before=None, after=None, undoes_log_id=None):
    """Record one change on the caller's cursor, inside their transaction."""
    cur.execute(
        """
        INSERT INTO activity_log
            (user_id, actor, entity_type, entity_id, action,
             before_json, after_json, undoes_log_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, actor or 'Unknown', entity_type, entity_id, action,
         _dumps(before), _dumps(after), undoes_log_id)
    )
    return cur.lastrowid


def log_created(cur, user_id, actor, entity_type, entity_id):
    """Convenience wrapper: snapshot the freshly written row and log it."""
    after = snapshot(cur, entity_type, entity_id, user_id)
    return log_change(cur, user_id, actor, entity_type, entity_id, CREATE, after=after)


def diff(before, after):
    """Fields that actually changed, as (label, old, new) triples.

    Values are compared as strings because a snapshot round-trips through
    JSON: a Decimal written as "300.00" must compare equal to the "300.00"
    read back, and unchanged fields must not show up as noise in the feed.
    """
    before = before or {}
    after = after or {}
    changes = []
    for field in list(before.keys()) + [k for k in after if k not in before]:
        old, new = before.get(field), after.get(field)
        if _as_text(old) != _as_text(new):
            changes.append((FIELD_LABELS.get(field, field), _display(old), _display(new)))
    return changes


def _as_text(value):
    return '' if value is None else str(value)


def _display(value):
    if value is None or value == '':
        return '—'
    return str(value)


def already_undone(cur, log_id):
    """An entry can only be undone once; a second undo would be ambiguous."""
    cur.execute("SELECT id FROM activity_log WHERE undoes_log_id=%s LIMIT 1", (log_id,))
    return cur.fetchone() is not None


def apply_undo(cur, user_id, entry):
    """Reverse one logged change.

    Undo is a forward event, never an erasure: the caller logs a `restore`
    entry pointing back at this one, so the history still shows that
    something was reverted and by whom.

    Returns (entity_id, note) where note flags anything that couldn't be put
    back exactly -- currently only a receipt whose file is gone.
    """
    spec = ENTITIES[entry['entity_type']]
    table = spec['table']
    before = loads(entry['before_json'])
    action = entry['action']
    note = None

    if action == CREATE:
        cur.execute(
            f"DELETE FROM {table} WHERE id=%s AND user_id=%s",
            (entry['entity_id'], user_id)
        )
        return entry['entity_id'], note

    if before is None:
        return None, "Nothing recorded to restore."

    before = dict(before)
    if 'attachment' in before and before.get('attachment'):
        if not _receipt_exists(before['attachment']):
            before['attachment'] = None
            note = "The receipt file is no longer on disk, so it was not restored."

    if action == UPDATE:
        assignments = ', '.join(f"{c}=%s" for c in spec['columns'])
        values = [before.get(c) for c in spec['columns']]
        cur.execute(
            f"UPDATE {table} SET {assignments} WHERE id=%s AND user_id=%s",
            (*values, entry['entity_id'], user_id)
        )
        return entry['entity_id'], note

    if action == DELETE:
        columns = ', '.join(spec['columns'])
        placeholders = ', '.join(['%s'] * len(spec['columns']))
        values = [before.get(c) for c in spec['columns']]
        cur.execute(
            f"INSERT INTO {table} ({columns}, user_id) VALUES ({placeholders}, %s)",
            (*values, user_id)
        )
        return cur.lastrowid, note

    return None, "This entry can't be undone."


def _receipt_exists(filename):
    import os
    from flask import current_app
    folder = current_app.config.get('RECEIPT_FOLDER')
    if not folder:
        return False
    return os.path.isfile(os.path.join(folder, filename))
