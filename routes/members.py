"""Household members and the "who is using this" profile switcher.

The household shares a single login, so the account tells us nothing about who
actually made a change. These are not real accounts and deliberately have no
passwords — this is attribution for a trusted household, not authentication.
"""

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    current_app, session, flash
)
from auth_utils import login_required

members_bp = Blueprint('members', __name__, url_prefix='/members')


def list_members(cur, user_id):
    """Names of everyone in this household, alphabetically."""
    cur.execute(
        "SELECT id, name FROM household_member WHERE user_id=%s ORDER BY name",
        (user_id,)
    )
    return cur.fetchall()


def member_names(cur, user_id):
    return [row['name'] for row in list_members(cur, user_id)]


def refresh_member_cache(cur, user_id):
    """Cache the roster in the session so the nav costs no query per render.

    Called at login and after any change to the roster. The roster changes
    about once a year, so this is a much better trade than re-querying it on
    every page view.
    """
    names = member_names(cur, user_id)
    session['household_members'] = names

    # Don't leave the session pointing at somebody who is no longer a member.
    if session.get('actor') and session['actor'] not in names:
        session.pop('actor', None)
    return names


@members_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            if request.method == 'POST':
                name = request.form.get('name', '').strip()
                if not name or len(name) > 50:
                    flash("Member name is required (max 50 chars).", "error")
                else:
                    cur.execute(
                        "INSERT IGNORE INTO household_member (user_id, name) VALUES (%s, %s)",
                        (session['user_id'], name)
                    )
                    conn.commit()

            members = list_members(cur, session['user_id'])
            refresh_member_cache(cur, session['user_id'])
    finally:
        conn.close()

    # current_actor is supplied to every template by the context processor.
    return render_template('members.html', members=members)


@members_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute(
                "DELETE FROM household_member WHERE id=%s AND user_id=%s",
                (id, session['user_id'])
            )
            conn.commit()
            refresh_member_cache(cur, session['user_id'])
    finally:
        conn.close()

    return redirect(url_for('members.index'))


@members_bp.route('/switch', methods=['POST'])
@login_required
def switch():
    """Set who is at the keyboard for the rest of this session."""
    name = request.form.get('name', '').strip()

    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            names = member_names(cur, session['user_id'])
    finally:
        conn.close()

    # Only ever store a name that really belongs to this household — this value
    # ends up stamped on the activity log, so it must not be attacker-chosen.
    if name in names:
        session['actor'] = name
    else:
        flash("Unknown household member.", "error")

    return redirect(request.referrer or url_for('dashboard.index'))
