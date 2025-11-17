# routes.py

import json
import os
import decimal
import qrcode
import io
import base64
import time
import uuid
import queue
import threading
from datetime import datetime, date
from werkzeug.utils import secure_filename
from sqlalchemy import func

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, session, g,
    jsonify, current_app, Response
)

from models.nyota import (
    db, Creator, DigitalAsset, AssetStatus, AssetType, AssetFile, 
    SubscriptionInterval, CreatorSetting, Customer, Purchase, Comment, PurchaseStatus
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
    """Smart request hook to handle all admin authentication and setup logic."""
    public_endpoints = ['admin.creator_setup', 'admin.creator_login', 'admin.creator_login_verify']
    
    if not Creator.query.first():
        if request.endpoint not in ['admin.creator_setup']:
            return redirect(url_for('admin.creator_setup'))
    elif 'creator_id' not in session and request.endpoint not in public_endpoints:
        return redirect(url_for('admin.creator_login'))
    elif 'creator_id' in session:
        g.creator = Creator.query.get(session['creator_id'])
        if not g.creator:
            session.clear()
            return redirect(url_for('admin.creator_login'))

# --- AUTH & SETUP ROUTES ---

@admin_bp.route('/')
def admin_home():
    """Primary entry point for `/admin`. Redirects user based on their state."""
    if 'creator_id' in session:
        return redirect(url_for('admin.creator_dashboard'))
    elif Creator.query.first():
        return redirect(url_for('admin.creator_login'))
    else:
        return redirect(url_for('admin.creator_setup'))

@admin_bp.route('/setup', methods=['GET', 'POST'])
def creator_setup():
    if Creator.query.first(): return redirect(url_for('admin.creator_login'))
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create_user':
            username = request.form.get('username')
            if not username or len(username) < 3:
                flash(translate('username_required'), 'danger')
                return render_template('admin/setup.html', stage=1)
            
            totp_secret = generate_totp_secret()
            session['setup_info'] = {'username': username, 'totp_secret': totp_secret}
            totp_uri = get_totp_uri(username, session['setup_info']['totp_secret'])
            img = qrcode.make(totp_uri)
            buf = io.BytesIO()
            img.save(buf)
            qr_code_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            return render_template('admin/setup.html', stage=2, qr_code=qr_code_b64, username=username)

        elif action == 'verify_totp':
            setup_info, token = session.get('setup_info'), request.form.get('token')
            if not setup_info or not token:
                flash(translate('session_expired_setup'), 'danger')
                return redirect(url_for('admin.creator_setup'))
            
            if verify_totp(setup_info['totp_secret'], token):
                new_creator = Creator(username=setup_info['username'], totp_secret=setup_info['totp_secret'])
                db.session.add(new_creator)
                db.session.commit()
                session.pop('setup_info', None)
                flash(translate('setup_complete_success'), 'success')
                return redirect(url_for('admin.creator_login'))
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
    if not Creator.query.first(): return redirect(url_for('admin.creator_setup'))
    if 'creator_id' in session: return redirect(url_for('admin.creator_dashboard'))
    if request.method == 'POST':
        creator = Creator.query.filter_by(username=request.form.get('username')).first()
        if creator:
            session['2fa_creator_id'] = creator.id
            return redirect(url_for('admin.creator_login_verify'))
        flash(translate('invalid_username'), 'danger')
    return render_template('admin/login.html')

@admin_bp.route('/login/verify', methods=['GET', 'POST'])
def creator_login_verify():
    if '2fa_creator_id' not in session: return redirect(url_for('admin.creator_login'))
    if request.method == 'POST':
        creator = Creator.query.get(session['2fa_creator_id'])
        if verify_totp(creator.totp_secret, request.form.get('token')):
            session.pop('2fa_creator_id', None)
            session['creator_id'] = creator.id
            return redirect(url_for('admin.creator_dashboard'))
        flash(translate('invalid_2fa_token'), 'danger')
    return render_template('admin/login_verify.html')

@admin_bp.route('/logout')
def creator_logout():
    session.clear()
    flash(translate('logged_out'), 'info')
    return redirect(url_for('admin.creator_login'))

# --- CORE ADMIN ROUTES (Protected) ---

@admin_bp.route('/dashboard')
@creator_login_required
def creator_dashboard():
    # --- STATS CALCULATION ---
    # Total earnings from completed purchases
    total_earnings = db.session.query(func.sum(Purchase.amount_paid)).join(DigitalAsset).filter(
        DigitalAsset.creator_id == g.creator.id,
        Purchase.status == PurchaseStatus.COMPLETED
    ).scalar() or decimal.Decimal(0)

    # Total number of completed sales
    total_sales = Purchase.query.join(DigitalAsset).filter(
        DigitalAsset.creator_id == g.creator.id,
        Purchase.status == PurchaseStatus.COMPLETED
    ).count()

    # Total unique customers who have completed a purchase
    supporters_count = db.session.query(func.count(Customer.id.distinct())).join(Purchase).join(DigitalAsset).filter(
        DigitalAsset.creator_id == g.creator.id,
        Purchase.status == PurchaseStatus.COMPLETED
    ).scalar() or 0

    # Earnings this month
    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
    earnings_this_month = db.session.query(func.sum(Purchase.amount_paid)).join(DigitalAsset).filter(
        DigitalAsset.creator_id == g.creator.id,
        Purchase.status == PurchaseStatus.COMPLETED,
        Purchase.purchase_date >= start_of_month
    ).scalar() or decimal.Decimal(0)

    # New supporters this month
    new_supporters_this_month = db.session.query(func.count(Customer.id.distinct())).join(Purchase).join(DigitalAsset).filter(
        DigitalAsset.creator_id == g.creator.id,
        Purchase.status == PurchaseStatus.COMPLETED,
        Customer.created_at >= start_of_month
    ).scalar() or 0

    stats = {
        'total_earnings': total_earnings,
        'total_sales': total_sales,
        'supporters_count': supporters_count,
        'earnings_this_month': earnings_this_month,
        'new_supporters_this_month': new_supporters_this_month
    }
    
    # --- RECENT ACTIVITY (SALES) ---
    # Fetch the 10 most recent purchases (completed or pending)
    recent_activity = Purchase.query.join(DigitalAsset).filter(
        DigitalAsset.creator_id == g.creator.id
    ).order_by(Purchase.purchase_date.desc()).limit(10).all()

    return render_template(
        'admin/dashboard.html', 
        stats=stats, 
        activity=recent_activity,
        currency_symbol=g.creator.get_setting('currency_symbol', '$')
    )

@admin_bp.route('/assets')
@creator_login_required
def list_assets():
    creator_assets = DigitalAsset.query.filter_by(creator_id=g.creator.id).order_by(DigitalAsset.updated_at.desc()).all()
    assets_data = [{'id': a.id, 'title': a.title, 'description': a.description, 'cover': a.cover_image_url, 'type': a.asset_type.name, 'status': a.status.value, 'sales': a.total_sales, 'revenue': float(a.total_revenue), 'updated_at': a.updated_at} for a in creator_assets]
    return render_template('admin/assets.html', assets=json.dumps(assets_data, default=json_serial), currency_symbol=g.creator.get_setting('currency_symbol', '$'))

@admin_bp.route('/assets/new', methods=['GET', 'POST'])
@creator_login_required
def asset_new():
    if request.method == 'POST':
        try:
            new_asset = DigitalAsset(creator_id=g.creator.id)
            save_asset_from_form(new_asset, request)
            db.session.add(new_asset)
            db.session.commit()
            flash(f"Asset '{new_asset.title}' created successfully!", "success")
            return redirect(url_for('admin.list_assets'))
        except ValueError as e:
            flash(str(e), 'danger')
            return render_template('admin/asset_form.html', asset=request.form.get('asset_data', '{}'))
    return render_template('admin/asset_form.html', asset='{}')

@admin_bp.route('/assets/<int:asset_id>/edit', methods=['GET'])
@creator_login_required
def asset_edit(asset_id):
    asset = DigitalAsset.query.filter_by(id=asset_id, creator_id=g.creator.id).first_or_404()
    recent_purchases = Purchase.query.filter_by(asset_id=asset.id).order_by(Purchase.purchase_date.desc()).limit(5).all()
    recent_comments = Comment.query.filter_by(asset_id=asset.id).order_by(Comment.created_at.desc()).limit(5).all()
    return render_template('admin/asset_view.html', asset=asset, recent_purchases=recent_purchases, recent_comments=recent_comments, currency_symbol=g.creator.get_setting('currency_symbol', '$'), statuses=[s.value for s in AssetStatus])

@admin_bp.route('/api/assets/<int:asset_id>/update', methods=['POST'])
@creator_login_required
def update_asset_details(asset_id):
    """API endpoint to handle edits from the asset_view page."""
    asset = DigitalAsset.query.filter_by(id=asset_id, creator_id=g.creator.id).first_or_404()
    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'message': 'Invalid request.'}), 400

    title = data.get('title', '').strip()
    if not title:
        return jsonify({'success': False, 'message': 'Asset title cannot be empty.'}), 422

    try:
        asset.title = title
        asset.description = data.get('description', asset.description)
        asset.story = data.get('story', asset.story)
        asset.price = decimal.Decimal(data.get('price', asset.price))
        
        new_status_str = data.get('status')
        if new_status_str in [s.value for s in AssetStatus]:
            asset.status = AssetStatus(new_status_str)
        
        # Update type-specific fields
        if asset.asset_type == AssetType.TICKET:
            event_details = data.get('eventDetails', {})
            asset.event_location = event_details.get('link')
            if event_details.get('date') and event_details.get('time'):
                asset.event_date = datetime.strptime(f"{event_details['date']} {event_details['time']}", '%Y-%m-%d %H:%M')
            asset.max_attendees = int(event_details.get('maxAttendees')) if event_details.get('maxAttendees') else None
        elif asset.asset_type in [AssetType.SUBSCRIPTION, AssetType.NEWSLETTER]:
            asset.details = data.get('details', asset.details)

        db.session.commit()
        return jsonify({'success': True, 'message': f"'{asset.title}' updated successfully."})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating asset {asset_id} via API: {e}")
        return jsonify({'success': False, 'message': 'A server error occurred while saving.'}), 500

    # --- RENDER THE VIEW/EDIT PAGE (GET request) ---
    
    # Fetch recent purchases for this asset
    recent_purchases = Purchase.query.filter_by(asset_id=asset.id).order_by(Purchase.purchase_date.desc()).limit(5).all()
    
    # Fetch recent comments for this asset
    recent_comments = Comment.query.filter_by(asset_id=asset.id).order_by(Comment.created_at.desc()).limit(5).all()

    return render_template(
        'admin/asset_view.html',
        asset=asset,
        recent_purchases=recent_purchases,
        recent_comments=recent_comments,
        currency_symbol=g.creator.get_setting('currency_symbol', '$'),
        statuses=[s.value for s in AssetStatus]
    )

