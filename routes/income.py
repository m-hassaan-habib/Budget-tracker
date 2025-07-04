from flask import Blueprint, render_template, request, redirect, url_for
from models import db, Income
from decimal import Decimal


income_bp = Blueprint('income', __name__, url_prefix='/income')

@income_bp.route('/')
def index():
    incomes = Income.query.all()
    return render_template('income.html', incomes=incomes)

@income_bp.route('/add', methods=['POST'])
def add_income():
    source = request.form['source']
    amount = request.form['amount']
    db.session.add(Income(source=source, amount=amount))
    db.session.commit()
    return redirect(url_for('income.index'))

@income_bp.route('/edit/<int:id>', methods=['POST'])
def edit_income(id):
    income = Income.query.get_or_404(id)
    income.source = request.form['source']
    income.amount = Decimal(request.form['amount'])
    db.session.commit()
    return redirect(url_for('income.index'))

@income_bp.route('/delete/<int:id>')
def delete_income(id):
    income = Income.query.get_or_404(id)
    db.session.delete(income)
    db.session.commit()
    return redirect(url_for('income.index'))
