from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, redirect, url_for, current_app, session, flash
from auth_utils import login_required

income_bp = Blueprint('income', __name__, url_prefix='/income')

@income_bp.route('/')
@login_required
def index():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            # Expected income (manually entered)
            cur.execute("SELECT id, source, amount FROM income WHERE user_id=%s ORDER BY amount DESC", (session['user_id'],))
            incomes = [{"id": row['id'], "source": row['source'], "amount": float(row['amount'])} for row in cur.fetchall()]
            total_expected_income = sum(i['amount'] for i in incomes)

            # Actual income (calculated from expenses grouped by done_by)
            cur.execute("""
                SELECT done_by, SUM(amount) AS total
                FROM expense WHERE user_id=%s GROUP BY done_by
            """, (session['user_id'],))
            actual_income_by_person = {row['done_by']: float(row['total']) for row in cur.fetchall()}
            total_actual_income = sum(actual_income_by_person.values())

            # Variance between expected and actual
            income_variance = total_expected_income - total_actual_income

        return render_template(
            'income.html',
            incomes=incomes,
            total_expected_income=total_expected_income,
            actual_income_by_person=actual_income_by_person,
            total_actual_income=total_actual_income,
            income_variance=income_variance,
        )
    finally:
        conn.close()


@income_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_income():
    if request.method == 'GET':
        return render_template('income/add.html')

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

    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO income (source, amount, user_id) VALUES (%s, %s, %s)", (source, str(amount_val), session['user_id']))
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
            cur.execute("SELECT id, source, amount FROM income WHERE id=%s AND user_id=%s", (id, session['user_id']))
            income = cur.fetchone()
            if not income:
                return "Income not found", 404

            if request.method == 'GET':
                return render_template('income/edit.html', income=income)

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

            cur.execute("UPDATE income SET source=%s, amount=%s WHERE id=%s AND user_id=%s", (source, str(amount_val), id, session['user_id']))
            conn.commit()
        return redirect(url_for('income.index'))
    finally:
        conn.close()


@income_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_income(id):
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM income WHERE id=%s AND user_id=%s", (id, session['user_id']))
            conn.commit()
        return redirect(url_for('income.index'))
    finally:
        conn.close()
