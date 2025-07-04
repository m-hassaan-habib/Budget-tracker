from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Income(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    note = db.Column(db.Text)
    date = db.Column(db.Date, nullable=False)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    monthly_limit = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    total_savings = db.Column(db.Numeric(10, 2), nullable=True, server_default="0.0")


class ArchivedIncome(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    month = db.Column(db.String(20), nullable=False)

class ArchivedExpense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    note = db.Column(db.Text)
    date = db.Column(db.Date, nullable=False)
    month = db.Column(db.String(20), nullable=False)
