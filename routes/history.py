from flask import Blueprint, render_template, request, current_app, session
from auth_utils import login_required

history_bp = Blueprint('history', __name__, url_prefix='/history')


@history_bp.route('/')
@login_required
def index():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            # Get all archived months
            cur.execute("""
                SELECT month FROM archived_income WHERE user_id=%s
                UNION
                SELECT month FROM archived_expense WHERE user_id=%s
                ORDER BY month DESC
            """, (session['user_id'], session['user_id']))
            months = [row['month'] for row in cur.fetchall()]

            selected_month = request.args.get('month') or (months[0] if months else None)
            category_filter = request.args.get('category', '')

            archived_income = []
            archived_expenses = []
            total_income_month = 0.0
            total_expense_month = 0.0
            category_breakdown = {}
            expense_categories = []

            actual_income_by_person = {}
            total_actual_income_month = 0.0

            if selected_month:
                # Expected Income (manually entered, archived)
                cur.execute(
                    "SELECT id, source, amount FROM archived_income WHERE month=%s AND user_id=%s",
                    (selected_month, session['user_id'])
                )
                archived_income = [
                    {"id": r['id'], "source": r['source'], "amount": float(r['amount'])}
                    for r in cur.fetchall()
                ]
                total_income_month = sum(i["amount"] for i in archived_income)

                # Actual Income (calculated from archived expenses grouped by done_by)
                cur.execute("""
                    SELECT done_by, SUM(amount) AS total
                    FROM archived_expense WHERE month=%s AND user_id=%s GROUP BY done_by
                """, (selected_month, session['user_id']))
                actual_income_by_person = {row['done_by']: float(row['total']) for row in cur.fetchall()}
                total_actual_income_month = sum(actual_income_by_person.values())

                # Expenses
                expense_query = """
                    SELECT id, amount, category, note, date, done_by
                    FROM archived_expense
                    WHERE month=%s AND user_id=%s
                """
                expense_params = [selected_month, session['user_id']]

                if category_filter:
                    expense_query += " AND category=%s"
                    expense_params.append(category_filter)

                expense_query += " ORDER BY date DESC"
                cur.execute(expense_query, tuple(expense_params))

                archived_expenses = [
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

                # Total expenses (unfiltered for summary)
                cur.execute(
                    "SELECT COALESCE(SUM(amount),0) AS total FROM archived_expense WHERE month=%s AND user_id=%s",
                    (selected_month, session['user_id'])
                )
                total_expense_month = float(cur.fetchone()['total'])

                # Category breakdown
                cur.execute("""
                    SELECT category, SUM(amount) AS total, COUNT(*) AS count
                    FROM archived_expense
                    WHERE month=%s AND user_id=%s
                    GROUP BY category
                    ORDER BY total DESC
                """, (selected_month, session['user_id']))
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
            selected_month=selected_month,
            incomes=archived_income,
            expenses=archived_expenses,
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
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute(
                """
                SELECT id, amount, category, note, date, done_by
                FROM archived_expense
                WHERE id=%s AND user_id=%s
                """,
                (id, session['user_id'])
            )
            expense = cur.fetchone()

        if not expense:
            return "Archived expense not found", 404

        return render_template(
            "expenses/view_archived.html",
            expense=expense
        )
    finally:
        conn.close()


@history_bp.route('/compare', methods=['GET'])
@login_required
def compare():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:

            cur.execute("""
                SELECT DISTINCT month FROM archived_income WHERE user_id=%s
                UNION
                SELECT DISTINCT month FROM archived_expense WHERE user_id=%s
                ORDER BY month DESC
            """, (session['user_id'], session['user_id']))
            months = [r['month'] for r in cur.fetchall()]

            m1 = request.args.get('m1')
            m2 = request.args.get('m2')

            comparison = None

            # All-months trend data
            trend = []
            if months:
                for month in reversed(months):
                    cur.execute(
                        "SELECT COALESCE(SUM(amount),0) AS total FROM archived_income WHERE user_id=%s AND month=%s",
                        (session['user_id'], month)
                    )
                    inc = float(cur.fetchone()['total'])
                    cur.execute(
                        "SELECT COALESCE(SUM(amount),0) AS total FROM archived_expense WHERE user_id=%s AND month=%s",
                        (session['user_id'], month)
                    )
                    exp = float(cur.fetchone()['total'])
                    trend.append({
                        "month": month,
                        "income": inc,
                        "expense": exp,
                        "net": inc - exp,
                        "savings_rate": round((inc - exp) / inc * 100, 1) if inc else 0
                    })

            if m1 and m2:
                # Income totals
                cur.execute("""
                    SELECT month, COALESCE(SUM(amount),0) AS total
                    FROM archived_income
                    WHERE user_id=%s AND month IN (%s,%s)
                    GROUP BY month
                """, (session['user_id'], m1, m2))
                income = {r['month']: float(r['total']) for r in cur.fetchall()}

                # Expense totals
                cur.execute("""
                    SELECT month, COALESCE(SUM(amount),0) AS total
                    FROM archived_expense
                    WHERE user_id=%s AND month IN (%s,%s)
                    GROUP BY month
                """, (session['user_id'], m1, m2))
                expense = {r['month']: float(r['total']) for r in cur.fetchall()}

                # Category breakdown
                cur.execute("""
                    SELECT category, month, SUM(amount) AS total
                    FROM archived_expense
                    WHERE user_id=%s AND month IN (%s,%s)
                    GROUP BY category, month
                """, (session['user_id'], m1, m2))

                cat_raw = cur.fetchall()
                categories = {}
                for r in cat_raw:
                    categories.setdefault(r['category'], {})
                    categories[r['category']][r['month']] = float(r['total'])

                # Income source breakdown
                cur.execute("""
                    SELECT source, month, SUM(amount) AS total
                    FROM archived_income
                    WHERE user_id=%s AND month IN (%s,%s)
                    GROUP BY source, month
                """, (session['user_id'], m1, m2))
                src_raw = cur.fetchall()
                income_sources = {}
                for r in src_raw:
                    income_sources.setdefault(r['source'], {})
                    income_sources[r['source']][r['month']] = float(r['total'])

                i1 = income.get(m1, 0)
                i2 = income.get(m2, 0)
                e1 = expense.get(m1, 0)
                e2 = expense.get(m2, 0)
                n1 = i1 - e1
                n2 = i2 - e2

                comparison = {
                    "m1": m1,
                    "m2": m2,
                    "income": income,
                    "expense": expense,
                    "net": {m1: n1, m2: n2},
                    "categories": categories,
                    "income_sources": income_sources,
                    "savings_rate": {
                        m1: round(n1 / i1 * 100, 1) if i1 else 0,
                        m2: round(n2 / i2 * 100, 1) if i2 else 0,
                    },
                }

        return render_template(
            "history/compare.html",
            months=months,
            comparison=comparison,
            m1=m1,
            m2=m2,
            trend=trend,
        )

    finally:
        conn.close()
