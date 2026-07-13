"""
main.py

This is the application factory for the Nyota ✨ project.
"""

import os
import json
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from flask import Flask, g, session, request
from flask_babel import Babel
import mistune
from flask_compress import Compress

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
    
    # Check headers for country code (Cloudflare, App Engine, or Generic)
    country = request.headers.get('CF-IPCountry') or \
              request.headers.get('X-AppEngine-Country') or \
              request.headers.get('X-Country-Code')
    
    # If a country is detected and it is NOT Tanzania, default to English
    if country and country.upper() != 'TZ':
        return 'en'
        
    # Default to Swahili for Tanzania and all unknown locations
    return 'sw'


# --- Application Factory Function ---

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Trust the reverse proxy's X-Forwarded-Proto header so request.url_root
    # uses https:// instead of http:// when behind nginx/Cloudflare.
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    # --- Initialize Flask Extensions ---
    db.init_app(app)
    migrate.init_app(app, db)
    babel.init_app(app, locale_selector=get_locale)
    Compress(app)
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # 1 year cache for static files

    # Static files are cached for a year, so every url_for('static', ...) carries a
    # ?v=<mtime> stamp — editing a CSS/JS file changes the URL and busts the cache.
    _static_versions = {}

    @app.url_defaults
    def add_static_version(endpoint, values):
        if endpoint != 'static' or 'filename' not in values:
            return
        filename = values['filename']
        version = _static_versions.get(filename)
        if version is None or app.debug:
            path = os.path.join(app.static_folder, filename)
            try:
                version = str(int(os.path.getmtime(path)))
            except OSError:
                version = ''
            _static_versions[filename] = version
        if version:
            values['v'] = version

    # --- Register Jinja2 Filters ---
    app.jinja_env.filters['format_currency'] = format_currency

    def nl2br(value):
        from markupsafe import Markup, escape
        if not value:
            return ""
        return Markup(str(escape(value)).replace('\n', '<br>\n'))
    
    app.jinja_env.filters['nl2br'] = nl2br
    
    # This lambda function takes text, processes it with mistune, and returns HTML.
    app.jinja_env.filters['markdown'] = lambda text: mistune.html(text)

    def local_dt_filter(dt, fmt='%b %d, %Y %I:%M %p'):
        """Convert a naive UTC datetime to the creator's local timezone."""
        if dt is None:
            return ''
        tz_str = None
        if hasattr(g, 'creator') and g.creator:
            tz_str = g.creator.get_setting('creator_timezone')
        if not tz_str:
            return dt.strftime(fmt)
        try:
            local = dt.replace(tzinfo=ZoneInfo('UTC')).astimezone(ZoneInfo(tz_str))
            return local.strftime(fmt)
        except (ZoneInfoNotFoundError, Exception):
            return dt.strftime(fmt)

    app.jinja_env.filters['local_dt'] = local_dt_filter

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

    @app.context_processor
    def inject_site_footer():
        """Make the footer available to every storefront page.

        Routes pass `creator` inconsistently (the library and recovery pages
        don't), so the footer resolves the creator itself rather than depending
        on each route to remember. Admin pages don't render it.
        """
        if request.blueprint == 'admin':
            return {}

        from models.nyota import Creator
        from utils.site_meta import build_site_footer, build_structured_data

        try:
            creator = Creator.query.first()
            footer = build_site_footer(creator)
            return dict(
                site_footer=footer,
                site_schema=build_structured_data(creator, footer),
            )
        except Exception as exc:
            # Pre-setup (no tables yet) or a bad settings row must not 500 the store.
            app.logger.warning(f"Footer context unavailable: {exc}")
            return dict(site_footer={'enabled': False}, site_schema=None)

    def get_currency_symbol():
        from models.nyota import Creator
        creator = Creator.query.first()
        if creator:
            return creator.get_setting('payment_uza_currency', 'TZS')
        return 'TZS'

    # --- Cache Headers for Static Assets ---
    @app.after_request
    def add_cache_headers(response):
        if request.path.startswith('/static/'):
            response.cache_control.max_age = 31536000
            response.cache_control.public = True
        return response

    # Start background worker (scheduled campaigns + subscription reminders).
    # Suppressed during flask db migrate / flask db upgrade via env var.
    import os
    if not os.environ.get('FLASK_SKIP_BACKGROUND_WORKER'):
        from services.background_tasks import start_background_worker
        start_background_worker(app)

    return app