def save_asset_from_form(asset, req):
    if 'asset_data' not in req.form: raise ValueError("Form submission incomplete. Please try again.")
    form_data = json.loads(req.form['asset_data'])
    asset_details = form_data.get('asset', {})
    title = asset_details.get('title')
    asset_type_enum_str = form_data.get('assetTypeEnum')
    if not asset_type_enum_str: raise ValueError("No asset type selected. Please go back to Step 1.")
    if not title or not title.strip(): raise ValueError("A Title is required. Please enter a title in Step 2.")
    
    asset.asset_type = AssetType[asset_type_enum_str]
    asset.title, asset.description, asset.story = title, asset_details.get('description'), asset_details.get('story_snippet')

    if 'cover_image' in req.files:
        file = req.files['cover_image']
        if file and file.filename:
            filename = f"{asset.id or 'new'}_{int(datetime.now().timestamp())}_{secure_filename(file.filename)}"
            upload_path = os.path.join(current_app.root_path, 'static/uploads/covers')
            os.makedirs(upload_path, exist_ok=True)
            file.save(os.path.join(upload_path, filename))
            asset.cover_image_url = f'/static/uploads/covers/{filename}'

    pricing_data = form_data.get('pricing', {})
    asset.price = decimal.Decimal(pricing_data.get('amount') or 0.0)
    asset.is_subscription = pricing_data.get('type') == 'recurring'
    asset.subscription_interval = SubscriptionInterval[pricing_data.get('billingCycle', 'monthly').upper()] if asset.is_subscription else None
    
    asset.details = asset.details or {}
    if asset.asset_type == AssetType.TICKET:
        event_details = form_data.get('eventDetails', {})
        asset.event_location, asset.custom_fields = event_details.get('link'), form_data.get('customFields', [])
        if event_details.get('date') and event_details.get('time'):
            try: asset.event_date = datetime.strptime(f"{event_details['date']} {event_details['time']}", '%Y-%m-%d %H:%M')
            except (ValueError, TypeError): asset.event_date = None
        asset.max_attendees = int(event_details.get('maxAttendees')) if event_details.get('maxAttendees') else None
    elif asset.asset_type == AssetType.SUBSCRIPTION: asset.details = form_data.get('subscriptionDetails', {})
    elif asset.asset_type == AssetType.NEWSLETTER: asset.details = form_data.get('newsletterDetails', {})
    
    AssetFile.query.filter_by(asset_id=asset.id).delete()
    for i, item in enumerate(form_data.get('contentItems', [])):
        db.session.add(AssetFile(asset=asset, title=item.get('title'), description=item.get('description'), storage_path=item.get('link'), order_index=i))

    asset.status = AssetStatus.DRAFT if form_data.get('action') == 'draft' else AssetStatus.PUBLISHED
    return asset

