# routes.py

import json
import os
import decimal
import qrcode
import io
import base64
from datetime import datetime, date
from werkzeug.utils import secure_filename
from sqlalchemy import func

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, session, g,
    jsonify, current_app
)

from models.nyota import (
    db, Creator, DigitalAsset, AssetStatus, AssetType, AssetFile, 
    SubscriptionInterval, CreatorSetting, Customer, Purchase
)

from utils.security import creator_login_required, generate_totp_secret, get_totp_uri, verify_totp
from utils.translator import translate

# --- Helper for JSON serialization ---
def json_serial(obj):
    """JSON serializer for objects not serializable by default json code."""
    if isinstance(obj, (datetime, date)): return obj.isoformat()
    if isinstance(obj, decimal.Decimal): return float(obj)
    if hasattr(obj, 'value'): return obj.value
    raise TypeError(f"Type {type(obj)} not serializable")

# --- Blueprint Definitions ---
main_bp = Blueprint('main', __name__)
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# ==============================================================================
# == ADMIN BLUEPRINT (The Creator Hub)
# ==============================================================================

@admin_bp.before_request
def before_admin_request():
    """
    Smart request hook to handle all admin authentication and setup logic.
    This runs before any route in the admin blueprint.
    """
    public_endpoints = ['admin.creator_setup', 'admin.login', 'admin.login_verify']
    
    # State 1: No creator exists in the database.
    if not Creator.query.first():
        # If the user is trying to access anything other than the setup page, force them to it.
        if request.endpoint not in ['admin.creator_setup']:
            return redirect(url_for('admin.creator_setup'))
    # State 2: A creator exists, but the user is not logged in.
    elif 'creator_id' not in session:
        # If they are trying to access a protected page, force them to the login page.
        if request.endpoint not in public_endpoints:
            return redirect(url_for('admin.login'))
    # State 3: User is logged in.
    else:
        # Load the creator object into the global context for use in templates and routes.
        g.creator = Creator.query.get(session['creator_id'])
        if not g.creator:
            # Failsafe: If session contains an invalid ID, clear it and force login.
            session.clear()
            return redirect(url_for('admin.login'))

# --- AUTH & SETUP ROUTES ---

@admin_bp.route('/')
def admin_home():
    """
    Primary entry point for `/admin`. Redirects user based on their state.
    """
    if 'creator_id' in session:
        return redirect(url_for('admin.creator_dashboard'))
    elif Creator.query.first():
        return redirect(url_for('admin.login'))
    else:
        return redirect(url_for('admin.creator_setup'))

