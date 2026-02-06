from flask import Blueprint, render_template, request, redirect, url_for, current_app, session
from auth_utils import login_required

categories_bp = Blueprint('categories', __name__, url_prefix='/categories')

@categories_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            if request.method == 'POST':
                name = request.form['name'].strip()
                if name:
                    cur.execute(
                        "INSERT IGNORE INTO categories (user_id, name) VALUES (%s, %s)",
                        (session['user_id'], name)
                    )
                    conn.commit()

            cur.execute("SELECT id, name FROM categories WHERE user_id=%s ORDER BY name", (session['user_id'],))
            rows = cur.fetchall()
    finally:
        conn.close()
    return render_template('categories.html', categories=rows)


@categories_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM categories WHERE id=%s AND user_id=%s", (id, session['user_id']))
            conn.commit()
    finally:
        conn.close()
    return redirect(url_for('categories.index'))
