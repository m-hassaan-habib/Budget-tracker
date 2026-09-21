from functools import wraps
from flask import session, redirect, url_for, current_app

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return fn(*args, **kwargs)
    return wrapper


def current_actor():
    """Which household member is at the keyboard right now.

    The household shares one login, so session['user_id'] identifies the
    account, not the person. The nav profile switcher sets session['actor'];
    until somebody picks, fall back to the account's saved default_done_by.
    Returns None when neither is set, so callers can prompt rather than
    attribute a change to the wrong person.
    """
    actor = session.get('actor')
    if actor:
        return actor

    if 'user_id' not in session or current_app.db_pool is None:
        return None

    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute(
                "SELECT default_done_by FROM setting WHERE user_id=%s LIMIT 1",
                (session['user_id'],)
            )
            row = cur.fetchone()
    finally:
        conn.close()

    default = row.get('default_done_by') if row else None
    # default_done_by is nullable, and whatever lands here gets stamped on the
    # activity log and stored in the session -- only accept a real name.
    if isinstance(default, str) and default:
        session['actor'] = default
        return default
    return None
