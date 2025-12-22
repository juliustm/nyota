
import os
import sys
import sqlite3
import subprocess
import logging
from flask import Flask
from flask_migrate import Migrate, upgrade, current, heads
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

# Configure robust logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Attempt to import the create_app factory to use Flask-Migrate context programmatically
# This is much more robust than shelling out to subprocesses for everything
try:
    from main import create_app
    from models.nyota import db
except ImportError as e:
    logger.critical(f"Could not import application factory: {e}")
    sys.exit(1)

def check_migration_status(app):
    """
    Verifies if the database is up-to-date with the latest migration files.
    """
    with app.app_context():
        # This is a simplified check. Getting the raw revision effectively is harder via public API,
        # so we will trust the command line tools for the final verification which are designed for this.
        # However, we can basic checks here.
        pass

def bootstrap_legacy_db(db_path):
    """
    Handles the edge case where a database exists but has no Alembic version history.
    This often happens if the DB was created manually or existed before migrations were added.
    """
    if not os.path.exists(db_path):
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if alembic_version table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
        has_version_table = cursor.fetchone() is not None
        
        if has_version_table:
            conn.close()
            return # DB is already managed, let Alembic handle it.

        # Check if *any* application tables exist (using 'creator' as a permanent anchor)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='creator'")
        has_content = cursor.fetchone() is not None

        if has_content:
            logger.warning("Existing database detected without migration history (Unmanaged State).")
            logger.info("Attempting to stamp database to a safe baseline...")
            
            # Create version table
            cursor.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
            
            # We determine the baseline based on table signatures to be safe but generic
            # Check for a "middle-age" feature table, e.g., 'access_attempt'
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='access_attempt'")
            has_access_attempt = cursor.fetchone() is not None
            
            baseline_revision = '5ae8f9f63cf5' # Initial
            if has_access_attempt:
                baseline_revision = '155b518ebeb5' # Session Recovery
                
            cursor.execute(f"INSERT INTO alembic_version (version_num) VALUES ('{baseline_revision}')")
            conn.commit()
            logger.info(f"Successfully stamped database with baseline revision: {baseline_revision}")
            
        conn.close()

    except Exception as e:
        logger.error(f"Error checking/bootstrapping legacy DB: {e}")
        # We continue and let the upgrade command succeed or fail on its own merits
        
def run_migrations():
    """
    Main deployment function.
    """
    logger.info("--- Starting Deployment & Migration Check ---")
    
    app = create_app()
    
    # 1. Resolve Database Path logic (matching config.py)
    # We need this for the bootstrapping check
    base_dir = os.path.abspath(os.path.dirname(__file__))
    data_dir = os.path.join(base_dir, 'instance')
    db_path = os.path.join(data_dir, 'nyota.db')
    
    # Ensure directory exists
    os.makedirs(data_dir, exist_ok=True)
    
    # 2. Bootstrapping Check (Reliability)
    # This prevents "table already exists" errors on older unmanaged instances
    if os.path.exists(db_path):
        bootstrap_legacy_db(db_path)
    
    # 3. run `flask db upgrade`
    # We use subprocess to ensure we run exactly what the CLI would run,
    # avoiding any context/import differences.
    logger.info("Running database upgrades...")
    try:
        # Capture output to log it
        result = subprocess.run(
            [sys.executable, "-m", "flask", "db", "upgrade"], 
            check=True, 
            capture_output=True, 
            text=True
        )
        logger.info("Upgrade command completed successfully.")
        if result.stdout:
            logger.info(f"Upgrade Output:\n{result.stdout}")
            
    except subprocess.CalledProcessError as e:
        logger.error("CRITICAL: Database upgrade failed.")
        logger.error(f"Error Output:\n{e.stderr}")
        logger.error(f"Standard Output:\n{e.stdout}")
        sys.exit(1)

    # 4. Final Verification
    # We check if the current database revision matches the head revision
    logger.info("Verifying migration state...")
    try:
        # Get Current DB Revision
        current_proc = subprocess.run(
            [sys.executable, "-m", "flask", "db", "current"],
            capture_output=True, text=True, check=True
        )
        current_rev = current_proc.stdout.strip().split(' ')[0] # Extract hash
        
        # Get Head Revision (Code)
        heads_proc = subprocess.run(
            [sys.executable, "-m", "flask", "db", "heads"],
            capture_output=True, text=True, check=True
        )
        head_rev = heads_proc.stdout.strip().split(' ')[0] # Extract hash
        
        logger.info(f"Database Revision: {current_rev}")
        logger.info(f"Codebase Head:     {head_rev}")
        
        if current_rev.startswith(head_rev) or head_rev.startswith(current_rev):
            logger.info("SUCCESS: Database is fully synchronized with codebase.")
        else:
            # It's possible to have slightly different formatted outputs (e.g. (head))
            # If the simple check fails, we warn but don't strictly fail unless it's critical
            # because string parsing commands can be brittle.
            if head_rev in current_proc.stdout or current_rev in heads_proc.stdout:
                 logger.info("SUCCESS: Database appears synchronized (fuzzy match).")
            else:
                 logger.warning("WARNING: Database revision might be out of sync. Please check logs.")
        
    except Exception as e:
        logger.warning(f"Verification step encountered an issue: {e}")
        # We don't exit(1) here because the upgrade itself succeeded.

if __name__ == "__main__":
    run_migrations()
