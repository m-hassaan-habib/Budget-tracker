"""Idempotent schema and data migrations for Budget Tracker.

Safe to run as many times as you like: every step inspects the current state of
the database before changing anything, so a second run is a no-op.

    python migrate.py            # run every pending step
    python migrate.py --list     # show steps without running them

This exists because `init_db.py` executes schema.sql top to bottom, and
schema.sql contains bare `ALTER TABLE ... ADD COLUMN` statements that fail on a
database where those columns already exist. New tables still go in schema.sql
(guarded with IF NOT EXISTS) so fresh installs work from init_db.py alone;
anything that has to inspect existing data belongs here.
"""

import sys

import mysql.connector

from config import Config
from defaults import DEFAULT_CATEGORIES, DEFAULT_MEMBERS


# --------------------------------------------------------------------------
# introspection helpers
# --------------------------------------------------------------------------

def table_exists(cur, table):
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = %s",
        (table,),
    )
    return cur.fetchone()[0] > 0


def column_exists(cur, table, column):
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        (table, column),
    )
    return cur.fetchone()[0] > 0


def index_exists(cur, table, index):
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.statistics "
        "WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s",
        (table, index),
    )
    return cur.fetchone()[0] > 0


def all_user_ids(cur):
    cur.execute("SELECT id FROM users")
    return [row[0] for row in cur.fetchall()]


# --------------------------------------------------------------------------
# step registry
# --------------------------------------------------------------------------

STEPS = []


def step(name):
    def register(fn):
        STEPS.append((name, fn))
        return fn
    return register


# --------------------------------------------------------------------------
# Phase 0 — profile switcher
# --------------------------------------------------------------------------

@step("create household_member table")
def create_household_member(cur):
    if table_exists(cur, "household_member"):
        return "already present"
    cur.execute(
        """
        CREATE TABLE household_member (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            name VARCHAR(50) NOT NULL,
            UNIQUE KEY user_member_unique (user_id, name)
        )
        """
    )
    return "created"


@step("seed household members from existing done_by values")
def seed_household_members(cur):
    seeded = 0
    for user_id in all_user_ids(cur):
        cur.execute(
            "SELECT COUNT(*) FROM household_member WHERE user_id = %s", (user_id,)
        )
        if cur.fetchone()[0] > 0:
            continue

        # Prefer the names this household has actually used.
        cur.execute(
            "SELECT DISTINCT done_by FROM expense "
            "WHERE user_id = %s AND done_by IS NOT NULL AND done_by <> ''",
            (user_id,),
        )
        names = [row[0] for row in cur.fetchall()] or list(DEFAULT_MEMBERS)

        for name in names:
            cur.execute(
                "INSERT IGNORE INTO household_member (user_id, name) VALUES (%s, %s)",
                (user_id, name),
            )
            seeded += 1
    return f"seeded {seeded} member(s)" if seeded else "nothing to seed"


# --------------------------------------------------------------------------
# Phase A — quick entry
# --------------------------------------------------------------------------

@step("add icon/color columns to categories")
def add_category_presentation(cur):
    added = []
    if not column_exists(cur, "categories", "icon"):
        cur.execute("ALTER TABLE categories ADD COLUMN icon VARCHAR(50) NULL")
        added.append("icon")
    if not column_exists(cur, "categories", "color"):
        cur.execute("ALTER TABLE categories ADD COLUMN color VARCHAR(20) NULL")
        added.append("color")
    return f"added {', '.join(added)}" if added else "already present"


@step("seed categories from the previously hardcoded template list")
def seed_categories(cur):
    """Populate the categories table, which existed but was never used.

    Also picks up any category already present on an expense row but missing
    from the default list, so nothing the household has actually used
    disappears from the picker.
    """
    seeded = 0
    for user_id in all_user_ids(cur):
        for name, icon, color in DEFAULT_CATEGORIES:
            cur.execute(
                "INSERT IGNORE INTO categories (user_id, name, icon, color) "
                "VALUES (%s, %s, %s, %s)",
                (user_id, name, icon, color),
            )
            seeded += cur.rowcount

        cur.execute(
            "SELECT DISTINCT category FROM expense "
            "WHERE user_id = %s AND category IS NOT NULL AND category <> ''",
            (user_id,),
        )
        for (used,) in cur.fetchall():
            cur.execute(
                "INSERT IGNORE INTO categories (user_id, name) VALUES (%s, %s)",
                (user_id, used),
            )
            seeded += cur.rowcount

    return f"seeded {seeded} categor(ies)" if seeded else "nothing to seed"


@step("backfill icon/color on categories that lack them")
def backfill_category_presentation(cur):
    lookup = {name: (icon, color) for name, icon, color in DEFAULT_CATEGORIES}
    cur.execute("SELECT id, name FROM categories WHERE icon IS NULL OR color IS NULL")
    rows = cur.fetchall()
    for cat_id, name in rows:
        icon, color = lookup.get(name, (None, None))
        if icon:
            cur.execute(
                "UPDATE categories SET icon = %s, color = %s WHERE id = %s",
                (icon, color, cat_id),
            )
    return f"backfilled {len(rows)} row(s)" if rows else "nothing to backfill"


# --------------------------------------------------------------------------
# Phase D — change tracking
# --------------------------------------------------------------------------

