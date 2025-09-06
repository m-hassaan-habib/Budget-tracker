# Budget Tracker

A responsive, full-featured web application to manage your income, expenses, and savings. Built with Flask, MySQL, and Tailwind CSS, it provides a modern UI, charts, and a clear financial overview.

## Features

- Add, edit, and delete income streams and expenses
- Set monthly expense limits and track progress visually
- Automatically calculate net savings
- Archive data monthly and view past months
- Interactive charts (Pie, Bar, Line) using Chart.js
- Responsive, mobile-friendly Tailwind UI
- Secure and clean codebase

## Tech Stack

- **Backend**: Flask (Python 3.11+), MySQL
- **Database**: MySQL (or SQLite for dev)
- **Frontend**: Jinja2 templates + Tailwind CSS
- **Charts**: Chart.js
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

### 7. Run the app

```bash
flask run
```

Visit `http://localhost:5000`

## Folder Structure

```
.
├── app/
│   ├── models.py
│   ├── routes/
│   ├── templates/
│   ├── static/
├── requirements.txt
├── README.md
├── config.py
├── .env
└── run.py
```

## Deployment

Use Gunicorn with a production WSGI server:

```bash
gunicorn -w 4 app:app
```
