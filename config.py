import os

class Config:
    SECRET_KEY = 'devkey'  # replace in production
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/budget_db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
