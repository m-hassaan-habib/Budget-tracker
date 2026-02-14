"""
Budget Tracker Test Suite

This package contains comprehensive tests for the Budget Tracker application:

- test_auth.py: Authentication tests (signup, login, logout, profile)
- test_dashboard.py: Dashboard and KPI tests
- test_income.py: Income CRUD tests (Expected & Actual income)
- test_expenses.py: Expense CRUD tests with attachments
- test_settings.py: Settings, end-month, and fresh-start tests
- test_history.py: Archived data and comparison tests
- test_categories.py: Category management tests
- test_security.py: Security-focused tests (CSRF, headers, validation)

Run all tests:
    pytest tests/

Run specific test file:
    pytest tests/test_auth.py

Run with verbose output:
    pytest tests/ -v

Run with coverage:
    pytest tests/ --cov=. --cov-report=html
"""
