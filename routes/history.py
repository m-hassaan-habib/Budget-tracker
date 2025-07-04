from flask import Blueprint, render_template, request
from models import db, ArchivedIncome, ArchivedExpense
from sqlalchemy import func


history_bp = Blueprint('history', __name__, url_prefix='/history')

@history_bp.route('/')
def index():
    # Get distinct months for filter dropdown
    months = db.session.query(ArchivedExpense.month).distinct().order_by(ArchivedExpense.month.desc()).all()
    months = [m[0] for m in months]

    selected_month = request.args.get('month') or (months[0] if months else None)

    archived_income = ArchivedIncome.query.filter_by(month=selected_month).all() if selected_month else []
    archived_expenses = ArchivedExpense.query.filter_by(month=selected_month).all() if selected_month else []

    return render_template("history.html",
        months=months,
        selected_month=selected_month,
        incomes=archived_income,
        expenses=archived_expenses
    )
