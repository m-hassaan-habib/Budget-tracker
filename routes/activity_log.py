"""The Track tab: what changed, when, by whom -- and how to put it back."""

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    current_app, session, flash
)
from auth_utils import login_required, current_actor
import activity

track_bp = Blueprint('track', __name__, url_prefix='/track')

PAGE_SIZE = 100


def _decorate(row):
    """Attach the computed diff and a human label to a log row."""
    before = activity.loads(row['before_json'])
    after = activity.loads(row['after_json'])
    row['before'] = before
    row['after'] = after
    row['changes'] = activity.diff(before, after) if row['action'] == activity.UPDATE else []
    row['entity_label'] = activity.ENTITIES.get(row['entity_type'], {}).get(
        'label', row['entity_type'].title()
    )
    # A one-line summary of what the row was, for create/delete entries.
    snap = after or before or {}
    row['summary'] = snap.get('category') or snap.get('source') or snap.get('name') or ''
    row['amount'] = snap.get('amount')
    return row


def fetch_entries(cur, user_id, entity_type=None, actor=None, action=None,
                  entity_id=None, limit=PAGE_SIZE):
    query = """
        SELECT a.id, a.actor, a.entity_type, a.entity_id, a.action,
               a.before_json, a.after_json, a.undoes_log_id, a.created_at,
               (SELECT COUNT(*) FROM activity_log u WHERE u.undoes_log_id = a.id) AS undone
        FROM activity_log a
        WHERE a.user_id = %s
    """
    params = [user_id]

    if entity_type:
        query += " AND a.entity_type = %s"
        params.append(entity_type)
    if actor:
        query += " AND a.actor = %s"
        params.append(actor)
    if action:
        query += " AND a.action = %s"
        params.append(action)
    if entity_id is not None:
        query += " AND a.entity_id = %s"
        params.append(entity_id)

    query += " ORDER BY a.created_at DESC, a.id DESC LIMIT %s"
    params.append(limit)

    cur.execute(query, tuple(params))
    return [_decorate(row) for row in cur.fetchall()]


@track_bp.route('/')
@login_required
def index():
    entity_type = request.args.get('entity', '')
    actor = request.args.get('actor', '')
    action = request.args.get('action', '')

    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            entries = fetch_entries(
                cur, session['user_id'],
                entity_type=entity_type or None,
                actor=actor or None,
                action=action or None,
            )
            cur.execute(
                "SELECT DISTINCT actor FROM activity_log WHERE user_id=%s ORDER BY actor",
                (session['user_id'],)
            )
            actors = [r['actor'] for r in cur.fetchall()]
    finally:
        conn.close()

    # Group by calendar day so the feed reads as a diary.
    days = []
    for entry in entries:
        day = entry['created_at'].date()
        if not days or days[-1]['day'] != day:
            days.append({'day': day, 'entries': []})
        days[-1]['entries'].append(entry)

    return render_template(
        'track.html',
        days=days,
        total=len(entries),
        actors=actors,
        entity_types=sorted(activity.ENTITIES),
        entity_filter=entity_type,
        actor_filter=actor,
        action_filter=action,
    )


@track_bp.route('/undo/<int:log_id>', methods=['POST'])
@login_required
def undo(log_id):
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute(
                "SELECT id, entity_type, entity_id, action, before_json, after_json "
                "FROM activity_log WHERE id=%s AND user_id=%s",
                (log_id, session['user_id'])
            )
            entry = cur.fetchone()

            if not entry:
                return "Activity entry not found", 404

            if entry['action'] == activity.RESTORE:
                flash("That entry is itself an undo -- undo the original instead.", "error")
                return redirect(url_for('track.index'))

            if activity.already_undone(cur, log_id):
                flash("That change has already been undone.", "error")
                return redirect(url_for('track.index'))

            entity_id, note = activity.apply_undo(cur, session['user_id'], entry)

            if entity_id is None:
                flash(note or "That change can't be undone.", "error")
                return redirect(url_for('track.index'))

            # Undo is a forward event: the original entry stays, and this
            # records that it was reverted and by whom.
            after = activity.snapshot(cur, entry['entity_type'], entity_id, session['user_id'])
            activity.log_change(
                cur, session['user_id'], current_actor(), entry['entity_type'],
                entity_id, activity.RESTORE,
                before=activity.loads(entry['after_json']),
                after=after,
                undoes_log_id=log_id,
            )
            conn.commit()
    finally:
        conn.close()

    flash(note or "Change undone.", "error" if note else "success")
    return redirect(request.referrer or url_for('track.index'))
