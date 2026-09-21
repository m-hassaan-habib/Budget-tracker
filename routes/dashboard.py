"""The dashboard, scoped to one month and built to answer three questions:

    where did the money go · what changed vs last month · who spent what

It used to sum the whole table with no date filter at all, so the headline
numbers meant "since somebody last clicked End Month" rather than "this month".
Two other things are fixed here by construction rather than by patching:

  * the daily series is grouped and ordered by the real date. It used to order
    by DATE_FORMAT(date,'%b %d') -- a string -- so "Apr 01" sorted before
    "Jan 02" and the chart ran in alphabetical order.
  * income and expense are aggregated in separate queries and combined in
    Python. The old savings figure joined income to expense on user_id alone,
    which multiplies every income row by every expense row.
"""

from flask import Blueprint, render_template, current_app, session, request
from auth_utils import login_required
from months import (
    available_months, format_month, month_bounds, previous_month, resolve_month
)

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='')

TOP_CATEGORIES = 8
TOP_MOVERS = 6


def _total(cur, table, user_id, start, end):
    cur.execute(
        f"SELECT COALESCE(SUM(amount),0) AS total FROM {table} "
        "WHERE user_id=%s AND date BETWEEN %s AND %s",
        (user_id, start, end)
    )
    return float(cur.fetchone()['total'])


def _by_category(cur, user_id, start, end):
    cur.execute(
        """
        SELECT category, SUM(amount) AS total, COUNT(*) AS count
        FROM expense
        WHERE user_id=%s AND date BETWEEN %s AND %s
        GROUP BY category
        ORDER BY total DESC
        """,
        (user_id, start, end)
    )
    return {r['category']: {'total': float(r['total']), 'count': int(r['count'])}
            for r in cur.fetchall()}


def _movers(this_month, last_month, limit=TOP_MOVERS):
    """Biggest changes vs last month, largest absolute swing first.

    This is the signal a household can actually act on -- "Grocery is up
    Rs 8,400" is a decision, where a total is just a number.
    """
    names = set(this_month) | set(last_month)
    deltas = []
    for name in names:
        now = this_month.get(name, {}).get('total', 0.0)
        before = last_month.get(name, {}).get('total', 0.0)
        change = now - before
        if round(change, 2) == 0:
            continue
        deltas.append({
            'category': name,
            'now': now,
            'before': before,
            'change': change,
            'percent': (change / before * 100) if before else None,
            'is_new': before == 0,
            'stopped': now == 0,
        })

    deltas.sort(key=lambda d: abs(d['change']), reverse=True)
    return deltas[:limit]


