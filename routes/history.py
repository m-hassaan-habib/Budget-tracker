"""Past months, read from the one ledger.

This used to read archived_income / archived_expense, which only had data in
them once somebody remembered to click "End Month" -- and which stamped rows
with the click date rather than the expense date. Months now come from the
date column, so every past month is available whether or not anyone did
anything at month end.
"""

from flask import Blueprint, render_template, request, current_app, session
from auth_utils import login_required
from months import available_months, format_month, month_bounds

history_bp = Blueprint('history', __name__, url_prefix='/history')


@history_bp.route('/')
@login_required
def index():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            user_id = session['user_id']
            months = available_months(cur, user_id)

            selected_month = request.args.get('month') or (months[0] if months else None)
            category_filter = request.args.get('category', '')

            incomes = []
            expenses = []
            total_income_month = 0.0
            total_expense_month = 0.0
            category_breakdown = {}
            expense_categories = []
            actual_income_by_person = {}
            total_actual_income_month = 0.0

            if selected_month:
                start, end = month_bounds(selected_month)

                cur.execute(
                    "SELECT id, source, amount FROM income "
                    "WHERE user_id=%s AND date BETWEEN %s AND %s",
                    (user_id, start, end)
                )
                incomes = [
                    {"id": r['id'], "source": r['source'], "amount": float(r['amount'])}
                    for r in cur.fetchall()
                ]
                total_income_month = sum(i["amount"] for i in incomes)

                cur.execute(
                    "SELECT done_by, SUM(amount) AS total FROM expense "
                    "WHERE user_id=%s AND date BETWEEN %s AND %s GROUP BY done_by",
                    (user_id, start, end)
                )
                actual_income_by_person = {
                    r['done_by']: float(r['total']) for r in cur.fetchall()
                }
                total_actual_income_month = sum(actual_income_by_person.values())

                expense_query = """
                    SELECT id, amount, category, note, date, done_by
                    FROM expense
                    WHERE user_id=%s AND date BETWEEN %s AND %s
                """
                params = [user_id, start, end]
                if category_filter:
                    expense_query += " AND category=%s"
                    params.append(category_filter)
                expense_query += " ORDER BY date DESC, id DESC"

                cur.execute(expense_query, tuple(params))
                expenses = [
                    {
                        "id": r['id'],
                        "amount": float(r['amount']),
                        "category": r['category'],
                        "note": r['note'],
                        "date": r['date'],
                        "done_by": r['done_by'],
                    }
                    for r in cur.fetchall()
                ]

                cur.execute(
                    "SELECT COALESCE(SUM(amount),0) AS total FROM expense "
                    "WHERE user_id=%s AND date BETWEEN %s AND %s",
                    (user_id, start, end)
                )
                total_expense_month = float(cur.fetchone()['total'])

                cur.execute(
                    """
                    SELECT category, SUM(amount) AS total, COUNT(*) AS count
                    FROM expense
                    WHERE user_id=%s AND date BETWEEN %s AND %s
                    GROUP BY category
                    ORDER BY total DESC
                    """,
                    (user_id, start, end)
                )
                category_breakdown = {
                    r['category']: {"total": float(r['total']), "count": int(r['count'])}
                    for r in cur.fetchall()
                }
                expense_categories = list(category_breakdown.keys())

        net_savings = total_income_month - total_expense_month
        savings_rate = (net_savings / total_income_month * 100) if total_income_month else 0
        income_variance = total_income_month - total_actual_income_month

        return render_template(
            "history.html",
            months=months,
            month_options=[(m, format_month(m)) for m in months],
            selected_month=selected_month,
            selected_month_display=format_month(selected_month) if selected_month else None,
            incomes=incomes,
            expenses=expenses,
            total_income_month=total_income_month,
            total_actual_income_month=total_actual_income_month,
            actual_income_by_person=actual_income_by_person,
            income_variance=income_variance,
            total_expense_month=total_expense_month,
            net_savings=net_savings,
            savings_rate=savings_rate,
            category_breakdown=category_breakdown,
            expense_categories=expense_categories,
            category_filter=category_filter,
        )
    finally:
        conn.close()


