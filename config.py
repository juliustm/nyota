# config.py (Final, Corrected Version based on the working example)
import os
from datetime import timedelta

class Config:
    # Standard Flask secret key
    SECRET_KEY = os.environ.get('SECRET_KEY', 'a-very-secret-key-for-local-development')

    # Session timeout configuration (90 days for buyer convenience)
    PERMANENT_SESSION_LIFETIME = timedelta(days=90)
    
    # Security flags for session cookies
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False') == 'True'  # True in production (HTTPS)
    SESSION_COOKIE_HTTPONLY = True  # Prevent XSS attacks
    SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection while allowing normal navigation


    # --- THE PROVEN DATABASE CONFIGURATION ---
    # 1. Define the absolute path for our data directory.
    #    Use current working directory for local development.
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    DATA_DIR = os.path.join(BASE_DIR, 'instance')
    
    # 2. Proactively ensure this directory exists. This is the critical step.
    os.makedirs(DATA_DIR, exist_ok=True)

    # 3. Define the absolute path for the database file.
    DB_PATH = os.path.join(DATA_DIR, 'nyota.db')

    # 4. Set the SQLAlchemy URI to this explicit, absolute path.
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_PATH}"
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- UPLOAD FOLDER CONFIGURATION ---
    # Also use an absolute path for consistency.
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)