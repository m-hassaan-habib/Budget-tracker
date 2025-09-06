from flask import Blueprint, render_template, current_app

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='')

@dashboard_bp.route('/')
def index():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            # Total income
            cur.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM income")
            total_income = float(cur.fetchone()['total'])

            # Total expenses
            cur.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM expense")
            total_expenses = float(cur.fetchone()['total'])

            net_savings = total_income - total_expenses

            # Budget status
            cur.execute("SELECT monthly_limit, total_savings FROM setting LIMIT 1")
            setting = cur.fetchone()
            monthly_limit = float(setting['monthly_limit']) if setting else 0
            total_savings = float(setting['total_savings']) if setting else 0

            # Pie chart (category-wise)
            cur.execute("SELECT category, SUM(amount) AS total FROM expense GROUP BY category")
            category_data = cur.fetchall()
            pie_labels = [row['category'] for row in category_data]
            pie_values = [float(row['total']) for row in category_data]

            # Bar chart (daily)
            cur.execute("SELECT DATE_FORMAT(date, '%b %d') AS day, SUM(amount) AS total FROM expense GROUP BY DATE_FORMAT(date, '%b %d') ORDER BY DATE_FORMAT(date, '%b %d')")
            daily_data = cur.fetchall()
            daily_labels = [row['day'] for row in daily_data]
            daily_values = [float(row['total']) for row in daily_data]

            # Line chart (savings trend)
            cur.execute("""
                SELECT DATE_FORMAT(e.date, '%b') AS mon, 
                       COALESCE(SUM(i.amount), 0) - COALESCE(SUM(e.amount), 0) AS savings
                FROM expense e
                LEFT JOIN income i ON 1=1
                GROUP BY DATE_FORMAT(e.date, '%b')
                ORDER BY DATE_FORMAT(e.date, '%b')
            """)
            monthly_data = cur.fetchall()
            savings_labels = [row['mon'] for row in monthly_data]
            savings_values = [float(row['savings']) for row in monthly_data]

        return render_template("dashboard.html",
            total_income=total_income,
            total_expenses=total_expenses,
            net_savings=net_savings,
            pie_labels=pie_labels,
            pie_values=pie_values,
            daily_labels=daily_labels,
            daily_values=daily_values,
            savings_labels=savings_labels,
            savings_values=savings_values,
            total_savings=total_savings,
            monthly_limit=monthly_limit
        )
    finally:
        conn.close()