# --- API ENDPOINTS FOR ASSET ACTIONS ---
@admin_bp.route('/api/assets/bulk-action', methods=['POST'])
@creator_login_required
def assets_bulk_action():
    data = request.get_json()
    asset_ids, action = data.get('ids'), data.get('action')
    if not asset_ids or not action: return jsonify({'success': False, 'message': 'Missing data.'}), 400
    query = DigitalAsset.query.filter(DigitalAsset.id.in_(asset_ids), DigitalAsset.creator_id == g.creator.id)
    if query.count() != len(asset_ids): return jsonify({'success': False, 'message': 'Authorization error or some assets not found.'}), 403
    try:
        if action == 'publish': query.update({'status': AssetStatus.PUBLISHED}); msg = f"{len(asset_ids)} asset(s) published."
        elif action == 'draft': query.update({'status': AssetStatus.DRAFT}); msg = f"{len(asset_ids)} asset(s) moved to drafts."
        elif action == 'archive': query.update({'status': AssetStatus.ARCHIVED}); msg = f"{len(asset_ids)} asset(s) archived."
        elif action == 'delete': query.delete(synchronize_session=False); msg = f"{len(asset_ids)} asset(s) permanently deleted."
        else: return jsonify({'success': False, 'message': 'Invalid action.'}), 400
        db.session.commit()
        return jsonify({'success': True, 'message': msg})
    except Exception as e:
        db.session.rollback(); current_app.logger.error(f"Bulk action error: {e}"); return jsonify({'success': False, 'message': 'A server error occurred.'}), 500

