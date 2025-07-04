from flask import Blueprint, render_template
from models import db, Expense, Income, Setting
from sqlalchemy import func

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='')

@dashboard_bp.route('/')
def index():
    total_income = db.session.query(func.coalesce(func.sum(Income.amount), 0)).scalar()
    total_expenses = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).scalar()
    net_savings = total_income - total_expenses

    # Budget Status
    setting = Setting.query.first()
    monthly_limit = setting.monthly_limit if setting else 0
    total_savings = setting.total_savings if setting else 0
    # budget_status = round((total_expenses / monthly_limit) * 100, 1) if monthly_limit > 0 else 0

    # Pie Chart (category-wise)
    category_data = db.session.query(
        Expense.category,
        func.sum(Expense.amount)
    ).group_by(Expense.category).all()
    pie_labels = [row[0] for row in category_data]
    pie_values = [float(row[1]) for row in category_data]

    # Bar Chart (daily)
    daily_data = db.session.query(
        func.to_char(Expense.date, 'Mon DD'),
        func.sum(Expense.amount)
    ).group_by(func.to_char(Expense.date, 'Mon DD')).order_by(func.to_char(Expense.date, 'Mon DD')).all()
    daily_labels = [row[0] for row in daily_data]
    daily_values = [float(row[1]) for row in daily_data]

    # Line Chart (savings trend)
    monthly_data = db.session.query(
        func.to_char(Expense.date, 'Mon'),
        func.sum(Income.amount) - func.sum(Expense.amount)
    ).join(Income, db.literal(True)).group_by(func.to_char(Expense.date, 'Mon')).order_by(func.to_char(Expense.date, 'Mon')).all()

    savings_labels = [row[0] for row in monthly_data]
    savings_values = [float(row[1]) for row in monthly_data]

    return render_template("dashboard.html",
        total_income=total_income,
        total_expenses=total_expenses,
        net_savings=net_savings,
        # budget_status=budget_status,
        pie_labels=pie_labels,
        pie_values=pie_values,
        daily_labels=daily_labels,
        daily_values=daily_values,
        savings_labels=savings_labels,
        savings_values=savings_values,
        total_savings=total_savings,
        monthly_limit=monthly_limit
    )
