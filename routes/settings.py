from flask import Blueprint, render_template, request, redirect, url_for
from models import db, Setting

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

@settings_bp.route('/')
def index():
    setting = Setting.query.first()
    current_limit = setting.monthly_limit if setting else 0
    total_savings = setting.total_savings if setting else 0
    return render_template('settings.html', current_limit=current_limit, total_savings=total_savings)


@settings_bp.route('/update', methods=['POST'])
def update_limit():
    limit = request.form['limit']
    savings = request.form['savings']
    from decimal import Decimal

    setting = Setting.query.first()
    if not setting:
        setting = Setting(monthly_limit=Decimal(limit), total_savings=Decimal(savings))
        db.session.add(setting)
    else:
        setting.monthly_limit = Decimal(limit)
        setting.total_savings = Decimal(savings)
    db.session.commit()
    return redirect(url_for('settings.index'))



@settings_bp.route('/end-month', methods=['POST'])
def end_month():
    from decimal import Decimal
    from sqlalchemy import func
    from datetime import datetime
    from models import db, Income, Expense, Setting, ArchivedIncome, ArchivedExpense

    now = datetime.now()
    month_str = now.strftime("%Y-%m")

    total_income = db.session.query(func.coalesce(func.sum(Income.amount), 0)).scalar()
    total_expenses = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).scalar()
    net_savings = Decimal(total_income) - Decimal(total_expenses)

    setting = Setting.query.first()
    if setting:
        setting.total_savings += net_savings

    # Archive Income
    incomes = Income.query.all()
    for inc in incomes:
        db.session.add(ArchivedIncome(
            source=inc.source,
            amount=inc.amount,
            month=month_str
        ))

    # Archive Expenses
    expenses = Expense.query.all()
    for exp in expenses:
        db.session.add(ArchivedExpense(
            amount=exp.amount,
            category=exp.category,
            note=exp.note,
            date=exp.date,
            month=month_str
        ))

    db.session.query(Income).delete()
    db.session.query(Expense).delete()
    db.session.commit()

    return redirect(url_for('settings.index'))


@settings_bp.route('/fresh-start', methods=['POST'])
def fresh_start():
    from models import db, Income, Expense, Setting, ArchivedIncome, ArchivedExpense

    db.session.query(ArchivedIncome).delete()
    db.session.query(ArchivedExpense).delete()
    db.session.query(Income).delete()
    db.session.query(Expense).delete()
    db.session.query(Setting).delete()

    db.session.commit()

    return redirect(url_for('settings.index'))