@admin_bp.route('/api/assets/<int:asset_id>/duplicate', methods=['POST'])
@creator_login_required
def duplicate_asset(asset_id):
    original = DigitalAsset.query.filter_by(id=asset_id, creator_id=g.creator.id).first_or_404()
    try:
        db.session.add(DigitalAsset(creator_id=g.creator.id, title=f"Copy of {original.title}", status=AssetStatus.DRAFT, description=original.description, story=original.story, cover_image_url=original.cover_image_url, asset_type=original.asset_type, price=original.price, is_subscription=original.is_subscription, subscription_interval=original.subscription_interval, event_date=original.event_date, event_location=original.event_location, max_attendees=original.max_attendees, custom_fields=original.custom_fields, details=original.details))
        db.session.commit()
        return jsonify({'success': True, 'message': f"'{original.title}' was duplicated successfully."})
    except Exception as e:
        db.session.rollback(); current_app.logger.error(f"Duplication error: {e}"); return jsonify({'success': False, 'message': 'A server error occurred.'}), 500

@admin_bp.route('/supporters')
@creator_login_required
def supporters():
    """Fetches all customers and their aggregated data for the admin supporters page."""
    
    # --- THIS IS THE NEW, CORRECTED QUERY ---
    
    # 1. Find the IDs of all unique customers who have made a purchase from this creator.
    #    This is a very efficient and direct way to identify supporters.
    supporter_ids_query = db.session.query(Customer.id).distinct().join(Purchase).join(DigitalAsset).filter(
        DigitalAsset.creator_id == g.creator.id
    )
    supporter_ids = [item[0] for item in supporter_ids_query.all()]

    # 2. If there are any supporters, fetch their full objects with all relationships pre-loaded.
    #    This avoids the complex join issues and is the recommended pattern.
    if supporter_ids:
        all_customers = db.session.query(Customer).filter(
            Customer.id.in_(supporter_ids)
        ).options(
            db.selectinload(Customer.purchases),
            db.selectinload(Customer.subscriptions),
            db.selectinload(Customer.ambassador_profile)
        ).all()
    else:
        all_customers = []

    # 3. Serialize each customer. This part remains the same.
    supporters_data = [customer.to_dict_detailed() for customer in all_customers]

    return render_template(
        'admin/supporters.html', 
        supporters=json.dumps(supporters_data, default=json_serial),
        currency_symbol=g.creator.get_setting('currency_symbol', '$')
    )

