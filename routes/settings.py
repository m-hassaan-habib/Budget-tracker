from flask import Blueprint, render_template, request, redirect, url_for, current_app
from datetime import datetime

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

@settings_bp.route('/')
def index():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT monthly_limit, total_savings FROM setting LIMIT 1")
            setting = cur.fetchone()
            current_limit = float(setting['monthly_limit']) if setting else 0
            total_savings = float(setting['total_savings']) if setting else 0
        return render_template('settings.html', current_limit=current_limit, total_savings=total_savings)
    finally:
        conn.close()

@settings_bp.route('/update', methods=['POST'])
def update_limit():
    limit = request.form['limit']
    savings = request.form['savings']
    
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM setting LIMIT 1")
            if not cur.fetchone():
                cur.execute("INSERT INTO setting (monthly_limit, total_savings) VALUES (%s, %s)", (limit, savings))
            else:
                cur.execute("UPDATE setting SET monthly_limit = %s, total_savings = %s", (limit, savings))
            conn.commit()
        return redirect(url_for('settings.index'))
    finally:
        conn.close()

@settings_bp.route('/end-month', methods=['POST'])
def end_month():
    now = datetime.now()
    month_str = now.strftime("%Y-%m")
    
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            # Calculate totals
            cur.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM income")
            total_income = float(cur.fetchone()['total'])
            cur.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM expense")
            total_expenses = float(cur.fetchone()['total'])
            net_savings = total_income - total_expenses

            # Update total savings
            cur.execute("SELECT total_savings FROM setting LIMIT 1")
            setting = cur.fetchone()
            if setting:
                new_savings = float(setting['total_savings']) + net_savings
                cur.execute("UPDATE setting SET total_savings = %s", (new_savings,))

            # Archive income
            cur.execute("SELECT source, amount FROM income")
            for row in cur.fetchall():
                cur.execute(
                    "INSERT INTO archived_income (source, amount, month) VALUES (%s, %s, %s)",
                    (row['source'], row['amount'], month_str)
                )

            # Archive expenses
            cur.execute("SELECT amount, category, note, date FROM expense")
            for row in cur.fetchall():
                cur.execute(
                    "INSERT INTO archived_expense (amount, category, note, date, month) VALUES (%s, %s, %s, %s, %s)",
                    (row['amount'], row['category'], row['note'], row['date'], month_str)
                )

            # Clear current data
            cur.execute("DELETE FROM income")
            cur.execute("DELETE FROM expense")
            conn.commit()
        return redirect(url_for('settings.index'))
    finally:
        conn.close()

@settings_bp.route('/fresh-start', methods=['POST'])
def fresh_start():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM archived_income")
            cur.execute("DELETE FROM archived_expense")
            cur.execute("DELETE FROM income")
            cur.execute("DELETE FROM expense")
            cur.execute("DELETE FROM setting")
            conn.commit()
        return redirect(url_for('settings.index'))
    finally:
        conn.close()