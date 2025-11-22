from flask import Blueprint, render_template, request, redirect, url_for, current_app, session
from auth_utils import login_required

income_bp = Blueprint('income', __name__, url_prefix='/income')

@income_bp.route('/')
@login_required
def index():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT id, source, amount FROM income WHERE user_id=%s", (session['user_id'],))
            incomes = [{"id": row['id'], "source": row['source'], "amount": float(row['amount'])} for row in cur.fetchall()]
        return render_template('income.html', incomes=incomes)
    finally:
        conn.close()


@income_bp.route('/add', methods=['POST'])
@login_required
def add_income():
    source = request.form['source']
    amount = request.form['amount']

    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO income (source, amount, user_id) VALUES (%s, %s, %s)", (source, amount, session['user_id']))
            conn.commit()
        return redirect(url_for('income.index'))
    finally:
        conn.close()


@income_bp.route('/edit/<int:id>', methods=['POST'])
@login_required
def edit_income(id):
    source = request.form['source']
    amount = request.form['amount']

    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT id FROM income WHERE id=%s AND user_id=%s", (id, session['user_id']))
            if not cur.fetchone():
                return "Income not found", 404
            cur.execute("UPDATE income SET source=%s, amount=%s WHERE id=%s AND user_id=%s", (source, amount, id, session['user_id']))
            conn.commit()
        return redirect(url_for('income.index'))
    finally:
        conn.close()


@income_bp.route('/delete/<int:id>')
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
