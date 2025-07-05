from flask import Flask
from config import Config
from models import db
from flask_migrate import Migrate

from routes.dashboard import dashboard_bp
from routes.expenses import expenses_bp
from routes.income import income_bp
from routes.settings import settings_bp
from routes.history import history_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    Migrate(app, db)

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(income_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(history_bp)


    return app



app = create_app()


def clamp_filter(value, min_val=0, max_val=100):
    try:
        return max(min(float(value), max_val), min_val)
    except (ValueError, TypeError):
        return 0

app.jinja_env.filters['clamp'] = clamp_filter
