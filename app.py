import os
from flask import Flask, send_from_directory, session
from flask_wtf.csrf import CSRFProtect
from config import Config
from auth_utils import login_required
from routes.dashboard import dashboard_bp
from routes.expenses import expenses_bp
from routes.income import income_bp
from routes.settings import settings_bp
from routes.history import history_bp
from routes.auth import auth_bp
from routes.categories import categories_bp

csrf = CSRFProtect()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if not app.config.get("SECRET_KEY") or app.config["SECRET_KEY"] == "your-secret-key":
        import secrets
        app.config["SECRET_KEY"] = secrets.token_hex(32)

    # Session cookie security
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")

    csrf.init_app(app)
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

    # Security headers
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # Authenticated file serving routes
    @app.route('/uploads/avatars/<path:filename>')
    @login_required
    def avatar_file(filename):
        return send_from_directory(app.config['AVATAR_FOLDER'], filename)

    @app.route('/uploads/receipts/<path:filename>')
    @login_required
    def receipt_file(filename):
        return send_from_directory(app.config['RECEIPT_FOLDER'], filename)

    # Jinja2 filter
    def clamp_filter(value, min_val=0, max_val=100):
        try:
            return max(min(float(value), max_val), min_val)
        except (ValueError, TypeError):
            return 0
    app.jinja_env.filters['clamp'] = clamp_filter

    return app

app = create_app()