@admin_bp.route('/settings', methods=['GET', 'POST'])
@creator_login_required
def manage_settings():
    """
    Handles both displaying and saving all creator settings using the
    scalable CreatorSetting key-value model.
    """
    if request.method == 'POST':
        # --- SAVE SETTINGS LOGIC ---
        
        # Core Creator fields that are not in the key-value store
        g.creator.store_name = request.form.get('store_name', g.creator.store_name)
        g.creator.store_handle = request.form.get('store_handle', g.creator.store_handle)
        
        # A definitive list of all possible setting keys from the template
        setting_keys = [
            'store_logo_url', 'store_bio', 'social_twitter', 'social_instagram', 'contact_email', 
            'contact_phone', 'appearance_storefront_theme', 'telegram_enabled', 'telegram_bot_token', 
            'telegram_chat_id', 'telegram_notify_payments', 'telegram_notify_ratings', 
            'telegram_notify_comments', 'whatsapp_enabled', 'whatsapp_phone_id', 'whatsapp_access_token',
            'sms_provider', 'sms_twilio_sid', 'sms_twilio_token', 'sms_twilio_phone', 'sms_beem_api_key',
            'sms_beem_secret_key', 'sms_beem_sender_name', 'payment_stripe_enabled', 'payment_paypal_enabled',
            'ai_enabled', 'ai_provider', 'ai_api_key', 'ai_model', 'ai_temperature',
            'ai_feature_content_suggestions', 'ai_feature_seo_optimization', 'ai_feature_email_templates',
            'ai_feature_smart_analytics', 'social_instagram_connected', 'social_instagram_ai_enabled',
            'social_instagram_keywords', 'social_instagram_response_delay', 'social_instagram_ai_personality',
            'productivity_google_connected', 'productivity_google_calendar_id', 'productivity_google_sync_events',
            'productivity_google_send_reminders', 'productivity_google_check_conflicts', 'email_smtp_enabled',
            'email_smtp_host', 'email_smtp_port', 'email_smtp_user', 'email_smtp_pass', 'email_smtp_encryption',
            'email_smtp_sender_email', 'email_smtp_sender_name'
        ]

        # Iterate and save each setting
        for key in setting_keys:
            # Handle checkboxes, which are only present in form data if checked
            if 'enabled' in key or 'connected' in key or key.startswith('telegram_notify_') or key.startswith('productivity_google_'):
                value = True if request.form.get(key) else False
            else:
                value = request.form.get(key)
            
            g.creator.set_setting(key, value)
        
        # Handle file upload for store logo
        if 'store_logo' in request.files:
            file = request.files['store_logo']
            if file and file.filename:
                filename = f"logo_{g.creator.id}_{secure_filename(file.filename)}"
                upload_path = os.path.join(current_app.root_path, 'static/uploads/logos')
                os.makedirs(upload_path, exist_ok=True)
                file.save(os.path.join(upload_path, filename))
                g.creator.set_setting('store_logo_url', f'/static/uploads/logos/{filename}')

        db.session.commit()
        flash("Settings saved successfully!", "success")
        return redirect(url_for('admin.manage_settings'))

    all_settings = CreatorSetting.query.filter_by(creator_id=g.creator.id).all()
    settings_dict = {setting.key: setting.value for setting in all_settings}
    
    # Add core creator fields to the dictionary for a unified object
    settings_dict['store_name'] = g.creator.store_name
    settings_dict['store_handle'] = g.creator.store_handle

    # Convert the final dictionary to a JSON string for the data island
    settings_json = json.dumps(settings_dict, default=json_serial)

    return render_template('admin/settings.html', settings_json=settings_json)

