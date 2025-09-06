from flask import Blueprint, render_template, request, redirect, url_for, current_app

income_bp = Blueprint('income', __name__, url_prefix='/income')

@income_bp.route('/')
def index():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT id, source, amount FROM income")
            incomes = [{"id": row['id'], "source": row['source'], "amount": float(row['amount'])} for row in cur.fetchall()]
        return render_template('income.html', incomes=incomes)
    finally:
        conn.close()

@income_bp.route('/add', methods=['POST'])
def add_income():
    source = request.form['source']
    amount = request.form['amount']
    
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO income (source, amount) VALUES (%s, %s)", (source, amount))
            conn.commit()
        return redirect(url_for('income.index'))
    finally:
        conn.close()

@income_bp.route('/edit/<int:id>', methods=['POST'])
def edit_income(id):
    source = request.form['source']
    amount = request.form['amount']
    
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM income WHERE id = %s", (id,))
            if not cur.fetchone():
                return "Income not found", 404
            cur.execute("UPDATE income SET source = %s, amount = %s WHERE id = %s", (source, amount, id))
            conn.commit()
        return redirect(url_for('income.index'))
    finally:
        conn.close()

@income_bp.route('/delete/<int:id>')
def delete_income(id):
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM income WHERE id = %s", (id,))
            conn.commit()
        return redirect(url_for('income.index'))
    finally:
        conn.close()