"""
routes.py

Defines all web routes for the Nyota Digital application, organized into blueprints
for public-facing pages (main_bp) and the creator's hub (admin_bp).
Includes Server-Sent Events (SSE) for real-time updates.
"""

import queue
import json
import random
import time
import threading
import uuid
import qrcode
import io
import base64
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, session, g,
    jsonify, make_response, Response
)

from models.nyota import db, Creator
from utils.security import creator_login_required, generate_totp_secret, get_totp_uri, verify_totp
from utils.translator import translate
from mock_data import mock_assets, mock_purchased_assets

# --- Real-time Event Manager for Asynchronous Tasks ---
class SseManager:
    """Manages multiple client-specific SSE queues for async operations like payments."""
    def __init__(self):
        self.channels = {}
        self.lock = threading.Lock()

    def subscribe(self, channel_id):
        with self.lock:
            q = queue.Queue(maxsize=5)
            self.channels[channel_id] = q
            return q

    def unsubscribe(self, channel_id):
        with self.lock:
            if channel_id in self.channels:
                del self.channels[channel_id]

    def publish(self, channel_id, event_data):
        with self.lock:
            if channel_id in self.channels:
                q = self.channels[channel_id]
                sse_msg = f"data: {json.dumps(event_data)}\n\n"
                try:
                    q.put_nowait(sse_msg)
                except queue.Full:
                    pass # Ignore if client's queue is full

# A single global instance of the SSE manager
sse_manager = SseManager()


# --- Blueprint Definitions ---
main_bp = Blueprint('main', __name__)
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# ==============================================================================
# == MAIN BLUEPRINT (Public Storefront & Customer Library)
# ==============================================================================

@main_bp.route('/')
def landing_page():
    """Renders the main creator storefront."""
    return render_template('user/index.html', assets=mock_assets)
    

@main_bp.route('/asset/<slug>')
def asset_detail(slug):
    """Displays the detailed page for a single digital asset."""
    asset = next((a for a in mock_assets if a['slug'] == slug), None)
    if not asset:
        flash(translate('asset_not_found'), 'danger')
        return redirect(url_for('main.landing_page'))
    return render_template('user/asset_detail.html', asset=asset)

@main_bp.route('/access/<token>')
def customer_access(token):
    """Entry point for a customer after purchase to access their library."""
    session['current_customer_phone'] = token # Using token as a mock phone number for now
    flash(translate('library_access_granted'), 'success')
    return redirect(url_for('main.library'))

@main_bp.route('/library')
def library():
    """Displays the customer's personal library of ONLY purchased assets."""
    return render_template('user/library.html', assets=mock_purchased_assets)

@main_bp.route('/set-language/<lang>')
def set_language(lang):
    """Sets the user's preferred language in the session."""
    if lang in ['en', 'sw']:
        session['language'] = lang
    return redirect(request.referrer or url_for('main.landing_page'))


# --- Asynchronous Checkout Flow ---
def mock_payment_worker(channel_id, phone_number, success_redirect_url):
    """A background worker that simulates an external payment service."""
    time.sleep(random.randint(4, 8))
    payment_successful = random.choice([True, False, True]) # Skewed towards success

    if payment_successful:
        # Now we use the URL that was passed in as an argument
        sse_manager.publish(channel_id, {
            'status': 'SUCCESS',
            'message': 'Payment confirmed!',
            'redirect_url': success_redirect_url
        })
    else:
        sse_manager.publish(channel_id, {
            'status': 'FAILED',
            'message': 'Payment failed. Please check your phone and try again.'
        })
    
    time.sleep(2)
    sse_manager.unsubscribe(channel_id)


@main_bp.route('/checkout/<slug>')
def checkout(slug):
    asset = next((a for a in mock_assets if a['slug'] == slug), None)
    if not asset:
        flash(translate('asset_not_found'), 'danger')
        return redirect(url_for('main.landing_page'))
    
    channel_id = str(uuid.uuid4())
    return render_template('user/checkout.html', asset=asset, channel_id=channel_id)

