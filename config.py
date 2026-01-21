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


    # --- PERSISTENCE CONFIGURATION ---
    # We use '/nyota' as the immutable persistence volume.
    # In production/docker, this should be a volume mount.
    # For local dev without docker, we can fallback to a local folder or just use absolute path if writable.
    PERSISTENCE_DIR = os.environ.get('PERSISTENCE_DIR', '/nyota')

    # 1. Database Directory
    DB_DIR = os.path.join(PERSISTENCE_DIR, 'db')
    os.makedirs(DB_DIR, exist_ok=True)

    # 2. Database URI
    DB_PATH = os.path.join(DB_DIR, 'nyota.db')
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 3. User Data Directory (Uploads)
    USER_DATA_DIR = os.path.join(PERSISTENCE_DIR, 'userdata')
    os.makedirs(USER_DATA_DIR, exist_ok=True)

    # Specific subfolders for organization
    COVERS_DIR = os.path.join(USER_DATA_DIR, 'covers')
    LOGOS_DIR = os.path.join(USER_DATA_DIR, 'logos')
    SECURE_UPLOADS_DIR = os.path.join(USER_DATA_DIR, 'secure_uploads')
    
    os.makedirs(COVERS_DIR, exist_ok=True)
    os.makedirs(LOGOS_DIR, exist_ok=True)
    os.makedirs(SECURE_UPLOADS_DIR, exist_ok=True)

    # Keep Reference to Base Dir for other things if needed
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))