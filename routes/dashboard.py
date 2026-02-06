from flask import Blueprint, render_template, current_app, session
from auth_utils import login_required

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='')

@dashboard_bp.route('/')
@login_required
def index():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM income WHERE user_id=%s",
                (session['user_id'],)
            )
            total_income = float(cur.fetchone()['total'])

            cur.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM expense WHERE user_id=%s",
                (session['user_id'],)
            )
            total_expenses = float(cur.fetchone()['total'])

            net_savings = total_income - total_expenses

            cur.execute(
                "SELECT monthly_limit, total_savings FROM setting WHERE user_id=%s LIMIT 1",
                (session['user_id'],)
            )
            setting = cur.fetchone()
            monthly_limit = float(setting['monthly_limit']) if setting else 0
            total_savings = float(setting['total_savings']) if setting else 0

            grand_total = net_savings + total_savings

            cur.execute("""
                SELECT category, SUM(amount) AS total
                FROM expense
                WHERE user_id=%s
                GROUP BY category
            """, (session['user_id'],))
            category_data = cur.fetchall()
            pie_labels = [row['category'] for row in category_data]
            pie_values = [float(row['total']) for row in category_data]

            cur.execute("""
                SELECT DATE_FORMAT(date, '%b %d') AS day, SUM(amount) AS total
                FROM expense
                WHERE user_id=%s
                GROUP BY DATE_FORMAT(date, '%b %d')
                ORDER BY DATE_FORMAT(date, '%b %d')
            """, (session['user_id'],))
            daily_data = cur.fetchall()
            daily_labels = [row['day'] for row in daily_data]
            daily_values = [float(row['total']) for row in daily_data]

            cur.execute("""
                SELECT DATE_FORMAT(e.date, '%b') AS mon,
                       COALESCE(SUM(i.amount), 0) - COALESCE(SUM(e.amount), 0) AS savings
                FROM expense e
                LEFT JOIN income i ON i.user_id = e.user_id
                WHERE e.user_id=%s
                GROUP BY DATE_FORMAT(e.date, '%b')
                ORDER BY DATE_FORMAT(e.date, '%b')
            """, (session['user_id'],))
            monthly_data = cur.fetchall()
            savings_labels = [row['mon'] for row in monthly_data]
            savings_values = [float(row['savings']) for row in monthly_data]

            cur.execute("""
                SELECT done_by, SUM(amount) AS total
                FROM expense
                WHERE user_id=%s
                GROUP BY done_by
            """, (session['user_id'],))
            who_data = cur.fetchall()
            who_labels = [row['done_by'] for row in who_data]
            who_values = [float(row['total']) for row in who_data]

            # Recent expenses for quick view
            cur.execute("""
                SELECT id, amount, category, note, date
                FROM expense
                WHERE user_id=%s
                ORDER BY date DESC, id DESC
                LIMIT 5
            """, (session['user_id'],))
            recent_expenses = cur.fetchall()

            # Expense count
            cur.execute("SELECT COUNT(*) AS cnt FROM expense WHERE user_id=%s", (session['user_id'],))
            expense_count = int(cur.fetchone()['cnt'])

        return render_template(
            "dashboard.html",
            total_income=total_income,
            total_expenses=total_expenses,
            net_savings=net_savings,
            total_savings=total_savings,
            grand_total=grand_total,
            monthly_limit=monthly_limit,
            pie_labels=pie_labels,
            pie_values=pie_values,
            daily_labels=daily_labels,
            daily_values=daily_values,
            savings_labels=savings_labels,
            savings_values=savings_values,
            who_labels=who_labels,
            who_values=who_values,
            recent_expenses=recent_expenses,
            expense_count=expense_count,
        )
    finally:
        conn.close()
