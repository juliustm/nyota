# config.py (Final, Corrected Version based on the working example)
import os
from datetime import timedelta

class Config:
    # Standard Flask secret key
    SECRET_KEY = os.environ.get('SECRET_KEY', 'a-very-secret-key-for-local-development')

    # Session timeout configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=365)

    # --- THE PROVEN DATABASE CONFIGURATION ---
    # 1. Define the absolute path for our data directory inside the container.
    #    The application's root is '/app'.
    DATA_DIR = '/app/data'
    
    # 2. Proactively ensure this directory exists. This is the critical step.
    os.makedirs(DATA_DIR, exist_ok=True)

    # 3. Define the absolute path for the database file.
    DB_PATH = os.path.join(DATA_DIR, 'nyota.db')

    # 4. Set the SQLAlchemy URI to this explicit, absolute path.
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_PATH}"
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- UPLOAD FOLDER CONFIGURATION ---
    # Also use an absolute path for consistency.
    UPLOAD_FOLDER = '/app/static/uploads'
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)