@admin_bp.route('/setup', methods=['GET', 'POST'])
def creator_setup():
    """Handles the initial, one-time setup of the first creator account."""
    if Creator.query.first():
        return redirect(url_for('admin.login'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create_user':
            username = request.form.get('username')
            if not username or len(username) < 3:
                flash(translate('username_required'), 'danger')
                return render_template('admin/setup.html', stage=1)
            
            totp_secret = generate_totp_secret()
            session['setup_info'] = {'username': username, 'totp_secret': totp_secret}
            totp_uri = get_totp_uri(username, totp_secret)
            img = qrcode.make(totp_uri)
            buf = io.BytesIO()
            img.save(buf)
            qr_code_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            
            flash(translate('scan_qr_and_verify'), 'info')
            return render_template('admin/setup.html', stage=2, qr_code=qr_code_b64, username=username)

        elif action == 'verify_totp':
            setup_info = session.get('setup_info')
            token = request.form.get('token')
            if not setup_info or not token:
                flash(translate('session_expired_setup'), 'danger')
                return redirect(url_for('admin.creator_setup'))
            
            if verify_totp(setup_info['totp_secret'], token):
                new_creator = Creator(username=setup_info['username'], totp_secret=setup_info['totp_secret'])
                db.session.add(new_creator)
                db.session.commit()
                
                session.pop('setup_info', None)
                flash(translate('setup_complete_success'), 'success')
                return redirect(url_for('admin.login'))
            else:
                flash(translate('invalid_2fa_token'), 'danger')
                totp_uri = get_totp_uri(setup_info['username'], setup_info['totp_secret'])
                img = qrcode.make(totp_uri)
                buf = io.BytesIO()
                img.save(buf)
                qr_code_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                return render_template('admin/setup.html', stage=2, qr_code=qr_code_b64, username=setup_info['username'])

    return render_template('admin/setup.html', stage=1)

@admin_bp.route('/login', methods=['GET', 'POST'])
def creator_login():
    if not Creator.query.first():
        return redirect(url_for('admin.creator_setup'))
    if 'creator_id' in session:
        return redirect(url_for('admin.creator_dashboard'))

    if request.method == 'POST':
        creator = Creator.query.filter_by(username=request.form.get('username')).first()
        if creator:
            session['2fa_creator_id'] = creator.id
            return redirect(url_for('admin.login_verify'))
        else:
            flash(translate('invalid_username'), 'danger')
    return render_template('admin/login.html')

@admin_bp.route('/login/verify', methods=['GET', 'POST'])
def creator_login_verify():
    if '2fa_creator_id' not in session:
        return redirect(url_for('admin.login'))
    
    if request.method == 'POST':
        creator = Creator.query.get(session['2fa_creator_id'])
        if verify_totp(creator.totp_secret, request.form.get('token')):
            session.pop('2fa_creator_id', None)
            session['creator_id'] = creator.id
            flash(translate('login_successful'), 'success')
            return redirect(url_for('admin.creator_dashboard'))
        else:
            flash(translate('invalid_2fa_token'), 'danger')
    return render_template('admin/login_verify.html')

@admin_bp.route('/logout')
def creator_logout():
    session.clear()
    flash(translate('logged_out'), 'info')
    return redirect(url_for('admin.login'))

# --- CORE ADMIN ROUTES (Protected by the `before_request` hook) ---

@admin_bp.route('/dashboard')
@creator_login_required
def creator_dashboard():
    """Renders the main creator dashboard with real, calculated stats."""
    
    # --- Existing Correct Calculations ---
    total_earnings = db.session.query(func.sum(DigitalAsset.total_revenue)).filter(DigitalAsset.creator_id == g.creator.id).scalar() or 0.0
    total_sales = db.session.query(func.sum(DigitalAsset.total_sales)).filter(DigitalAsset.creator_id == g.creator.id).scalar() or 0
    total_assets = DigitalAsset.query.filter(DigitalAsset.creator_id == g.creator.id).count()
    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
    new_supporters = Customer.query.join(Purchase).join(DigitalAsset).filter(
        DigitalAsset.creator_id == g.creator.id,
        Customer.created_at >= start_of_month
    ).count()

    # Calculate earnings for the current month ===
    earnings_this_month = db.session.query(func.sum(Purchase.amount_paid)).join(DigitalAsset).filter(
        DigitalAsset.creator_id == g.creator.id,
        Purchase.purchase_date >= start_of_month
    ).scalar() or 0.0

    # Assemble the stats dictionary that the template expects.
    stats = {
        'total_earnings': total_earnings,
        'total_sales': total_sales,
        'total_assets': total_assets,
        'new_supporters': new_supporters,
        'earnings_this_month': earnings_this_month  # <-- Add the new value to the dictionary
    }
    
    # TODO: Fetch recent activity (e.g., last 5 purchases)
    activity = []
    
    return render_template('admin/dashboard.html', stats=stats, activity=activity)


# ==============================================================================
# == MAIN (PUBLIC) BLUEPRINT
# ==============================================================================

@main_bp.route('/')
def landing_page():
    """Renders the main creator storefront with live data."""
    creator = Creator.query.first()
    if not creator:
        return "<h1>Store not set up yet.</h1>", 503

    published_assets = DigitalAsset.query.filter_by(status=AssetStatus.PUBLISHED, creator_id=creator.id).all()
    assets_data = [a.to_dict() for a in published_assets]
    return render_template(
        'user/index.html', 
        assets=json.dumps(assets_data, default=json_serial),
        store_name=creator.store_name,
        store_bio=creator.get_setting('store_bio', 'Welcome to my store!')
    )

@main_bp.route('/asset/<slug>')
def asset_detail(slug):
    """Displays the detailed page for a single digital asset."""
    asset = DigitalAsset.query.filter_by(slug=slug, status=AssetStatus.PUBLISHED).first_or_404()
    asset_data = asset.to_dict()
    return render_template('user/asset_detail.html', asset=json.dumps(asset_data, default=json_serial))

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
        action = request.form.get('action')

        # Action 1: Create the user and show the QR code
        if action == 'create_user':
            username = request.form.get('username')
            if not username:
                flash(translate('username_required'), 'danger')
                return render_template('admin/setup.html', stage=1)

            totp_secret = generate_totp_secret()
            
            # Store temporary setup info in the session
            session['setup_info'] = {
                'username': username,
                'totp_secret': totp_secret
            }

            totp_uri = get_totp_uri(username, totp_secret)
            img = qrcode.make(totp_uri)
            buf = io.BytesIO()
            img.save(buf)
            buf.seek(0)
            qr_code_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            
            flash(translate('scan_qr_and_verify'), 'info')
            return render_template('admin/setup.html', stage=2, qr_code=qr_code_b64, username=username)

        # Verify the TOTP code and finalize setup 
        elif action == 'verify_totp':
            setup_info = session.get('setup_info')
            token = request.form.get('token')
            if not setup_info or not token:
                flash(translate('session_expired_setup'), 'danger')
                session.pop('setup_info', None) # Clean up session
                return redirect(url_for('admin.setup'))
            
            # Verify the code the user entered
            if verify_totp(setup_info['totp_secret'], token):
                # On success, create the Creator record in the database
                new_creator = Creator(
                    username=setup_info['username'],
                    totp_secret=setup_info['totp_secret']
                )
                db.session.add(new_creator)
                db.session.commit()
                
                session.pop('setup_info', None) # Clean up session
                flash(translate('setup_complete_success'), 'success')
                return redirect(url_for('admin.login'))
            else:
                # If verification fails, re-render the verification page with an error
                flash(translate('invalid_2fa_token'), 'danger')
                # We need to regenerate the QR code to show it again
                totp_uri = get_totp_uri(setup_info['username'], setup_info['totp_secret'])
                img = qrcode.make(totp_uri)
                buf = io.BytesIO()
                img.save(buf)
                buf.seek(0)
                qr_code_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                return render_template('admin/setup.html', stage=2, qr_code=qr_code_b64, username=setup_info['username'])

    # Default GET request shows the first stage
    return render_template('admin/setup.html', stage=1)

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
    """The main dashboard showing key metrics and recent activity."""
    return render_template(
        'admin/dashboard.html',
        stats=dashboard_stats,
        activity=recent_activity
    )

@admin_bp.route('/assets')
@creator_login_required
def list_assets():
    """Renders the main list of all digital assets from the database."""
    
    # 1. Fetch all assets belonging to the currently logged-in creator.
    creator_assets = DigitalAsset.query.filter_by(creator_id=g.creator.id).order_by(DigitalAsset.updated_at.desc()).all()
    
    # 2. Serialize the asset data into a list of dictionaries for the frontend.
    assets_data = [
        {
            'id': asset.id, 'title': asset.title, 'description': asset.description,
            'cover': asset.cover_image_url, 'type': asset.asset_type.name,
            'status': asset.status.value, 'sales': asset.total_sales,
            'revenue': float(asset.total_revenue), 'updated_at': asset.updated_at
        } for asset in creator_assets
    ]
    
    # 3. Pass the data as a JSON string to the template.
    return render_template(
        'admin/assets.html', 
        assets=json.dumps(assets_data, default=json_serial)
    )

@admin_bp.route('/assets/new', methods=['GET', 'POST'])
@creator_login_required
def asset_new():
    if request.method == 'POST':
        # ... logic for creating a new asset ...
        flash("Asset created successfully!", "success")
        return redirect(url_for('admin.list_assets'))
    # Pass an empty dictionary for the form template
    return render_template('admin/asset_form.html', asset={})

@admin_bp.route('/assets/<int:asset_id>/edit', methods=['GET', 'POST'])
@creator_login_required
def asset_edit(asset_id):
    asset = DigitalAsset.query.filter_by(id=asset_id, creator_id=g.creator.id).first_or_404()
    if request.method == 'POST':
        # ... logic for updating the asset ...
        flash(f"Asset '{asset.title}' updated successfully!", "success")
        return redirect(url_for('admin.list_assets'))
    
    # Pass the real asset data to the edit form
    return render_template('admin/asset_form.html', asset=asset.to_dict())


@admin_bp.route('/assets/<int:asset_id>/edit', methods=['GET', 'POST'])
@creator_login_required
def edit_asset(asset_id):
    """Handles both displaying and processing the editing of an existing asset."""

    # 1. Fetch the specific asset, ensuring it belongs to the logged-in creator.
    asset = DigitalAsset.query.filter_by(id=asset_id, creator_id=g.creator.id).first_or_404()

    if request.method == 'POST':
        # TODO: Implement the logic to save changes from the edit form.
        flash(f"Asset '{asset.title}' updated successfully!", "success")
        return redirect(url_for('admin.list_assets'))

    # 2. Fetch recent supporters for this specific asset.
    recent_supporters = Customer.query.join(Purchase).filter(
        Purchase.asset_id == asset.id
    ).order_by(Purchase.purchase_date.desc()).limit(5).all()

    # 3. Pass the real asset data and supporters to the template.
    # We use to_dict() to ensure it's in a format the frontend can easily use.
    return render_template(
        'admin/asset_view.html', # Assuming asset_view.html is the simple edit form
        asset=asset.to_dict(), 
        recent_supporters=recent_supporters
    )

@admin_bp.route('/supporters')
@creator_login_required
def supporters():
    """Page for the creator to manage their supporters and affiliates."""
    return render_template('admin/supporters.html', supporters=mock_supporters)

@admin_bp.route('/settings', methods=['GET', 'POST'])
@creator_login_required
def settings():
    if request.method == 'POST':
        flash(translate('settings_saved'), 'success')
        return redirect(url_for('admin.settings'))
    
    mock_settings = {'store_name': "Amina's Digital Creations", 'default_currency': 'TZS'}
    return render_template('admin/settings.html', settings=mock_settings)