# ==============================================================================
# == MAIN (PUBLIC) BLUEPRINT
# ==============================================================================
# NOTE: This section uses mock data and will need to be updated later.
# It is preserved to prevent the public-facing pages from crashing.

# Mock SSE Manager
class SseManager:
    def __init__(self):
        self.channels = {}
        self.lock = threading.Lock()

    def subscribe(self, channel_id):
        with self.lock:
            q = queue.Queue(5)
            self.channels[channel_id] = q
            return q

    def unsubscribe(self, channel_id):
        with self.lock:
            self.channels.pop(channel_id, None)

    def publish(self, channel_id, data):
        with self.lock:
            if channel_id in self.channels:
                try:
                    # Format data as a Server-Sent Event
                    message = f"data: {json.dumps(data)}\n\n"
                    self.channels[channel_id].put_nowait(message)
                except queue.Full:
                    current_app.logger.warning(f"SSE channel {channel_id} queue is full. Message dropped.")

sse_manager = SseManager()

# Mock function to simulate the UZA payment gateway call and callback
# In a real app, the UZA callback would hit a separate '/api/uza-callback' endpoint
def simulate_uza_payment(channel_id, phone, asset_id):
    # 1. Simulate API call to UZA
    time.sleep(2)  # Network latency
    current_app.logger.info(f"Pretending to call UZA API for phone {phone}...")
    
    # 2. Simulate user taking time to pay on their phone
    time.sleep(8)
    
    # 3. Simulate UZA sending a callback to our server
    current_app.logger.info(f"Simulating UZA callback for channel {channel_id}...")
    
    # Randomly decide if payment was successful or failed
    import random
    if random.random() > 0.15: # 85% success rate
        # --- THIS IS WHAT YOUR REAL UZA CALLBACK ROUTE WOULD DO ---
        # 1. Find the purchase record in your DB using a transaction ID
        # 2. Update its status to 'PAID'
        # 3. Create a customer if they don't exist
        # 4. Publish success to the SSE channel
        sse_manager.publish(channel_id, {
            'status': 'SUCCESS', 
            'message': 'Payment confirmed! Thank you.',
            'redirect_url': url_for('main.library') # In a real app, this might be a unique download link
        })
    else:
        sse_manager.publish(channel_id, {
            'status': 'FAILED',
            'message': 'The payment was declined by your provider.'
        })
    
    # Clean up the SSE channel after completion
    sse_manager.unsubscribe(channel_id)

@main_bp.route('/')
def landing_page():
    creator = Creator.query.first()
    if not creator:
        return "<h1>Store not set up yet.</h1><p>Please complete the admin setup.</p>", 503

    # Fetch all published assets
    assets = DigitalAsset.query.filter_by(
        status=AssetStatus.PUBLISHED, 
        creator_id=creator.id
    ).order_by(DigitalAsset.updated_at.desc()).all()

    # Pre-categorize assets into a dictionary
    categorized_assets = {}
    for asset in assets:
        category_enum = asset.asset_type
        if category_enum not in categorized_assets:
            categorized_assets[category_enum] = []
        categorized_assets[category_enum].append(asset)
    
    # --- THIS IS THE NEW SESSION-AWARE LOGIC ---
    user_purchases = {} # A dictionary to hold the status of each asset for the user
    customer_phone = session.get('customer_phone')
    if customer_phone:
        customer = Customer.query.filter_by(whatsapp_number=customer_phone).first()
        if customer:
            # Fetch all of this customer's purchases
            purchases = Purchase.query.filter_by(customer_id=customer.id).all()
            # Create a simple lookup map: {asset_id: status_name}
            for p in purchases:
                # Store the most "important" status (Completed > Pending > Failed)
                if p.asset_id not in user_purchases or p.status == PurchaseStatus.COMPLETED:
                    user_purchases[p.asset_id] = p.status.name
            
    return render_template(
        'user/index.html',
        creator=creator,
        store_name=creator.store_name,
        categorized_assets=categorized_assets,
        user_purchases=user_purchases, # Pass the purchase map to the template
        currency_symbol=creator.get_setting('currency_symbol', '$')
    )