@dashboard_bp.route('/')
@login_required
def index():
    user_id = session['user_id']
    month = resolve_month(request)
    prev = previous_month(month)
    start, end = month_bounds(month)
    prev_start, prev_end = month_bounds(prev)

    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute(
                "SELECT monthly_limit, total_savings, use_automated_income "
                "FROM setting WHERE user_id=%s LIMIT 1",
                (user_id,)
            )
            setting = cur.fetchone()
            monthly_limit = float(setting['monthly_limit']) if setting else 0.0
            opening_balance = float(setting['total_savings']) if setting else 0.0
            use_automated_income = bool(setting['use_automated_income']) if setting else False

            month_expenses = _total(cur, 'expense', user_id, start, end)
            last_month_expenses = _total(cur, 'expense', user_id, prev_start, prev_end)
            month_manual_income = _total(cur, 'income', user_id, start, end)

            # "Automated" mode treats what was spent as what came in.
            month_income = month_expenses if use_automated_income else month_manual_income
            net = month_income - month_expenses

            categories = _by_category(cur, user_id, start, end)
            last_categories = _by_category(cur, user_id, prev_start, prev_end)

            # Who spent what, and what each person spent it on.
            cur.execute(
                """
                SELECT done_by, category, SUM(amount) AS total, COUNT(*) AS count
                FROM expense
                WHERE user_id=%s AND date BETWEEN %s AND %s
                GROUP BY done_by, category
                """,
                (user_id, start, end)
            )
            people = {}
            for row in cur.fetchall():
                person = people.setdefault(
                    row['done_by'] or 'Unknown',
                    {'name': row['done_by'] or 'Unknown', 'total': 0.0, 'count': 0,
                     'top_category': None, '_top': 0.0}
                )
                amount = float(row['total'])
                person['total'] += amount
                person['count'] += int(row['count'])
                if amount > person['_top']:
                    person['_top'] = amount
                    person['top_category'] = row['category']
            people = sorted(people.values(), key=lambda p: p['total'], reverse=True)

            # Daily series, grouped and ordered by the real date.
            cur.execute(
                """
                SELECT date, SUM(amount) AS total
                FROM expense
                WHERE user_id=%s AND date BETWEEN %s AND %s
                GROUP BY date
                ORDER BY date
                """,
                (user_id, start, end)
            )
            daily = [{'date': r['date'], 'total': float(r['total'])} for r in cur.fetchall()]

            cur.execute(
                """
                SELECT id, amount, category, note, date, done_by
                FROM expense
                WHERE user_id=%s
                ORDER BY date DESC, id DESC
                LIMIT 5
                """,
                (user_id,)
            )
            recent_expenses = cur.fetchall()

            cur.execute(
                "SELECT COUNT(*) AS cnt FROM expense WHERE user_id=%s AND date BETWEEN %s AND %s",
                (user_id, start, end)
            )
            expense_count = int(cur.fetchone()['cnt'])

            # Savings is derived now: an opening balance plus everything since.
            cur.execute(
                "SELECT COALESCE(SUM(amount),0) AS total FROM income WHERE user_id=%s",
                (user_id,)
            )
            all_income = float(cur.fetchone()['total'])
            cur.execute(
                "SELECT COALESCE(SUM(amount),0) AS total FROM expense WHERE user_id=%s",
                (user_id,)
            )
            all_expense = float(cur.fetchone()['total'])

            months = available_months(cur, user_id)
    finally:
        conn.close()

    total_savings = opening_balance + all_income - all_expense
    movers = _movers(categories, last_categories)

    ranked = sorted(categories.items(), key=lambda kv: kv[1]['total'], reverse=True)
    top_categories = [
        {'name': name, 'total': data['total'], 'count': data['count'],
         'share': (data['total'] / month_expenses * 100) if month_expenses else 0}
        for name, data in ranked[:TOP_CATEGORIES]
    ]
    other_total = sum(d['total'] for _, d in ranked[TOP_CATEGORIES:])
    if other_total:
        top_categories.append({
            'name': 'Other', 'total': other_total,
            'count': sum(d['count'] for _, d in ranked[TOP_CATEGORIES:]),
            'share': (other_total / month_expenses * 100) if month_expenses else 0,
        })

    month_change = month_expenses - last_month_expenses

    if month not in months:
        months = [month] + months

    return render_template(
        "dashboard.html",
        month=month,
        month_display=format_month(month),
        previous_month_display=format_month(prev),
        month_options=[(m, format_month(m)) for m in months],
        month_expenses=month_expenses,
        last_month_expenses=last_month_expenses,
        month_change=month_change,
        month_change_percent=(month_change / last_month_expenses * 100) if last_month_expenses else None,
        month_income=month_income,
        net=net,
        total_savings=total_savings,
        monthly_limit=monthly_limit,
        use_automated_income=use_automated_income,
        top_categories=top_categories,
        max_category_total=max((c['total'] for c in top_categories), default=0),
        movers=movers,
        max_mover_change=max((abs(m['change']) for m in movers), default=0),
        people=people,
        max_person_total=max((p['total'] for p in people), default=0),
        daily=daily,
        max_daily=max((d['total'] for d in daily), default=0),
        recent_expenses=recent_expenses,
        expense_count=expense_count,
    )
