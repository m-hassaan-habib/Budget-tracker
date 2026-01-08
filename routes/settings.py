from flask import Blueprint, render_template, request, redirect, url_for, current_app, session
from datetime import datetime
from auth_utils import login_required

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

@settings_bp.route('/')
@login_required
def index():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("""
                SELECT monthly_limit, total_savings, default_done_by
                FROM setting
                WHERE user_id=%s
                LIMIT 1
            """, (session['user_id'],))
            setting = cur.fetchone()

            current_limit = float(setting['monthly_limit']) if setting else 0
            total_savings = float(setting['total_savings']) if setting else 0
            default_done_by = setting['default_done_by'] if setting else None

        return render_template(
            'settings.html',
            current_limit=current_limit,
            total_savings=total_savings,
            default_done_by=default_done_by
        )
    finally:
        conn.close()


@settings_bp.route('/update', methods=['POST'])
@login_required
def update_limit():
    limit = request.form['limit']
    savings = request.form['savings']
    default_done_by = request.form.get('default_done_by')

    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT id FROM setting WHERE user_id=%s LIMIT 1", (session['user_id'],))
            row = cur.fetchone()

            if not row:
                cur.execute("""
                    INSERT INTO setting (monthly_limit, total_savings, default_done_by, user_id)
                    VALUES (%s, %s, %s, %s)
                """, (limit, savings, default_done_by, session['user_id']))
            else:
                cur.execute("""
                    UPDATE setting
                    SET monthly_limit=%s,
                        total_savings=%s,
                        default_done_by=%s
                    WHERE user_id=%s
                """, (limit, savings, default_done_by, session['user_id']))

            conn.commit()
        return redirect(url_for('settings.index'))
    finally:
        conn.close()


@settings_bp.route('/end-month', methods=['POST'])
@login_required
def end_month():
    now = datetime.now()
    month_str = now.strftime("%Y-%m")

    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM income WHERE user_id=%s", (session['user_id'],))
            total_income = float(cur.fetchone()['total'])
            cur.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM expense WHERE user_id=%s", (session['user_id'],))
            total_expenses = float(cur.fetchone()['total'])
            net_savings = total_income - total_expenses

            cur.execute("SELECT total_savings FROM setting WHERE user_id=%s LIMIT 1", (session['user_id'],))
            setting = cur.fetchone()
            if setting:
                new_savings = float(setting['total_savings']) + net_savings
                cur.execute("UPDATE setting SET total_savings=%s WHERE user_id=%s", (new_savings, session['user_id']))

            cur.execute("SELECT source, amount FROM income WHERE user_id=%s", (session['user_id'],))
            for row in cur.fetchall():
                cur.execute(
                    "INSERT INTO archived_income (source, amount, month, user_id) VALUES (%s, %s, %s, %s)",
                    (row['source'], row['amount'], month_str, session['user_id'])
                )

            cur.execute("SELECT amount, category, note, date FROM expense WHERE user_id=%s", (session['user_id'],))
            for row in cur.fetchall():
                cur.execute(
                    "INSERT INTO archived_expense (amount, category, note, date, month, user_id) VALUES (%s, %s, %s, %s, %s, %s)",
                    (row['amount'], row['category'], row['note'], row['date'], month_str, session['user_id'])
                )

            cur.execute("DELETE FROM income WHERE user_id=%s", (session['user_id'],))
            cur.execute("DELETE FROM expense WHERE user_id=%s", (session['user_id'],))
            conn.commit()
        return redirect(url_for('settings.index'))
    finally:
        conn.close()


@settings_bp.route('/fresh-start', methods=['POST'])
@login_required
def fresh_start():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM archived_income WHERE user_id=%s", (session['user_id'],))
            cur.execute("DELETE FROM archived_expense WHERE user_id=%s", (session['user_id'],))
            cur.execute("DELETE FROM income WHERE user_id=%s", (session['user_id'],))
            cur.execute("DELETE FROM expense WHERE user_id=%s", (session['user_id'],))
            cur.execute("DELETE FROM setting WHERE user_id=%s", (session['user_id'],))
            conn.commit()
        return redirect(url_for('settings.index'))
    finally:
        conn.close()