@step("create activity_log table")
def create_activity_log(cur):
    if table_exists(cur, "activity_log"):
        return "already present"
    cur.execute(
        """
        CREATE TABLE activity_log (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            actor VARCHAR(50) NOT NULL,
            entity_type VARCHAR(20) NOT NULL,
            entity_id INT NULL,
            action VARCHAR(10) NOT NULL,
            before_json JSON NULL,
            after_json JSON NULL,
            undoes_log_id BIGINT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_user_time (user_id, created_at),
            INDEX idx_user_entity (user_id, entity_type, entity_id)
        )
        """
    )
    return "created"


# --------------------------------------------------------------------------
# Phase B — one ledger
#
# Stop physically moving rows into archived_* on "End Month". Keep everything
# in expense/income forever and derive the month from the date column, so a
# month-over-month comparison is one query against one table instead of a
# UNION across two tables with different schemas.
# --------------------------------------------------------------------------

@step("add date column to income")
def add_income_date(cur):
    if column_exists(cur, "income", "date"):
        return "already present"
    cur.execute("ALTER TABLE income ADD COLUMN date DATE NULL")
    return "added"


@step("backfill dates on existing income rows")
def backfill_income_dates(cur):
    """Live income rows have no date at all -- they represent the currently
    open month, so that's where they belong."""
    cur.execute(
        "UPDATE income SET date = DATE_FORMAT(CURDATE(), '%Y-%m-01') WHERE date IS NULL"
    )
    return f"dated {cur.rowcount} row(s)" if cur.rowcount else "nothing to backfill"


@step("merge archived expenses back into the ledger")
def merge_archived_expenses(cur):
    if not table_exists(cur, "archived_expense"):
        return "already merged"

    # archived_expense keeps each row's real date, so the merged rows land in
    # the month they actually happened -- which also repairs the rows that the
    # old end_month mislabelled by stamping them with the click date.
    cur.execute(
        """
        INSERT INTO expense (user_id, amount, category, note, date, attachment, done_by)
        SELECT user_id, amount, category, note, date, NULL, done_by
        FROM archived_expense
        """
    )
    return f"merged {cur.rowcount} expense row(s)"


@step("merge archived income back into the ledger")
def merge_archived_income(cur):
    if not table_exists(cur, "archived_income"):
        return "already merged"

    # archived_income only ever had a 'YYYY-MM' string, so the best available
    # date is the first of that month.
    cur.execute(
        """
        INSERT INTO income (user_id, source, amount, date)
        SELECT user_id, source, amount,
               STR_TO_DATE(CONCAT(month, '-01'), '%Y-%m-%d')
        FROM archived_income
        """
    )
    return f"merged {cur.rowcount} income row(s)"


@step("reset carried-over savings so past months aren't counted twice")
def reset_carried_savings(cur):
    """total_savings was accumulated by end_month FROM the very rows we just
    merged back in. Leaving it would count every past month twice.

    Savings is now derived: total_savings acts as an opening balance, and the
    real figure is opening_balance + SUM(income) - SUM(expense).
    """
    if not table_exists(cur, "archived_expense"):
        return "already handled"

    cur.execute("SELECT COUNT(*) FROM archived_expense")
    archived_rows = cur.fetchone()[0]
    if archived_rows == 0:
        return "no archived rows, savings left alone"

    cur.execute("UPDATE setting SET total_savings = 0 WHERE total_savings <> 0")
    return f"reset opening balance on {cur.rowcount} setting row(s)"


@step("retire the archive tables (renamed, not dropped)")
def retire_archive_tables(cur):
    """Renamed rather than dropped so the originals stay recoverable. Drop
    them in a separate step once the merged data has been eyeballed."""
    renamed = []
    for name in ("archived_expense", "archived_income"):
        if table_exists(cur, name) and not table_exists(cur, f"{name}_backup"):
            cur.execute(f"RENAME TABLE {name} TO {name}_backup")
            renamed.append(name)
    return f"renamed {', '.join(renamed)}" if renamed else "already retired"


@step("add indexes for month-scoped queries")
def add_ledger_indexes(cur):
    wanted = [
        ("expense", "idx_expense_user_date", "(user_id, date)"),
        ("expense", "idx_expense_user_category", "(user_id, category)"),
        ("income", "idx_income_user_date", "(user_id, date)"),
        ("activity_log", "idx_user_time", "(user_id, created_at)"),
    ]
    added = []
    for table, index, columns in wanted:
        if table_exists(cur, table) and not index_exists(cur, table, index):
            cur.execute(f"CREATE INDEX {index} ON {table} {columns}")
            added.append(index)
    return f"created {', '.join(added)}" if added else "already present"


# --------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------

def run():
    if "--list" in sys.argv:
        for name, _ in STEPS:
            print(f"  - {name}")
        return

    conn = mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DATABASE,
    )
    try:
        with conn.cursor() as cur:
            for name, fn in STEPS:
                outcome = fn(cur)
                conn.commit()
                print(f"[ok] {name}: {outcome}")
    except mysql.connector.Error as exc:
        conn.rollback()
        print(f"[failed] {exc}", file=sys.stderr)
        raise
    finally:
        conn.close()
    print("\nAll migrations applied.")


if __name__ == "__main__":
    run()
