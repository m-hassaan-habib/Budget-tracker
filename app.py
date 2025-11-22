import os
from flask import Flask, send_from_directory
from config import Config
from routes.dashboard import dashboard_bp
from routes.expenses import expenses_bp
from routes.income import income_bp
from routes.settings import settings_bp
from routes.history import history_bp
from routes.auth import auth_bp
from routes.categories import categories_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    if not app.config.get("SECRET_KEY"):
        import secrets
        app.config["SECRET_KEY"] = secrets.token_hex(32)

    Config.init_db(app)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['AVATAR_FOLDER'], exist_ok=True)
    os.makedirs(app.config['RECEIPT_FOLDER'], exist_ok=True)

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(income_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(categories_bp)

    return app

app = create_app()

def clamp_filter(value, min_val=0, max_val=100):
    try:
        return max(min(float(value), max_val), min_val)
    except (ValueError, TypeError):
        return 0

app.jinja_env.filters['clamp'] = clamp_filter

@app.route('/uploads/avatars/<path:filename>')
def avatar_file(filename):
    return send_from_directory(app.config['AVATAR_FOLDER'], filename)

@app.route('/uploads/receipts/<path:filename>')
def receipt_file(filename):
    return send_from_directory(app.config['RECEIPT_FOLDER'], filename)
