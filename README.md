# Budget Tracker

A responsive, full-featured web application to manage your income, expenses, and savings. Built with Flask, MySQL, and Tailwind CSS, it is built for fast entry and a clear picture of where the money goes.

## Features

- **Quick add** — record an expense from the top of the Expenses page without a
  page load. The date and person stay put between entries, and the categories
  you actually use appear as one-click chips, so catching up on several days is
  a few keystrokes rather than a form-and-back for every line. **Repeat** clones
  a past expense onto today.
- **Month-scoped dashboard** answering three questions: where the money went
  (categories ranked biggest-first), what changed vs last month (per-category
  movers), and who spent what.
- **Track tab** — every add, edit and delete, with who made it and a field-level
  old → new diff. Any change can be undone, and each expense carries its own
  history.
- **Household members** — a profile switcher records who is at the keyboard and
  pre-fills *Done By*.
- Set monthly expense limits and track progress visually
- Browse any past month; compare two months side by side
- Responsive, mobile-friendly Tailwind UI, light and dark

### Months need no maintenance

A month is derived from each entry's own date, so September's spending is
September's whenever you record it. There is no "End Month" button to remember,
and nothing is moved between tables. Savings is derived too: the opening balance
in Settings plus all income minus all expenses.

## Tech Stack

- **Backend**: Flask (Python 3.11+), MySQL
- **Database**: MySQL (or SQLite for dev)
- **Frontend**: Jinja2 templates + Tailwind CSS
- **Charts**: CSS bar charts (no chart library)
- **Icons**: Font Awesome

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/budget-tracker.git
cd budget-tracker
```

### 2. Create virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file:

```ini
FLASK_APP=app.py
FLASK_ENV=production
MYSQL_HOST=host-name
MYSQL_USER=user-name
MYSQL_PASSWORD=your-secure-password
MYSQL_DATABASE=budget_tracker
SECRET_KEY=your-secret-key
```

### 5. Create a MySQL database (e.g. budget_tracker).

### 6. Initialize the database

```bash
python init_db.py
```

`init_db.py` runs `schema.sql`, which is the **fresh-install** schema.

### 7. Run the app

```bash
flask run
```

Visit `http://localhost:5000`, then add your household members under the
profile icon in the nav.

## Upgrading an existing database

Do **not** re-run `init_db.py` against a database that already has data. Use:

```bash
python migrate.py --list   # show the steps
python migrate.py          # apply them
```

Every step inspects the database before changing anything, so it is safe to
re-run; a second run is a no-op.

**Back up first.** One step merges `archived_expense` / `archived_income` back
into the main tables (preserving each row's real date) and renames the
originals to `*_backup` rather than dropping them. It also resets
`setting.total_savings` to zero, because that figure was accumulated from the
very rows being merged back — leaving it would count every past month twice.
Set your true opening balance in Settings afterwards.

## Folder Structure

```
.
├── app.py              # app factory, blueprint registration
├── config.py           # env config + MySQL connection pool
├── auth_utils.py       # login_required, current_actor
├── activity.py         # change tracking: snapshots, diffs, undo
├── months.py           # month boundaries derived from dates
├── defaults.py         # seed categories and members
├── migrate.py          # idempotent schema + data migrations
├── init_db.py          # fresh install, runs schema.sql
├── routes/             # one blueprint per area
├── templates/
├── static/
├── tests/
└── requirements.txt
```

## Tests

```bash
pytest
```

## Deployment

Use Gunicorn with a production WSGI server:

```bash
gunicorn -w 4 app:app
```
