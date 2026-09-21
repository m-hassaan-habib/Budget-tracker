import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    current_app, session, flash, jsonify
)
from werkzeug.utils import secure_filename
from auth_utils import login_required, current_actor
from routes.categories import list_categories, top_categories
from routes.members import member_names
import activity

expenses_bp = Blueprint('expenses', __name__, url_prefix='/expenses')

ALLOWED_ATTACH_EXT = {"pdf", "png", "jpg", "jpeg", "doc"}

def allowed_attachment(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_ATTACH_EXT


def parse_expense_form(form):
    """Validate the fields common to every way of recording an expense.

    Returns (values, error). Shared by the full form and quick add so the two
    entry paths can't drift apart on what counts as valid.
    """
    try:
        amount = Decimal(form.get('amount', ''))
        if amount < 0 or amount > Decimal('99999999.99'):
            raise ValueError
    except (InvalidOperation, ValueError):
        return None, "Please enter a valid positive amount."

    date_str = form.get('date', '')
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return None, "Please enter a valid date (YYYY-MM-DD)."

    category = form.get('category', '').strip()
    if not category or len(category) > 50:
        return None, "Category is required (max 50 chars)."

    done_by = form.get('done_by', '').strip()
    if not done_by or len(done_by) > 50:
        return None, "Done By is required (max 50 chars)."

    note = form.get('note', '').strip()
    if note and len(note) > 1000:
        return None, "Note must be 1000 characters or less."

    return {
        'amount': amount,
        'category': category,
        'note': note or None,
        'date': date_str,
        'done_by': done_by,
    }, None


def remember_entry_context(values):
    """Keep the date and person between consecutive entries.

    Catching up on three days of spending shouldn't mean setting the same
    date eight times in a row.
    """
    session['last_expense_date'] = values['date']
    session['last_done_by'] = values['done_by']

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

            # Quick-entry context
            categories = list_categories(cur, session['user_id'])
            chips = top_categories(cur, session['user_id'])

        return render_template(
            'expenses.html',
            expenses=expenses,
            current_date=date.today(),
            default_done_by=default_done_by,
            categories=categories,
            top_categories=chips,
            sticky_date=session.get('last_expense_date') or date.today().isoformat(),
            sticky_done_by=session.get('last_done_by') or session.get('actor') or default_done_by,
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
                categories = list_categories(cur, session['user_id'])
                members = member_names(cur, session['user_id'])
            return render_template(
                'expenses/add.html',
                current_date=date.today(),
                default_done_by=session.get('actor') or default_done_by,
                categories=categories,
                members=members,
            )
        finally:
            conn.close()

    values, error = parse_expense_form(request.form)
    if error:
        flash(error, "error")
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
        with conn.cursor(dictionary=True) as cur:
            new_id = _insert_expense(cur, session['user_id'], values, filename)
            activity.log_created(cur, session['user_id'], current_actor(), 'expense', new_id)
            conn.commit()
        remember_entry_context(values)
        return redirect(url_for('expenses.index'))
    finally:
        conn.close()


def _insert_expense(cur, user_id, values, attachment=None):
    cur.execute(
        "INSERT INTO expense (amount, category, note, date, user_id, attachment, done_by) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (str(values['amount']), values['category'], values['note'],
         values['date'], user_id, attachment, values['done_by'])
    )
    return cur.lastrowid


def _render_row(cur, user_id, expense_id):
    """Render one expense exactly as the list renders it."""
    cur.execute(
        "SELECT id, amount, category, note, date, attachment, done_by "
        "FROM expense WHERE id=%s AND user_id=%s",
        (expense_id, user_id)
    )
    expense = cur.fetchone()
    return render_template('expenses/_row.html', expense=expense)


@expenses_bp.route('/quick', methods=['POST'])
@login_required
def quick_add():
    """Record an expense without leaving the page.

    Returns the rendered row so the list can prepend it, which keeps the
    markup in one place instead of rebuilding it in JavaScript.
    """
    values, error = parse_expense_form(request.form)
    if error:
        return jsonify({'ok': False, 'error': error}), 400

    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            new_id = _insert_expense(cur, session['user_id'], values)
            activity.log_created(cur, session['user_id'], current_actor(), 'expense', new_id)
            conn.commit()
            html = _render_row(cur, session['user_id'], new_id)
    finally:
        conn.close()

    remember_entry_context(values)
    return jsonify({'ok': True, 'id': new_id, 'html': html})


@expenses_bp.route('/repeat/<int:id>', methods=['POST'])
@login_required
def repeat_expense(id):
    """Clone an existing expense onto today.

    Most household spending is the same handful of things, so re-entering
    them from scratch is wasted typing.
    """
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute(
                "SELECT amount, category, note, done_by FROM expense WHERE id=%s AND user_id=%s",
                (id, session['user_id'])
            )
            original = cur.fetchone()
            if not original:
                return "Expense not found", 404

            values = {
                'amount': original['amount'],
                'category': original['category'],
                'note': original['note'],
                'date': date.today().isoformat(),
                'done_by': original['done_by'],
            }
            new_id = _insert_expense(cur, session['user_id'], values)
            activity.log_created(cur, session['user_id'], current_actor(), 'expense', new_id)
            conn.commit()
    finally:
        conn.close()

    return redirect(url_for('expenses.index'))


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
                return render_template(
                    'expenses/edit.html',
                    expense=expense,
                    categories=list_categories(cur, session['user_id']),
                    members=member_names(cur, session['user_id']),
                )

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

            before = activity.snapshot(cur, 'expense', id, session['user_id'])

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

            after = activity.snapshot(cur, 'expense', id, session['user_id'])
            activity.log_change(cur, session['user_id'], current_actor(), 'expense', id,
                                activity.UPDATE, before=before, after=after)
            conn.commit()
    finally:
        conn.close()

    return redirect(url_for('expenses.index'))


@expenses_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_expense(id):
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            before = activity.snapshot(cur, 'expense', id, session['user_id'])
            cur.execute("DELETE FROM expense WHERE id=%s AND user_id=%s", (id, session['user_id']))
            if before:
                activity.log_change(cur, session['user_id'], current_actor(), 'expense', id,
                                    activity.DELETE, before=before)
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

            # This record's own history, from the same log that powers /track.
            from routes.activity_log import fetch_entries
            trail = fetch_entries(cur, session['user_id'],
                                  entity_type='expense', entity_id=id, limit=20)

        return render_template("expenses/view.html", expense=expense, trail=trail)

    finally:
        conn.close()