@main_bp.route('/asset/<slug>')
def asset_detail(slug):
    asset_obj = DigitalAsset.query.filter_by(slug=slug, status=AssetStatus.PUBLISHED).first_or_404()
    asset_json = json.dumps(asset_obj.to_dict(), default=json_serial)
    creator = Creator.query.get(asset_obj.creator_id)

    purchase_status = None
    customer_phone = session.get('customer_phone')
    if customer_phone:
        customer = Customer.query.filter_by(whatsapp_number=customer_phone).first()
        if customer:
            # Find the most recent purchase attempt for this asset by this customer
            latest_purchase = Purchase.query.filter_by(
                customer_id=customer.id, 
                asset_id=asset_obj.id
            ).order_by(Purchase.purchase_date.desc()).first()
            
            if latest_purchase:
                purchase_status = latest_purchase.status.name # e.g., "COMPLETED", "PENDING", "FAILED"

    return render_template(
        'user/asset_detail.html',
        asset_obj=asset_obj,
        asset_json=asset_json,
        purchase_status=purchase_status, # Pass the status to the template
        store_name=creator.store_name if creator else "Creator Store",
        currency_symbol=creator.get_setting('currency_symbol', '$') if creator else '$'
    )

@main_bp.route('/checkout/<slug>')
def checkout(slug):
    asset = DigitalAsset.query.filter_by(slug=slug, status=AssetStatus.PUBLISHED).first_or_404()
    return render_template('user/checkout.html', asset=asset.to_dict(), channel_id=str(uuid.uuid4()))

@main_bp.route('/api/initiate-payment', methods=['POST'])
def initiate_payment():
    """
    Called by the frontend to start a payment.
    This endpoint creates a PENDING purchase record and simulates calling the UZA API.
    """
    data = request.get_json()
    if not all(k in data for k in ['phone_number', 'asset_id', 'channel_id']):
        return jsonify({'success': False, 'message': 'Missing required payment data.'}), 400
    
    asset = DigitalAsset.query.get(data['asset_id'])
    if not asset:
        return jsonify({'success': False, 'message': 'The selected product could not be found.'}), 404

    # 1. Find or create the customer
    customer = Customer.query.filter_by(whatsapp_number=data['phone_number']).first()
    if not customer:
        customer = Customer(whatsapp_number=data['phone_number'])
        db.session.add(customer)
        db.session.commit()

    # 2. Create a new Purchase record in 'PENDING' state
    # This record now contains our internal transaction_token and the SSE channel link
    new_purchase = Purchase(
        customer_id=customer.id,
        asset_id=asset.id,
        amount_paid=asset.price,
        status=PurchaseStatus.PENDING,
        sse_channel_id=data['channel_id']
    )
    db.session.add(new_purchase)
    db.session.commit()
    
    # 3. >>> REAL WORLD: Call the UZA payment gateway API <<<
    #    response = requests.post("https://api.uza.com/v1/charge", json={
    #        "phone_number": data['phone_number'],
    #        "amount": str(new_purchase.amount_paid),
    #        "reference": new_purchase.transaction_token, # Send OUR ID to UZA
    #        "callback_url": url_for('main.uza_payment_callback', _external=True)
    #    })
    #    uza_data = response.json()
    #    uza_transaction_id = uza_data.get('transaction_id')

    # --- SIMULATION of the UZA API response ---
    # UZA generates its own ID and sends it back to us immediately.
    uza_transaction_id = f"UZA_{uuid.uuid4().hex[:12].upper()}"
    current_app.logger.info(
        f"Simulating UZA API call for our transaction '{new_purchase.transaction_token}'. "
        f"UZA responds with its own ID: '{uza_transaction_id}'"
    )

    # 4. Store the UZA transaction ID in our database
    new_purchase.payment_gateway_ref = uza_transaction_id
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f"A payment request for {asset.title} has been sent. Please approve it."
    })


