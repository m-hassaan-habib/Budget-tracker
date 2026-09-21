"""Snapshot the shape of the database. Run BEFORE and AFTER migrating.

Reads connection details from .env -- no credentials on the command line,
nothing to paste into a chat window.

    python check_db.py before
    python check_db.py after
    python check_db.py compare
"""
import json
import os
import sys

import mysql.connector
from dotenv import load_dotenv

load_dotenv()

TABLES = [
    "users", "income", "expense", "setting", "categories",
    "household_member", "activity_log",
    "archived_income", "archived_expense",
    "archived_income_backup", "archived_expense_backup",
]


def snapshot():
    conn = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE"),
    )
    out = {"tables": {}, "sums": {}}
    try:
        with conn.cursor() as cur:
            for table in TABLES:
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = DATABASE() AND table_name = %s",
                    (table,),
                )
                if not cur.fetchone()[0]:
                    continue
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                out["tables"][table] = cur.fetchone()[0]

            # Money totals -- the numbers that must not change.
            for table in ("expense", "income", "archived_expense", "archived_income",
                          "archived_expense_backup", "archived_income_backup"):
                if table in out["tables"]:
                    cur.execute(f"SELECT COALESCE(SUM(amount),0) FROM {table}")
                    out["sums"][table] = str(cur.fetchone()[0])
    finally:
        conn.close()
    return out


def total_expense_money(snap):
    """All expense money, wherever it currently lives."""
    return sum(float(snap["sums"].get(t, 0)) for t in
               ("expense", "archived_expense", "archived_expense_backup"))


def total_income_money(snap):
    return sum(float(snap["sums"].get(t, 0)) for t in
               ("income", "archived_income", "archived_income_backup"))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "before"

    if mode == "compare":
        before = json.load(open("db-before.json"))
        after = json.load(open("db-after.json"))

        print("TABLE ROW COUNTS")
        for table in sorted(set(before["tables"]) | set(after["tables"])):
            b = before["tables"].get(table, "-")
            a = after["tables"].get(table, "-")
            flag = "" if b == a else "   <-- changed"
            print(f"  {table:28} {str(b):>8} -> {str(a):>8}{flag}")

        print("\nMONEY (must match -- rows moved tables, nothing was created or lost)")
        ok = True
        for label, fn in (("expenses", total_expense_money), ("income", total_income_money)):
            b, a = fn(before), fn(after)
            match = abs(b - a) < 0.01
            ok = ok and match
            print(f"  total {label:10} {b:>14,.2f} -> {a:>14,.2f}   {'OK' if match else 'MISMATCH'}")

        print("\n" + ("PASS - no money gained or lost" if ok
                      else "FAIL - STOP AND RESTORE THE BACKUP"))
        sys.exit(0 if ok else 1)

    snap = snapshot()
    path = f"db-{mode}.json"
    json.dump(snap, open(path, "w"), indent=2)
    print(f"wrote {path}")
    for table, count in snap["tables"].items():
        print(f"  {table:28} {count:>8}")


if __name__ == "__main__":
    main()
