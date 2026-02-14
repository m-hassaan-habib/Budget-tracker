from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, redirect, url_for, current_app, session, flash
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

            # Current month snapshot for End Month preview
            # Expected income
            cur.execute("SELECT COALESCE(SUM(amount),0) AS total, COUNT(*) AS count FROM income WHERE user_id=%s", (session['user_id'],))
            inc_row = cur.fetchone()
            month_expected_income = float(inc_row['total'])
            income_count = int(inc_row['count'])

            # Expenses
            cur.execute("SELECT COALESCE(SUM(amount),0) AS total, COUNT(*) AS count FROM expense WHERE user_id=%s", (session['user_id'],))
            exp_row = cur.fetchone()
            month_expenses = float(exp_row['total'])
            expense_count = int(exp_row['count'])

            # Actual income (from expenses grouped by done_by)
            cur.execute("""
                SELECT done_by, SUM(amount) AS total
                FROM expense WHERE user_id=%s GROUP BY done_by
            """, (session['user_id'],))
            month_actual_income = sum(float(row['total']) for row in cur.fetchall())

            month_net = month_expected_income - month_expenses
            month_income_variance = month_expected_income - month_actual_income

            # Count archived months
            cur.execute("""
                SELECT COUNT(DISTINCT month) AS cnt FROM (
                    SELECT month FROM archived_income WHERE user_id=%s
                    UNION
                    SELECT month FROM archived_expense WHERE user_id=%s
                ) AS months
            """, (session['user_id'], session['user_id']))
            archived_months = int(cur.fetchone()['cnt'])

        return render_template(
            'settings.html',
            current_limit=current_limit,
            total_savings=total_savings,
            default_done_by=default_done_by,
            month_expected_income=month_expected_income,
            month_actual_income=month_actual_income,
            month_income_variance=month_income_variance,
            month_expenses=month_expenses,
            month_net=month_net,
            income_count=income_count,
            expense_count=expense_count,
            archived_months=archived_months,
        )
    finally:
        conn.close()


@settings_bp.route('/update', methods=['POST'])
@login_required
def update_limit():
    limit = request.form.get('limit', '')
    savings = request.form.get('savings', '')
    default_done_by = request.form.get('default_done_by', '').strip()

    try:
        limit_val = Decimal(limit)
        savings_val = Decimal(savings)
        if limit_val < 0 or savings_val < Decimal('-99999999.99'):
            raise ValueError
        if limit_val > Decimal('99999999.99') or savings_val > Decimal('99999999.99'):
            raise ValueError
    except (InvalidOperation, ValueError):
        flash("Please enter valid numeric values.", "error")
        return redirect(url_for('settings.index'))

    if default_done_by and len(default_done_by) > 50:
        flash("Default done-by must be 50 characters or less.", "error")
        return redirect(url_for('settings.index'))

    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT id FROM setting WHERE user_id=%s LIMIT 1", (session['user_id'],))
            row = cur.fetchone()

            if not row:
                cur.execute("""
                    INSERT INTO setting (monthly_limit, total_savings, default_done_by, user_id)
                    VALUES (%s, %s, %s, %s)
                """, (str(limit_val), str(savings_val), default_done_by or None, session['user_id']))
            else:
                cur.execute("""
                    UPDATE setting
                    SET monthly_limit=%s,
                        total_savings=%s,
                        default_done_by=%s
                    WHERE user_id=%s
                """, (str(limit_val), str(savings_val), default_done_by or None, session['user_id']))

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

            cur.execute("SELECT amount, category, note, date, done_by FROM expense WHERE user_id=%s", (session['user_id'],))
            for row in cur.fetchall():
                cur.execute(
                    "INSERT INTO archived_expense (amount, category, note, date, month, user_id, done_by) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (row['amount'], row['category'], row['note'], row['date'], month_str, session['user_id'], row['done_by'])
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
