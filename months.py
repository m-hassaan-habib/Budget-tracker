"""Months, derived from the data rather than from a button.

Before this, "this month" meant "everything since somebody last clicked End
Month", and last month's rows lived in a different table. Now a month is just
a range of dates, and every month-scoped query looks the same.
"""

from datetime import date, datetime, timedelta

ONE_DAY = timedelta(days=1)


def month_key(value):
    """'YYYY-MM' for a date."""
    return value.strftime('%Y-%m')


def current_month():
    return month_key(date.today())


def parse_month(value):
    """'YYYY-MM' -> date of the 1st, or None if it isn't a month."""
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m').date()
    except (ValueError, TypeError):
        return None


def month_bounds(month):
    """Inclusive (first_day, last_day) for a 'YYYY-MM' string.

    Returned as dates rather than a DATE_FORMAT comparison so queries stay
    sargable against the (user_id, date) index.
    """
    start = parse_month(month) or date.today().replace(day=1)
    if start.month == 12:
        next_start = start.replace(year=start.year + 1, month=1)
    else:
        next_start = start.replace(month=start.month + 1)
    return start, next_start - ONE_DAY


def previous_month(month):
    start = parse_month(month) or date.today().replace(day=1)
    if start.month == 1:
        return month_key(start.replace(year=start.year - 1, month=12))
    return month_key(start.replace(month=start.month - 1))


def format_month(month):
    """'2026-09' -> 'September 2026'."""
    parsed = parse_month(month)
    return parsed.strftime('%B %Y') if parsed else month


def resolve_month(request):
    """The month a request is asking about, defaulting to the current one."""
    requested = request.args.get('month')
    return requested if parse_month(requested) else current_month()


def available_months(cur, user_id, tables=('expense', 'income')):
    """Every month that has any activity, newest first.

    `tables` narrows which ledgers count -- the expenses page only offers
    months it can actually show rows for. The names come from this module's
    own tuples, never from a request, so interpolating them is safe.
    """
    unions = " UNION ".join(
        "SELECT DATE_FORMAT(date, '%Y-%m') AS m FROM " + table +
        " WHERE user_id=%s AND date IS NOT NULL"
        for table in tables
    )
    cur.execute(
        "SELECT m FROM (" + unions + ") AS months ORDER BY m DESC",
        tuple(user_id for _ in tables)
    )
    return [row['m'] for row in cur.fetchall() if row['m']]


def month_options(cur, user_id, selected=None, tables=('expense', 'income')):
    """(value, label) pairs for a month dropdown, selected month guaranteed.

    A month with no rows left in it must still be selectable, otherwise the
    dropdown would silently jump the user somewhere else.
    """
    months = available_months(cur, user_id, tables)
    if selected and selected not in months:
        months = sorted([selected] + months, reverse=True)
    return [(m, format_month(m)) for m in months]
