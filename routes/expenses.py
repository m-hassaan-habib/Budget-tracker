import os
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, current_app, session
from werkzeug.utils import secure_filename
from auth_utils import login_required

expenses_bp = Blueprint('expenses', __name__, url_prefix='/expenses')

ALLOWED_ATTACH_EXT = {"pdf", "png", "jpg", "jpeg", "doc", "JPG"}

def allowed_attachment(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_ATTACH_EXT

@expenses_bp.route('/')
@login_required
def index():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("""
                SELECT id, amount, category, note, date, attachment, done_by
                FROM expense
                WHERE user_id=%s
                ORDER BY date DESC
            """, (session['user_id'],))
            expenses = cur.fetchall()

            cur.execute("""
                SELECT default_done_by
                FROM setting
                WHERE user_id=%s
                LIMIT 1
            """, (session['user_id'],))
            row = cur.fetchone()
            default_done_by = row['default_done_by'] if row else None

        return render_template(
            'expenses.html',
            expenses=expenses,
            current_date=date.today(),
            default_done_by=default_done_by
        )
    finally:
        conn.close()


@expenses_bp.route('/add', methods=['POST'])
@login_required
def add_expense():
    amount = request.form['amount']
    category = request.form['category']
    note = request.form.get('note')
    date_str = request.form['date']
    done_by = request.form['done_by']

    file = request.files.get('attachment')
    filename = None
    if file and file.filename and allowed_attachment(file.filename):
        filename = secure_filename(file.filename)
        filename = f"user{session['user_id']}_{filename}"
        os.makedirs(current_app.config['RECEIPT_FOLDER'], exist_ok=True)
        file.save(os.path.join(current_app.config['RECEIPT_FOLDER'], filename))

    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO expense (amount, category, note, date, user_id, attachment, done_by) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (amount, category, note, date_str, session['user_id'], filename, done_by)
            )
            conn.commit()
        return redirect(url_for('expenses.index'))
    finally:
        conn.close()


@expenses_bp.route('/edit/<int:id>', methods=['POST'])
@login_required
def edit_expense(id):
    amount = request.form['amount']
    category = request.form['category']
    note = request.form.get('note')
    date_str = request.form['date']
    done_by = request.form['done_by']

    file = request.files.get('attachment')
    new_filename = None
    if file and file.filename and allowed_attachment(file.filename):
        new_filename = secure_filename(file.filename)
        new_filename = f"user{session['user_id']}_{new_filename}"
        os.makedirs(current_app.config['RECEIPT_FOLDER'], exist_ok=True)
        file.save(os.path.join(current_app.config['RECEIPT_FOLDER'], new_filename))

    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT attachment FROM expense WHERE id=%s AND user_id=%s", (id, session['user_id']))
            row = cur.fetchone()
            if not row:
                return "Expense not found", 404
            old_attachment = row['attachment']

            if new_filename:
                cur.execute(
                    "UPDATE expense SET amount=%s, category=%s, note=%s, date=%s, attachment=%s, done_by=%s WHERE id=%s AND user_id=%s",
                    (amount, category, note, date_str, new_filename, done_by, id, session['user_id'])
                )
            else:
                cur.execute(
                    "UPDATE expense SET amount=%s, category=%s, note=%s, date=%s, done_by=%s WHERE id=%s AND user_id=%s",
                    (amount, category, note, date_str, done_by, id, session['user_id'])
                )
            conn.commit()
    finally:
        conn.close()

    return redirect(url_for('expenses.index'))


@expenses_bp.route('/delete/<int:id>')
@login_required
def delete_expense(id):
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM expense WHERE id=%s AND user_id=%s", (id, session['user_id']))
            conn.commit()
        return redirect(url_for('expenses.index'))
    finally:
        conn.close()


@expenses_bp.route("/view/<int:id>")
@login_required
def view_expense(id):
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute(
                "SELECT id, amount, category, note, date, attachment, done_by "
                "FROM expense WHERE id=%s AND user_id=%s",
                (id, session['user_id'])
            )
            expense = cur.fetchone()

        if not expense:
            return "Expense not found", 404

        return render_template("expenses/view.html", expense=expense)

    finally:
        conn.close()
