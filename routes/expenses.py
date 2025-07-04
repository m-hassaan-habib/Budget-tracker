from flask import Blueprint, render_template, request, redirect, url_for
from models import db, Expense
from datetime import date

expenses_bp = Blueprint('expenses', __name__, url_prefix='/expenses')

@expenses_bp.route('/')
def index():
    expenses = Expense.query.order_by(Expense.date.desc()).all()
    return render_template('expenses.html', expenses=expenses, current_date=date.today())

@expenses_bp.route('/add', methods=['POST'])
def add_expense():
    amount = request.form['amount']
    category = request.form['category']
    note = request.form.get('note')
    date_str = request.form['date']

    new_expense = Expense(
        amount=amount,
        category=category,
        note=note,
        date=date.fromisoformat(date_str)
    )
    db.session.add(new_expense)
    db.session.commit()
    return redirect(url_for('expenses.index'))

@expenses_bp.route('/edit/<int:id>', methods=['POST'])
def edit_expense(id):
    from decimal import Decimal
    expense = Expense.query.get_or_404(id)
    expense.amount = Decimal(request.form['amount'])
    expense.category = request.form['category']
    expense.note = request.form.get('note')
    expense.date = request.form['date']
    db.session.commit()
    return redirect(url_for('expenses.index'))

@expenses_bp.route('/delete/<int:id>')
def delete_expense(id):
    expense = Expense.query.get_or_404(id)
    db.session.delete(expense)
    db.session.commit()
    return redirect(url_for('expenses.index'))
