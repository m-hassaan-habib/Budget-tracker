from flask import Blueprint, render_template, request, current_app

history_bp = Blueprint('history', __name__, url_prefix='/history')

@history_bp.route('/')
def index():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            # Get distinct months
            cur.execute("SELECT DISTINCT month FROM archived_expense ORDER BY month DESC")
            months = [row['month'] for row in cur.fetchall()]
            selected_month = request.args.get('month') or (months[0] if months else None)

            # Fetch archived income
            archived_income = []
            if selected_month:
                cur.execute("SELECT id, source, amount, month FROM archived_income WHERE month = %s", (selected_month,))
                archived_income = [
                    {"id": row['id'], "source": row['source'], "amount": float(row['amount']), "month": row['month']}
                    for row in cur.fetchall()
                ]

            # Fetch archived expenses
            archived_expenses = []
            if selected_month:
                cur.execute("SELECT id, amount, category, note, date, month FROM archived_expense WHERE month = %s", (selected_month,))
                archived_expenses = [
                    {"id": row['id'], "amount": float(row['amount']), "category": row['category'], "note": row['note'], "date": row['date'], "month": row['month']}
                    for row in cur.fetchall()
                ]

        return render_template("history.html",
            months=months,
            selected_month=selected_month,
            incomes=archived_income,
            expenses=archived_expenses
        )
    finally:
        conn.close()