from flask import Blueprint, render_template, request, redirect, url_for, current_app
from datetime import date

expenses_bp = Blueprint('expenses', __name__, url_prefix='/expenses')

@expenses_bp.route('/')
def index():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT id, amount, category, note, date FROM expense ORDER BY date DESC")
            expenses = [
                {"id": row['id'], "amount": float(row['amount']), "category": row['category'], "note": row['note'], "date": row['date']}
                for row in cur.fetchall()
            ]
        return render_template('expenses.html', expenses=expenses, current_date=date.today())
    finally:
        conn.close()

@expenses_bp.route('/add', methods=['POST'])
def add_expense():
    amount = request.form['amount']
    category = request.form['category']
    note = request.form.get('note')
    date_str = request.form['date']
    
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO expense (amount, category, note, date) VALUES (%s, %s, %s, %s)",
                (amount, category, note, date_str)
            )
            conn.commit()
        return redirect(url_for('expenses.index'))
    finally:
        conn.close()

@expenses_bp.route('/edit/<int:id>', methods=['POST'])
def edit_expense(id):
    amount = request.form['amount']
    category = request.form['category']
    note = request.form.get('note')
    date_str = request.form['date']
    
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM expense WHERE id = %s", (id,))
            if not cur.fetchone():
                return "Expense not found", 404
            cur.execute(
                "UPDATE expense SET amount = %s, category = %s, note = %s, date = %s WHERE id = %s",
                (amount, category, note, date_str, id)
            )
            conn.commit()
        return redirect(url_for('expenses.index'))
    finally:
        conn.close()

@expenses_bp.route('/delete/<int:id>')
def delete_expense(id):
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM expense WHERE id = %s", (id,))
            conn.commit()
        return redirect(url_for('expenses.index'))
    finally:
        conn.close()