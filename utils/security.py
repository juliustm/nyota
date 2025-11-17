"""
security.py

This module contains all security-related functions and decorators for the Nyota ✨ application.
It handles route protection for both Creators (Admins) and Customers (Users), as well as
the generation and verification of authentication tokens.
"""

import pyotp
import uuid
from functools import wraps
from flask import session, redirect, url_for, flash, g, request, jsonify
from models.nyota import Creator, Customer, Purchase # Assuming Purchase model will exist

# --- Decorators for Route Protection ---

def creator_login_required(f):
    """
    Ensures that the current user is a logged-in Creator (Admin).
    If not, they are redirected to the admin login page. This decorator is
    used to protect the entire creator dashboard.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Check if the creator's ID is in the session cookie.
        if 'creator_id' not in session:
            flash('Please log in to access the creator dashboard.', 'warning')
            return redirect(url_for('admin.creator_login'))

        # 2. Fetch the creator from the database to ensure they still exist.
        #    This prevents issues if a creator is deleted but their session persists.
        #    We store the object in Flask's `g` for easy access in the view function.
        g.creator = Creator.query.get(session['creator_id'])
        if g.creator is None:
            session.clear() # Clear the invalid session
            flash('Your account could not be found. Please log in again.', 'danger')
            return redirect(url_for('admin.creator_login'))

        return f(*args, **kwargs)
    return decorated_function

def customer_access_required(f):
    """
    Ensures a valid customer access token is present in the session.
    This is NOT a traditional login. It verifies that the user has arrived
    via a valid purchase link and loads their context (Customer, Purchase)
    into the `g` object for use in the view.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Check for the transaction token, which acts as the key to the customer's library.
        token = session.get('current_transaction_token')
        if not token:
            # If it's an API request (e.g., fetching more files), return a JSON error.
            if request.path.startswith('/api/'):
                return jsonify({'error': 'No valid access token found in session.'}), 401
            # For page loads, redirect to the main page with a message.
            flash('Your access link is invalid or has expired. Please use the link sent to your WhatsApp.', 'info')
            return redirect(url_for('main.landing_page'))

        # 2. Find the purchase associated with this token.
        #    We use .first() because the token is unique.
        purchase = Purchase.query.filter_by(transaction_token=token).first()
        if not purchase:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Invalid access token.'}), 403 # 403 Forbidden is more appropriate
            flash('Your access link is invalid.', 'danger')
            session.pop('current_transaction_token', None) # Clear the bad token
            return redirect(url_for('main.landing_page'))

        # 3. Success! Load the customer and their purchase into the `g` object.
        g.customer = purchase.customer
        g.purchase = purchase
        return f(*args, **kwargs)
    return decorated_function

# --- Token Generation Functions ---

def generate_transaction_token():
    """
    Generates a unique, unguessable token for a customer's purchase.
    This token is the key to their personal content library.
    """
    return str(uuid.uuid4())


# --- TOTP (Creator Two-Factor Authentication) Functions ---

def generate_totp_secret():
    """Generates a new random base32 secret for TOTP."""
    return pyotp.random_base32()

def get_totp_uri(username, secret):
    """
    Generates the provisioning URI for scanning into an authenticator app.
    This URI contains the secret, username, and issuer name.
    """
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=username,
        issuer_name="Nyota ✨"  # Customized for our application
    )

def verify_totp(secret, token):
    """
    Verifies a given TOTP token (6-digit code from the app) against
    the creator's stored secret.
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(token)