@main_bp.route('/api/initiate-payment', methods=['POST'])
def initiate_payment():
    """API endpoint that starts the asynchronous payment process."""
    data = request.get_json()
    phone_number = data.get('phone_number')
    asset_id = data.get('asset_id')
    channel_id = data.get('channel_id')

    if not all([phone_number, asset_id, channel_id]):
        return jsonify({'success': False, 'message': 'Missing required data.'}), 400

    # Generate the success URL here, while we have the app context
    success_url = url_for('main.library', _external=True)

    # Pass the generated URL as an argument to the worker
    worker_thread = threading.Thread(
        target=mock_payment_worker,
        args=(channel_id, phone_number, success_url)
    )
    worker_thread.start()

    return jsonify({
        'success': True,
        'message': 'Payment initiated. Please check your phone to authorize the transaction.',
        'channel_id': channel_id
    })

@main_bp.route('/api/payment-stream/<channel_id>')
def payment_stream(channel_id):
    """SSE endpoint for a client to listen for their specific payment result."""
    def event_stream():
        q = sse_manager.subscribe(channel_id)
        try:
            message = q.get(timeout=60)
            yield message
        except queue.Empty:
            yield f'data: {json.dumps({"status": "TIMEOUT", "message": "Payment request timed out."})}\n\n'
        finally:
            sse_manager.unsubscribe(channel_id)
            
    response = Response(event_stream(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response
    
@main_bp.route('/api/payment-success-session', methods=['POST'])
def set_payment_success_session():
    """API endpoint to securely set the session after a successful payment event."""
    data = request.get_json()
    phone_number = data.get('phone_number')
    if phone_number:
        session['current_customer_phone'] = phone_number
        return jsonify({'success': True})
    return jsonify({'success': False}), 400


# ==============================================================================
# == ADMIN BLUEPRINT (The Creator Hub)
# ==============================================================================

@admin_bp.route('/')
def index():
    if 'creator_id' in session:
        return redirect(url_for('admin.dashboard'))
    return redirect(url_for('admin.login'))

@admin_bp.route('/setup', methods=['GET', 'POST'])
def setup():
    if Creator.query.first():
        return redirect(url_for('admin.login'))

    if request.method == 'POST':
        username = request.form.get('username')
        if not username:
            flash(translate('username_required'), 'danger')
            return render_template('admin/setup.html', setup_complete=False)

        totp_secret = generate_totp_secret()
        new_creator = Creator(username=username, totp_secret=totp_secret)
        db.session.add(new_creator)
        db.session.commit()

        totp_uri = get_totp_uri(username, totp_secret)
        img = qrcode.make(totp_uri)
        buf = io.BytesIO()
        img.save(buf)
        buf.seek(0)
        qr_code_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        flash(translate('creator_account_created'), 'success')
        return render_template('admin/setup.html', setup_complete=True, qr_code=qr_code_b64, username=username)

    return render_template('admin/setup.html', setup_complete=False)

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if not Creator.query.first():
        flash(translate('setup_required'), 'info')
        return redirect(url_for('admin.setup'))
    if 'creator_id' in session:
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        creator = Creator.query.filter_by(username=request.form.get('username')).first()
        if creator:
            session['2fa_creator_id'] = creator.id
            return redirect(url_for('admin.login_verify'))
        else:
            flash(translate('invalid_username'), 'danger')

    return render_template('admin/login.html')

@admin_bp.route('/login/verify', methods=['GET', 'POST'])
def login_verify():
    if '2fa_creator_id' not in session:
        return redirect(url_for('admin.login'))
    
    if request.method == 'POST':
        creator = Creator.query.get(session['2fa_creator_id'])
        if verify_totp(creator.totp_secret, request.form.get('token')):
            session.pop('2fa_creator_id', None)
            session['creator_id'] = creator.id
            flash(translate('login_successful'), 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash(translate('invalid_2fa_token'), 'danger')
            
    return render_template('admin/login_verify.html')

@admin_bp.route('/logout')
def logout():
    session.clear()
    flash(translate('logged_out'), 'info')
    return redirect(url_for('admin.login'))

@admin_bp.route('/dashboard')
@creator_login_required
def dashboard():
    return render_template('admin/dashboard.html')

@admin_bp.route('/settings', methods=['GET', 'POST'])
@creator_login_required
def settings():
    if request.method == 'POST':
        flash(translate('settings_saved'), 'success')
        return redirect(url_for('admin.settings'))
    
    mock_settings = {'store_name': "Amina's Digital Creations", 'default_currency': 'TZS'}
    return render_template('admin/settings.html', settings=mock_settings)