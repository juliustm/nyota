"""
main.py

This is the application factory for the Nyota ✨ project.
"""

import os
import json
from datetime import timedelta
from flask import Flask, g, session, request
from flask_babel import Babel
import mistune

from config import Config
from models.nyota import db, migrate
from routes import main_bp, admin_bp

babel = Babel()

# --- Jinja2 Custom Filters ---

def format_currency(value, symbol='$'):
    if value is None:
        return f"{symbol} 0.00"
    return f"{symbol} {float(value):,.2f}"

from utils.translator import translate

# --- Language Selection for Babel ---

def get_locale():
    if 'language' in session:
        return session['language']
    # Default to Swahili if no preference is set
    return request.accept_languages.best_match(['sw', 'en']) or 'sw'


# --- Application Factory Function ---

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # --- Initialize Flask Extensions ---
    db.init_app(app)
    migrate.init_app(app, db)
    babel.init_app(app, locale_selector=get_locale)

    # --- Register Jinja2 Filters ---
    app.jinja_env.filters['format_currency'] = format_currency
    
    # This lambda function takes text, processes it with mistune, and returns HTML.
    app.jinja_env.filters['markdown'] = lambda text: mistune.html(text)

    # --- Register Blueprints ---
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)

    # --- Request Hooks ---
    @app.before_request
    def before_request_tasks():
        session.permanent = True
        app.permanent_session_lifetime = timedelta(days=30)
        g.language = get_locale()

    # --- Context Processors ---
    @app.context_processor
    def inject_global_vars():
        return dict(
            store_name="Nyota ✨",
            currency_symbol=get_currency_symbol(),
            translate=translate
        )

    def get_currency_symbol():
        from models.nyota import Creator
        creator = Creator.query.first()
        if creator:
            return creator.get_setting('payment_uza_currency', 'TZS')
        return 'TZS'
        
    return app