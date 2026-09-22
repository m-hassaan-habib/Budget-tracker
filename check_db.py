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


def money(snap, table):
    return float(snap["sums"].get(table, 0) or 0)


def expected_after(before, live, archived):
    """What the live table should total once the archive is merged into it.

    The `*_backup` tables are a retained copy of rows that now also live in
    the main table, so they must NOT be added to the live total -- doing that
    counts every archived row twice.
    """
    return money(before, live) + money(before, archived)


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

        print("\nMONEY (live table after == live + archived before)")
        ok = True
        for label, live, archived in (("expenses", "expense", "archived_expense"),
                                      ("income", "income", "archived_income")):
            want = expected_after(before, live, archived)
            got = money(after, live)
            match = abs(want - got) < 0.01
            ok = ok and match
            print(f"  {label:9} live {money(before, live):>13,.2f}"
                  f" + archived {money(before, archived):>13,.2f}"
                  f" = {want:>13,.2f} | actual {got:>13,.2f}  {'OK' if match else 'MISMATCH'}")

        print("\n  retained copies (must still match what was archived):")
        for label, archived in (("expenses", "archived_expense"), ("income", "archived_income")):
            want = money(before, archived)
            got = money(after, f"{archived}_backup")
            match = abs(want - got) < 0.01
            ok = ok and match
            print(f"  {label:9} {archived}_backup {got:>13,.2f} vs original "
                  f"{want:>13,.2f}  {'OK' if match else 'MISMATCH'}")

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
