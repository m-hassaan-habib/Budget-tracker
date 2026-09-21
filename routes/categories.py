from flask import Blueprint, render_template, request, redirect, url_for, current_app, session, flash
from auth_utils import login_required, current_actor
import activity
from defaults import FALLBACK_ICON, FALLBACK_COLOR

categories_bp = Blueprint('categories', __name__, url_prefix='/categories')

# How far back "most used" looks when building the quick-entry chips.
RECENT_WINDOW_DAYS = 90


def list_categories(cur, user_id):
    """Every category for this user, with presentation defaults filled in.

    This is the single source of truth for the category picker. It used to be
    a 57-option block hardcoded in two templates.
    """
    cur.execute(
        "SELECT id, name, icon, color FROM categories WHERE user_id=%s ORDER BY name",
        (user_id,)
    )
    rows = cur.fetchall()
    for row in rows:
        row['icon'] = row.get('icon') or FALLBACK_ICON
        row['color'] = row.get('color') or FALLBACK_COLOR
    return rows


def top_categories(cur, user_id, limit=8):
    """The categories this household actually reaches for, most-used first.

    Drives the one-click chips above the quick-entry field, which is what
    turns a 57-item dropdown into a single click for the common case.
    """
    cur.execute(
        """
        SELECT e.category AS name,
               COALESCE(c.icon, %s) AS icon,
               COALESCE(c.color, %s) AS color,
               COUNT(*) AS uses
        FROM expense e
        LEFT JOIN categories c
               ON c.user_id = e.user_id AND c.name = e.category
        WHERE e.user_id = %s
          AND e.date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        GROUP BY e.category, c.icon, c.color
        ORDER BY uses DESC, e.category ASC
        LIMIT %s
        """,
        (FALLBACK_ICON, FALLBACK_COLOR, user_id, RECENT_WINDOW_DAYS, limit)
    )
    return cur.fetchall()


def seed_default_categories(cur, user_id):
    """Give a brand-new account the standard category list."""
    from defaults import DEFAULT_CATEGORIES
    for name, icon, color in DEFAULT_CATEGORIES:
        cur.execute(
            "INSERT IGNORE INTO categories (user_id, name, icon, color) VALUES (%s, %s, %s, %s)",
            (user_id, name, icon, color)
        )


@categories_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            if request.method == 'POST':
                name = request.form.get('name', '').strip()
                if not name or len(name) > 50:
                    flash("Category name is required (max 50 chars).", "error")
                else:
                    cur.execute(
                        "INSERT IGNORE INTO categories (user_id, name, icon, color) "
                        "VALUES (%s, %s, %s, %s)",
                        (session['user_id'], name, FALLBACK_ICON, FALLBACK_COLOR)
                    )
                    if cur.rowcount:
                        activity.log_created(cur, session['user_id'], current_actor(),
                                             'category', cur.lastrowid)
                    conn.commit()

            rows = list_categories(cur, session['user_id'])
    finally:
        conn.close()
    return render_template('categories.html', categories=rows)


@categories_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            before = activity.snapshot(cur, 'category', id, session['user_id'])
            cur.execute("DELETE FROM categories WHERE id=%s AND user_id=%s", (id, session['user_id']))
            if before:
                activity.log_change(cur, session['user_id'], current_actor(), 'category', id,
                                    activity.DELETE, before=before)
            conn.commit()
    finally:
        conn.close()
    return redirect(url_for('categories.index'))
