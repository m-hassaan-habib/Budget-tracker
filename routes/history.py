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

            if selected_month:
                cur.execute(
                    "SELECT id, source, amount, month FROM archived_income WHERE month=%s AND user_id=%s",
                    (selected_month, session['user_id'])
                )
                archived_income = [
                    {"id": row['id'], "source": row['source'], "amount": float(row['amount']), "month": row['month']}
                    for row in cur.fetchall()
                ]

                cur.execute(
                    "SELECT id, amount, category, note, date, month FROM archived_expense WHERE month=%s AND user_id=%s",
                    (selected_month, session['user_id'])
                )
                archived_expenses = [
                    {"id": row['id'], "amount": float(row['amount']), "category": row['category'],
                     "note": row['note'], "date": row['date'], "month": row['month']}
                    for row in cur.fetchall()
                ]

        return render_template(
            "history.html",
            months=months,
            selected_month=selected_month,
            incomes=archived_income,
            expenses=archived_expenses
        )
    finally:
        conn.close()