@main_bp.route('/api/uza-callback', methods=['POST'])
def uza_payment_callback():
    """
    THIS IS THE WEBHOOK ENDPOINT FOR UZA.
    It is unauthenticated and will be called by the UZA servers.
    """
    data = request.get_json()
    
    # The UZA documentation says they will send back their ID in the 'gateway_ref' field
    # and our original ID in the 'reference' field. We'll use our reference.
    our_transaction_token = data.get('reference') # UZA calls it 'reference'
    uza_gateway_ref = data.get('gateway_ref')     # UZA's ID for the transaction
    status = data.get('status')                   # e.g., "COMPLETED" or "FAILED"

    if not our_transaction_token:
        current_app.logger.error("UZA Callback received without a 'reference' (our transaction_token).")
        return jsonify({'status': 'error', 'message': 'Missing reference'}), 400

    # Find the original purchase record using the token we sent to UZA
    purchase = Purchase.query.filter_by(transaction_token=our_transaction_token).first()
    if not purchase:
        current_app.logger.error(f"UZA Callback for unknown transaction_token: {our_transaction_token}")
        return jsonify({'status': 'error', 'message': 'Transaction not found'}), 404
        
    if purchase.status == PurchaseStatus.COMPLETED:
        return jsonify({'status': 'ok', 'message': 'Transaction already processed'}), 200

    if status == 'COMPLETED':
        purchase.status = PurchaseStatus.COMPLETED
        purchase.payment_gateway_ref = uza_gateway_ref # Store UZA's final reference ID
        
        asset = purchase.asset
        asset.total_sales = (asset.total_sales or 0) + 1
        asset.total_revenue = (asset.total_revenue or 0) + purchase.amount_paid
        session['customer_phone'] = purchase.customer.whatsapp_number
        
        db.session.commit()
        
        # Notify the waiting frontend via SSE
        sse_manager.publish(purchase.sse_channel_id, {
            'status': 'SUCCESS', 
            'message': 'Payment confirmed! Thank you.',
            'redirect_url': url_for('main.library')
        })
        current_app.logger.info(f"Processed successful payment for transaction {our_transaction_token}")
    else:
        purchase.status = PurchaseStatus.FAILED
        db.session.commit()
        
        sse_manager.publish(purchase.sse_channel_id, {
            'status': 'FAILED',
            'message': data.get('message', 'Payment was not completed.')
        })
        current_app.logger.info(f"Processed failed payment for transaction {our_transaction_token}")

    return jsonify({'status': 'ok'}), 200

@main_bp.route('/api/payment-stream/<channel_id>')
def payment_stream(channel_id):
    def event_stream():
        q = sse_manager.subscribe(channel_id)
        try:
            # Wait for a message. Timeout after 60 seconds.
            message = q.get(timeout=60)
            yield message
        except queue.Empty:
            # This is our fallback mechanism for timeouts
            yield f'data: {json.dumps({"status": "TIMEOUT"})}\n\n'
        finally:
            sse_manager.unsubscribe(channel_id)

    return Response(event_stream(), mimetype='text/event-stream')
    
@main_bp.route('/library', methods=['GET', 'POST'])
def library():
    customer_phone = session.get('customer_phone')
    
    if request.method == 'POST':
        form_phone = request.form.get('phone_number')
        if form_phone:
            session['customer_phone'] = form_phone.strip()
            return redirect(url_for('main.library'))

    purchases = []
    if customer_phone:
        customer = Customer.query.filter_by(whatsapp_number=customer_phone).first()
        if customer:
            purchases = Purchase.query.filter_by(customer_id=customer.id).order_by(Purchase.purchase_date.desc()).all()
    
    creator = Creator.query.first()

    return render_template(
        'user/library.html',
        customer_phone=customer_phone,
        purchases=purchases,
        store_name=creator.store_name if creator else "Creator Store",
        currency_symbol=creator.get_setting('currency_symbol', '$') if creator else '$'
    )

@main_bp.route('/logout')
def logout():
    """Logs out the customer by clearing their phone from the session."""
    session.pop('customer_phone', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('main.library'))