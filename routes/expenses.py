import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, redirect, url_for, current_app, session, flash
from werkzeug.utils import secure_filename
from auth_utils import login_required

expenses_bp = Blueprint('expenses', __name__, url_prefix='/expenses')

ALLOWED_ATTACH_EXT = {"pdf", "png", "jpg", "jpeg", "doc"}

def allowed_attachment(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_ATTACH_EXT

@expenses_bp.route('/')
@login_required
def index():
    category_filter = request.args.get('category', '')
    person_filter = request.args.get('person', '')

    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            # Build filtered query
            expense_query = """
                SELECT id, amount, category, note, date, attachment, done_by
                FROM expense
                WHERE user_id=%s
            """
            params = [session['user_id']]

            if category_filter:
                expense_query += " AND category=%s"
                params.append(category_filter)
            if person_filter:
                expense_query += " AND done_by=%s"
                params.append(person_filter)

            expense_query += " ORDER BY date DESC"
            cur.execute(expense_query, tuple(params))
            expenses = cur.fetchall()

            # Unfiltered totals for summary
            cur.execute(
                "SELECT COALESCE(SUM(amount),0) AS total, COUNT(*) AS count FROM expense WHERE user_id=%s",
                (session['user_id'],)
            )
            summary = cur.fetchone()
            total_expenses = float(summary['total'])
            expense_count = int(summary['count'])

            # Category breakdown for filter + top category
            cur.execute("""
                SELECT category, SUM(amount) AS total, COUNT(*) AS count
                FROM expense WHERE user_id=%s
                GROUP BY category ORDER BY total DESC
            """, (session['user_id'],))
            categories = cur.fetchall()
            top_category = categories[0]['category'] if categories else None
            category_list = [r['category'] for r in categories]

            # Persons for filter
            cur.execute(
                "SELECT DISTINCT done_by FROM expense WHERE user_id=%s AND done_by IS NOT NULL",
                (session['user_id'],)
            )
            person_list = [r['done_by'] for r in cur.fetchall()]

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
            default_done_by=default_done_by,
            total_expenses=total_expenses,
            expense_count=expense_count,
            top_category=top_category,
            category_list=category_list,
            person_list=person_list,
            category_filter=category_filter,
            person_filter=person_filter,
        )
    finally:
        conn.close()


@expenses_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'GET':
        conn = current_app.db_pool.get_connection()
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute("SELECT default_done_by FROM setting WHERE user_id=%s LIMIT 1", (session['user_id'],))
                row = cur.fetchone()
                default_done_by = row['default_done_by'] if row else None
            return render_template('expenses/add.html', current_date=date.today(), default_done_by=default_done_by)
        finally:
            conn.close()

    amount = request.form.get('amount', '')
    category = request.form.get('category', '').strip()
    note = request.form.get('note', '').strip()
    date_str = request.form.get('date', '')
    done_by = request.form.get('done_by', '').strip()

    # Validate amount
    try:
        amount_val = Decimal(amount)
        if amount_val < 0 or amount_val > Decimal('99999999.99'):
            raise ValueError
    except (InvalidOperation, ValueError):
        flash("Please enter a valid positive amount.", "error")
        return redirect(url_for('expenses.add_expense'))

    # Validate date
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        flash("Please enter a valid date (YYYY-MM-DD).", "error")
        return redirect(url_for('expenses.add_expense'))

    # Validate required fields
    if not category or len(category) > 50:
        flash("Category is required (max 50 chars).", "error")
        return redirect(url_for('expenses.add_expense'))
    if not done_by or len(done_by) > 50:
        flash("Done By is required (max 50 chars).", "error")
        return redirect(url_for('expenses.add_expense'))
    if note and len(note) > 1000:
        flash("Note must be 1000 characters or less.", "error")
        return redirect(url_for('expenses.add_expense'))

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
                (str(amount_val), category, note or None, date_str, session['user_id'], filename, done_by)
            )
            conn.commit()
        return redirect(url_for('expenses.index'))
    finally:
        conn.close()


@expenses_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_expense(id):
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute(
                "SELECT id, amount, category, note, date, attachment, done_by FROM expense WHERE id=%s AND user_id=%s",
                (id, session['user_id'])
            )
            expense = cur.fetchone()
            if not expense:
                return "Expense not found", 404

            if request.method == 'GET':
                return render_template('expenses/edit.html', expense=expense)

            amount = request.form.get('amount', '')
            category = request.form.get('category', '').strip()
            note = request.form.get('note', '').strip()
            date_str = request.form.get('date', '')
            done_by = request.form.get('done_by', '').strip()

            # Validate amount
            try:
                amount_val = Decimal(amount)
                if amount_val < 0 or amount_val > Decimal('99999999.99'):
                    raise ValueError
            except (InvalidOperation, ValueError):
                flash("Please enter a valid positive amount.", "error")
                return redirect(url_for('expenses.edit_expense', id=id))

            # Validate date
            try:
                datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                flash("Please enter a valid date (YYYY-MM-DD).", "error")
                return redirect(url_for('expenses.edit_expense', id=id))

            if not category or len(category) > 50:
                flash("Category is required (max 50 chars).", "error")
                return redirect(url_for('expenses.edit_expense', id=id))
            if not done_by or len(done_by) > 50:
                flash("Done By is required (max 50 chars).", "error")
                return redirect(url_for('expenses.edit_expense', id=id))

            file = request.files.get('attachment')
            new_filename = None
            if file and file.filename and allowed_attachment(file.filename):
                new_filename = secure_filename(file.filename)
                new_filename = f"user{session['user_id']}_{new_filename}"
                os.makedirs(current_app.config['RECEIPT_FOLDER'], exist_ok=True)
                file.save(os.path.join(current_app.config['RECEIPT_FOLDER'], new_filename))

            if new_filename:
                cur.execute(
                    "UPDATE expense SET amount=%s, category=%s, note=%s, date=%s, attachment=%s, done_by=%s WHERE id=%s AND user_id=%s",
                    (str(amount_val), category, note or None, date_str, new_filename, done_by, id, session['user_id'])
                )
            else:
                cur.execute(
                    "UPDATE expense SET amount=%s, category=%s, note=%s, date=%s, done_by=%s WHERE id=%s AND user_id=%s",
                    (str(amount_val), category, note or None, date_str, done_by, id, session['user_id'])
                )
            conn.commit()
    finally:
        conn.close()

    return redirect(url_for('expenses.index'))


@expenses_bp.route('/delete/<int:id>', methods=['POST'])
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
