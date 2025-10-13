from flask import Flask, session
from flask_discord import DiscordOAuth2Session
from flask_wtf.csrf import CSRFProtect
from datetime import datetime
from config import Config
from models.user import is_user_admin

# Import all route blueprints
from routes.auth import auth_bp, init_discord, enforce_session_version, inject_is_user_admin
from routes.main import main_bp
from routes.user import user_bp
from routes.api import api_bp
from routes.payments import payments_bp, inject_stripe_key
from routes.admin import admin_bp
from routes.pdf_api import pdf_api_bp

def create_app():
    """Application factory pattern."""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(Config)
    
    # Initialize CSRF Protection
    csrf = CSRFProtect(app)
    
    # Exempt API endpoints that use token-based authentication from CSRF
    csrf.exempt(pdf_api_bp)  # PDF API uses bearer tokens
    
    # Initialize Discord OAuth
    global discord
    discord = init_discord(app)
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(pdf_api_bp)
    
    # Exempt specific token-protected API endpoints from CSRF
    csrf.exempt('api.ingest_flashcards')
    
    # Register template filters and context processors
    @app.template_filter('datetimeformat')
    def datetimeformat_filter(value):
        try:
            return datetime.utcfromtimestamp(int(value)).strftime('%Y-%m-%d %H:%M')
        except Exception:
            return value
    
    @app.before_request
    def before_request():
        enforce_session_version()
    
    @app.context_processor
    def context_processors():
        return {
            **inject_is_user_admin(),
            **inject_stripe_key()
        }
    
    return app

# Create the app instance
app = create_app()

if __name__ == "__main__":
    import os
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    app.run(host='127.0.0.1', debug=True, port=2456)
