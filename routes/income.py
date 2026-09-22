from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, redirect, url_for, current_app, session, flash
from auth_utils import login_required, current_actor
from months import format_month, month_bounds, month_options, parse_month
import activity

income_bp = Blueprint('income', __name__, url_prefix='/income')

@income_bp.route('/')
@login_required
def index():
    # Both halves of this page -- manual sources and the expense-derived
    # contributor split -- are date-backed, so one month scopes them together.
    month_filter = request.args.get('month', '')
    if not parse_month(month_filter):
        month_filter = ''
    month_range = month_bounds(month_filter) if month_filter else None

    def scoped(query, params):
        if not month_range:
            return query, params
        return query + " AND date BETWEEN %s AND %s", params + list(month_range)

    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            # Check income mode setting
            cur.execute("SELECT use_automated_income FROM setting WHERE user_id=%s LIMIT 1", (session['user_id'],))
            setting = cur.fetchone()
            use_automated_income = bool(setting['use_automated_income']) if setting else False

            # Manual income (user-entered)
            manual_query, manual_params = scoped(
                "SELECT id, source, amount, date FROM income WHERE user_id=%s",
                [session['user_id']]
            )
            cur.execute(manual_query + " ORDER BY amount DESC", tuple(manual_params))
            incomes = [{"id": row['id'], "source": row['source'],
                        "amount": float(row['amount']), "date": row['date']}
                       for row in cur.fetchall()]
            total_manual_income = sum(i['amount'] for i in incomes)

            # Automated income (calculated from expenses grouped by done_by)
            automated_query, automated_params = scoped(
                "SELECT done_by, SUM(amount) AS total FROM expense WHERE user_id=%s",
                [session['user_id']]
            )
            cur.execute(automated_query + " GROUP BY done_by", tuple(automated_params))
            income_by_person = {row['done_by']: float(row['total']) for row in cur.fetchall()}
            total_automated_income = sum(income_by_person.values())

            months = month_options(cur, session['user_id'], month_filter)

        return render_template(
            'income.html',
            use_automated_income=use_automated_income,
            incomes=incomes,
            total_manual_income=total_manual_income,
            income_by_person=income_by_person,
            total_automated_income=total_automated_income,
            month_filter=month_filter,
            month_display=format_month(month_filter) if month_filter else None,
            month_options=months,
        )
    finally:
        conn.close()


def parse_income_date(form):
    """The month an income belongs to.

    Undated rows would drop out of every month filter, so a date is required
    here even though the column is nullable for rows predating this.
    """
    date_str = form.get('date', '')
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return None
    return date_str


@income_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_income():
    if request.method == 'GET':
        return render_template('income/add.html', current_date=date.today().isoformat())

    source = request.form.get('source', '').strip()
    amount = request.form.get('amount', '')

    if not source or len(source) > 100:
        flash("Source name is required (max 100 chars).", "error")
        return redirect(url_for('income.add_income'))

    try:
        amount_val = Decimal(amount)
        if amount_val < 0 or amount_val > Decimal('99999999.99'):
            raise ValueError
    except (InvalidOperation, ValueError):
        flash("Please enter a valid positive amount.", "error")
        return redirect(url_for('income.add_income'))

    date_str = parse_income_date(request.form)
    if not date_str:
        flash("Please enter a valid date (YYYY-MM-DD).", "error")
        return redirect(url_for('income.add_income'))

    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("INSERT INTO income (source, amount, date, user_id) VALUES (%s, %s, %s, %s)",
                        (source, str(amount_val), date_str, session['user_id']))
            activity.log_created(cur, session['user_id'], current_actor(), 'income', cur.lastrowid)
            conn.commit()
        return redirect(url_for('income.index'))
    finally:
        conn.close()


@income_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_income(id):
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT id, source, amount, date FROM income WHERE id=%s AND user_id=%s", (id, session['user_id']))
            income = cur.fetchone()
            if not income:
                return "Income not found", 404

            if request.method == 'GET':
                return render_template('income/edit.html', income=income,
                                       current_date=date.today().isoformat())

            source = request.form.get('source', '').strip()
            amount = request.form.get('amount', '')

            if not source or len(source) > 100:
                flash("Source name is required (max 100 chars).", "error")
                return redirect(url_for('income.edit_income', id=id))

            try:
                amount_val = Decimal(amount)
                if amount_val < 0 or amount_val > Decimal('99999999.99'):
                    raise ValueError
            except (InvalidOperation, ValueError):
                flash("Please enter a valid positive amount.", "error")
                return redirect(url_for('income.edit_income', id=id))

            date_str = parse_income_date(request.form)
            if not date_str:
                flash("Please enter a valid date (YYYY-MM-DD).", "error")
                return redirect(url_for('income.edit_income', id=id))

            before = activity.snapshot(cur, 'income', id, session['user_id'])
            cur.execute("UPDATE income SET source=%s, amount=%s, date=%s WHERE id=%s AND user_id=%s",
                        (source, str(amount_val), date_str, id, session['user_id']))
            after = activity.snapshot(cur, 'income', id, session['user_id'])
            activity.log_change(cur, session['user_id'], current_actor(), 'income', id,
                                activity.UPDATE, before=before, after=after)
            conn.commit()
        return redirect(url_for('income.index'))
    finally:
        conn.close()


@income_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_income(id):
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            before = activity.snapshot(cur, 'income', id, session['user_id'])
            cur.execute("DELETE FROM income WHERE id=%s AND user_id=%s", (id, session['user_id']))
            if before:
                activity.log_change(cur, session['user_id'], current_actor(), 'income', id,
                                    activity.DELETE, before=before)
            conn.commit()
        return redirect(url_for('income.index'))
    finally:
        conn.close()
