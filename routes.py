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
    SubscriptionInterval, CreatorSetting, Customer, Purchase, Comment
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
    total_earnings = db.session.query(func.sum(DigitalAsset.total_revenue)).filter(DigitalAsset.creator_id == g.creator.id).scalar() or 0.0
    total_sales = db.session.query(func.sum(DigitalAsset.total_sales)).filter(DigitalAsset.creator_id == g.creator.id).scalar() or 0
    total_assets = DigitalAsset.query.filter(DigitalAsset.creator_id == g.creator.id).count()
    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
    new_supporters = Customer.query.join(Purchase).join(DigitalAsset).filter(DigitalAsset.creator_id == g.creator.id, Customer.created_at >= start_of_month).count()
    earnings_this_month = db.session.query(func.sum(Purchase.amount_paid)).join(DigitalAsset).filter(DigitalAsset.creator_id == g.creator.id, Purchase.purchase_date >= start_of_month).scalar() or 0.0
    stats = {'total_earnings': total_earnings, 'total_sales': total_sales, 'total_assets': total_assets, 'new_supporters': new_supporters, 'earnings_this_month': earnings_this_month}
    activity = [] # TODO: Fetch recent activity
    return render_template('admin/dashboard.html', stats=stats, activity=activity)

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
    return render_template('admin/supporters.html', supporters=[])

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

    # --- DISPLAY SETTINGS LOGIC (GET request) ---
    all_settings = CreatorSetting.query.filter_by(creator_id=g.creator.id).all()
    
    # Organize settings into a simple dictionary for easy access in the template
    settings_dict = {setting.key: setting.value for setting in all_settings}
    
    # Add core creator fields to the dictionary for a unified 'settings' object
    settings_dict['store_name'] = g.creator.store_name
    settings_dict['store_handle'] = g.creator.store_handle

    return render_template('admin/settings.html', settings=settings_dict)

# ==============================================================================
# == MAIN (PUBLIC) BLUEPRINT
# ==============================================================================
# NOTE: This section uses mock data and will need to be updated later.
# It is preserved to prevent the public-facing pages from crashing.

# Mock SSE Manager
class SseManager:
    def __init__(self): self.channels, self.lock = {}, threading.Lock()
    def subscribe(self, channel_id):
        with self.lock: q = queue.Queue(5); self.channels[channel_id] = q; return q
    def unsubscribe(self, channel_id):
        with self.lock: self.channels.pop(channel_id, None)
    def publish(self, channel_id, data):
        with self.lock:
            if channel_id in self.channels:
                try: self.channels[channel_id].put_nowait(f"data: {json.dumps(data)}\n\n")
                except queue.Full: pass
sse_manager = SseManager()

def mock_payment_worker(channel_id, phone, url):
    time.sleep(5)
    sse_manager.publish(channel_id, {'status': 'SUCCESS', 'message': 'Payment confirmed!', 'redirect_url': url})
    time.sleep(2)
    sse_manager.unsubscribe(channel_id)

@main_bp.route('/')
def landing_page():
    creator = Creator.query.first();
    if not creator: return "<h1>Store not set up yet.</h1>", 503
    assets = DigitalAsset.query.filter_by(status=AssetStatus.PUBLISHED, creator_id=creator.id).all()
    assets_data = [a.to_dict() for a in assets]
    return render_template('user/index.html', assets=json.dumps(assets_data, default=json_serial))

@main_bp.route('/asset/<slug>')
def asset_detail(slug):
    asset = DigitalAsset.query.filter_by(slug=slug, status=AssetStatus.PUBLISHED).first_or_404()
    return render_template('user/asset_detail.html', asset=json.dumps(asset.to_dict(), default=json_serial))

@main_bp.route('/checkout/<slug>')
def checkout(slug):
    asset = DigitalAsset.query.filter_by(slug=slug, status=AssetStatus.PUBLISHED).first_or_404()
    return render_template('user/checkout.html', asset=asset.to_dict(), channel_id=str(uuid.uuid4()))

@main_bp.route('/api/initiate-payment', methods=['POST'])
def initiate_payment():
    data = request.get_json()
    if not all(k in data for k in ['phone_number', 'asset_id', 'channel_id']):
        return jsonify({'success': False, 'message': 'Missing data.'}), 400
    success_url = url_for('main.library', _external=True)
    threading.Thread(target=mock_payment_worker, args=(data['channel_id'], data['phone_number'], success_url)).start()
    return jsonify({'success': True, 'message': 'Payment initiated.'})

@main_bp.route('/api/payment-stream/<channel_id>')
def payment_stream(channel_id):
    def event_stream():
        q = sse_manager.subscribe(channel_id)
        try: yield q.get(timeout=60)
        except queue.Empty: yield f'data: {json.dumps({"status": "TIMEOUT"})}\n\n'
        finally: sse_manager.unsubscribe(channel_id)
    return Response(event_stream(), mimetype='text/event-stream')
    
@main_bp.route('/library')
def library():
    return "<h1>Your Library</h1><p>This is a placeholder for purchased assets.</p>"