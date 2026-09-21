from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, redirect, url_for, current_app, session, flash
from datetime import datetime
from auth_utils import login_required, current_actor
from months import available_months
import activity

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

@settings_bp.route('/')
@login_required
def index():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("""
                SELECT monthly_limit, total_savings, default_done_by, use_automated_income
                FROM setting
                WHERE user_id=%s
                LIMIT 1
            """, (session['user_id'],))
            setting = cur.fetchone()

            current_limit = float(setting['monthly_limit']) if setting else 0
            total_savings = float(setting['total_savings']) if setting else 0
            default_done_by = setting['default_done_by'] if setting else None
            use_automated_income = bool(setting['use_automated_income']) if setting else False

            # Manual income (user-entered)
            cur.execute("SELECT COALESCE(SUM(amount),0) AS total, COUNT(*) AS count FROM income WHERE user_id=%s", (session['user_id'],))
            inc_row = cur.fetchone()
            month_manual_income = float(inc_row['total'])
            income_count = int(inc_row['count'])

            # Expenses
            cur.execute("SELECT COALESCE(SUM(amount),0) AS total, COUNT(*) AS count FROM expense WHERE user_id=%s", (session['user_id'],))
            exp_row = cur.fetchone()
            month_expenses = float(exp_row['total'])
            expense_count = int(exp_row['count'])

            # Automated income (from expenses grouped by done_by)
            cur.execute("""
                SELECT done_by, SUM(amount) AS total
                FROM expense WHERE user_id=%s GROUP BY done_by
            """, (session['user_id'],))
            automated_income_by_person = {row['done_by']: float(row['total']) for row in cur.fetchall()}
            month_automated_income = sum(automated_income_by_person.values())

            # Use the appropriate income based on toggle
            month_income = month_automated_income if use_automated_income else month_manual_income
            month_net = month_income - month_expenses

            # How many months this household has any record of.
            archived_months = len(available_months(cur, session['user_id']))

        return render_template(
            'settings.html',
            current_limit=current_limit,
            total_savings=total_savings,
            default_done_by=default_done_by,
            use_automated_income=use_automated_income,
            month_manual_income=month_manual_income,
            month_automated_income=month_automated_income,
            month_income=month_income,
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
    use_automated_income = request.form.get('use_automated_income') == '1'

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
                    INSERT INTO setting (monthly_limit, total_savings, default_done_by, use_automated_income, user_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (str(limit_val), str(savings_val), default_done_by or None, 1 if use_automated_income else 0, session['user_id']))
                activity.log_created(cur, session['user_id'], current_actor(), 'setting', cur.lastrowid)
            else:
                # A changed limit or savings figure silently moves every number
                # on the dashboard, so it belongs in the trail.
                before = activity.snapshot(cur, 'setting', row['id'], session['user_id'])
                cur.execute("""
                    UPDATE setting
                    SET monthly_limit=%s,
                        total_savings=%s,
                        default_done_by=%s,
                        use_automated_income=%s
                    WHERE user_id=%s
                """, (str(limit_val), str(savings_val), default_done_by or None, 1 if use_automated_income else 0, session['user_id']))
                after = activity.snapshot(cur, 'setting', row['id'], session['user_id'])
                activity.log_change(cur, session['user_id'], current_actor(), 'setting', row['id'],
                                    activity.UPDATE, before=before, after=after)

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
            cur.execute("DELETE FROM income WHERE user_id=%s", (session['user_id'],))
            cur.execute("DELETE FROM expense WHERE user_id=%s", (session['user_id'],))
            cur.execute("DELETE FROM setting WHERE user_id=%s", (session['user_id'],))
            cur.execute("DELETE FROM activity_log WHERE user_id=%s", (session['user_id'],))

            # The retired archive tables are kept as a migration safety net and
            # are no longer read by the app; clear them too if they're present
            # so "fresh start" really does leave nothing behind.
            for table in ("archived_income_backup", "archived_expense_backup"):
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = DATABASE() AND table_name = %s",
                    (table,)
                )
                if cur.fetchone()[0]:
                    cur.execute(f"DELETE FROM {table} WHERE user_id=%s", (session['user_id'],))

            conn.commit()
        return redirect(url_for('settings.index'))
    finally:
        conn.close()
