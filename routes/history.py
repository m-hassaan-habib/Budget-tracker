from flask import Blueprint, render_template, request, current_app, session
from auth_utils import login_required

history_bp = Blueprint('history', __name__, url_prefix='/history')

@history_bp.route('/')
@login_required
def index():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("""
                SELECT month FROM archived_income WHERE user_id=%s
                UNION
                SELECT month FROM archived_expense WHERE user_id=%s
                ORDER BY month DESC
            """, (session['user_id'], session['user_id']))
            months = [row['month'] for row in cur.fetchall()]

            selected_month = request.args.get('month') or (months[0] if months else None)

            archived_income = []
            archived_expenses = []
            total_income_month = 0.0
            total_expense_month = 0.0

            if selected_month:
                cur.execute(
                    "SELECT id, source, amount FROM archived_income WHERE month=%s AND user_id=%s",
                    (selected_month, session['user_id'])
                )
                archived_income = [
                    {"id": r['id'], "source": r['source'], "amount": float(r['amount'])}
                    for r in cur.fetchall()
                ]
                total_income_month = sum(i["amount"] for i in archived_income)

                cur.execute(
                    "SELECT id, amount, category, note, date FROM archived_expense WHERE month=%s AND user_id=%s",
                    (selected_month, session['user_id'])
                )
                archived_expenses = [
                    {
                        "id": r['id'],
                        "amount": float(r['amount']),
                        "category": r['category'],
                        "note": r['note'],
                        "date": r['date'],
                    }
                    for r in cur.fetchall()
                ]
                total_expense_month = sum(e["amount"] for e in archived_expenses)

        return render_template(
            "history.html",
            months=months,
            selected_month=selected_month,
            incomes=archived_income,
            expenses=archived_expenses,
            total_income_month=total_income_month,
            total_expense_month=total_expense_month,
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
                SELECT id, amount, category, note, date
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

            if m1 and m2:
                cur.execute("""
                    SELECT month, COALESCE(SUM(amount),0) AS total
                    FROM archived_income
                    WHERE user_id=%s AND month IN (%s,%s)
                    GROUP BY month
                """, (session['user_id'], m1, m2))
                income = {r['month']: float(r['total']) for r in cur.fetchall()}

                cur.execute("""
                    SELECT month, COALESCE(SUM(amount),0) AS total
                    FROM archived_expense
                    WHERE user_id=%s AND month IN (%s,%s)
                    GROUP BY month
                """, (session['user_id'], m1, m2))
                expense = {r['month']: float(r['total']) for r in cur.fetchall()}

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

                comparison = {
                    "m1": m1,
                    "m2": m2,
                    "income": income,
                    "expense": expense,
                    "net": {
                        m1: income.get(m1, 0) - expense.get(m1, 0),
                        m2: income.get(m2, 0) - expense.get(m2, 0),
                    },
                    "categories": categories
                }

        return render_template(
            "history/compare.html",
            months=months,
            comparison=comparison,
            m1=m1,
            m2=m2
        )

    finally:
        conn.close()