@history_bp.route('/expense/<int:id>')
@login_required
def view_archived_expense(id):
    """Kept for old bookmarks -- past expenses now live in the same table."""
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute(
                "SELECT id, amount, category, note, date, done_by "
                "FROM expense WHERE id=%s AND user_id=%s",
                (id, session['user_id'])
            )
            expense = cur.fetchone()

        if not expense:
            return "Archived expense not found", 404

        return render_template("expenses/view_archived.html", expense=expense)
    finally:
        conn.close()


def _month_totals(cur, user_id, months):
    """Income and expense totals for a set of months, in two queries."""
    if not months:
        return {}, {}

    placeholders = ', '.join(['%s'] * len(months))
    income, expense = {}, {}

    # Aggregated separately and combined in Python. Joining income to expense
    # on user_id alone -- as the old savings chart did -- multiplies every
    # income row by every expense row and inflates the result.
    cur.execute(
        f"""
        SELECT DATE_FORMAT(date, '%Y-%m') AS m, COALESCE(SUM(amount),0) AS total
        FROM income WHERE user_id=%s AND DATE_FORMAT(date, '%Y-%m') IN ({placeholders})
        GROUP BY m
        """,
        (user_id, *months)
    )
    for row in cur.fetchall():
        income[row['m']] = float(row['total'])

    cur.execute(
        f"""
        SELECT DATE_FORMAT(date, '%Y-%m') AS m, COALESCE(SUM(amount),0) AS total
        FROM expense WHERE user_id=%s AND DATE_FORMAT(date, '%Y-%m') IN ({placeholders})
        GROUP BY m
        """,
        (user_id, *months)
    )
    for row in cur.fetchall():
        expense[row['m']] = float(row['total'])

    return income, expense


@history_bp.route('/compare', methods=['GET'])
@login_required
def compare():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            user_id = session['user_id']
            months = available_months(cur, user_id)

            m1 = request.args.get('m1')
            m2 = request.args.get('m2')
            comparison = None

            all_income, all_expense = _month_totals(cur, user_id, months)
            trend = []
            for month in reversed(months):
                inc = all_income.get(month, 0.0)
                exp = all_expense.get(month, 0.0)
                trend.append({
                    "month": month,
                    "income": inc,
                    "expense": exp,
                    "net": inc - exp,
                    "savings_rate": round((inc - exp) / inc * 100, 1) if inc else 0,
                })

            if m1 and m2:
                income = {m: all_income.get(m, 0.0) for m in (m1, m2)}
                expense = {m: all_expense.get(m, 0.0) for m in (m1, m2)}

                cur.execute(
                    """
                    SELECT category, DATE_FORMAT(date, '%Y-%m') AS m, SUM(amount) AS total
                    FROM expense
                    WHERE user_id=%s AND DATE_FORMAT(date, '%Y-%m') IN (%s, %s)
                    GROUP BY category, m
                    """,
                    (user_id, m1, m2)
                )
                categories = {}
                for r in cur.fetchall():
                    categories.setdefault(r['category'], {})[r['m']] = float(r['total'])

                cur.execute(
                    """
                    SELECT source, DATE_FORMAT(date, '%Y-%m') AS m, SUM(amount) AS total
                    FROM income
                    WHERE user_id=%s AND DATE_FORMAT(date, '%Y-%m') IN (%s, %s)
                    GROUP BY source, m
                    """,
                    (user_id, m1, m2)
                )
                income_sources = {}
                for r in cur.fetchall():
                    income_sources.setdefault(r['source'], {})[r['m']] = float(r['total'])

                n1 = income[m1] - expense[m1]
                n2 = income[m2] - expense[m2]

                comparison = {
                    "m1": m1,
                    "m2": m2,
                    "income": income,
                    "expense": expense,
                    "net": {m1: n1, m2: n2},
                    "categories": categories,
                    "income_sources": income_sources,
                    "savings_rate": {
                        m1: round(n1 / income[m1] * 100, 1) if income[m1] else 0,
                        m2: round(n2 / income[m2] * 100, 1) if income[m2] else 0,
                    },
                }

        return render_template(
            "history/compare.html",
            months=months,
            month_options=[(m, format_month(m)) for m in months],
            comparison=comparison,
            m1=m1,
            m2=m2,
            m1_display=format_month(m1) if m1 else None,
            m2_display=format_month(m2) if m2 else None,
            trend=trend,
        )
    finally:
        conn.close()
