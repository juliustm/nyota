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
import requests
import re
from datetime import datetime, date, timedelta # Added timedelta
from functools import wraps
from flask import (
    Blueprint, render_template, request, jsonify, redirect, 
    url_for, flash, g, session, current_app, abort, send_from_directory,
    Response
)
from werkzeug.utils import secure_filename
from sqlalchemy import or_, func, distinct
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.declarative import DeclarativeMeta

from models.nyota import (
    db, Creator, CreatorSetting, DigitalAsset, AssetFile, 
    Purchase, Customer, Subscription, Comment, Rating, 
    Ambassador, AssetStatus, AssetType, PurchaseStatus, 
    SubscriptionInterval, SubscriptionStatus, TicketStatus,
    AccessAttempt
)
from utils.security import creator_login_required, generate_totp_secret, get_totp_uri, verify_totp
from utils.translator import translate
from extensions import limiter

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
    # --- FILTERS ---
    period = request.args.get('period', '30d') # Default to last 30 days
    asset_id = request.args.get('asset_id', type=int)
    
    start_date = None
    end_date = datetime.utcnow()
    
    if period == '7d':
        start_date = end_date - timedelta(days=7)
    elif period == '30d':
        start_date = end_date - timedelta(days=30)
    elif period == '90d':
        start_date = end_date - timedelta(days=90)
    elif period == '1y':
        start_date = end_date - timedelta(days=365)
    elif period == 'all':
        start_date = None
    elif period == 'custom':
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            except ValueError:
                pass
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1) - timedelta(seconds=1) # End of day
            except ValueError:
                pass

    # Base Query for Completed Purchases
    base_query = db.session.query(Purchase).join(DigitalAsset).filter(
        DigitalAsset.creator_id == g.creator.id,
        Purchase.status == PurchaseStatus.COMPLETED
    )

    if asset_id:
        base_query = base_query.filter(Purchase.asset_id == asset_id)
    
    # --- STATS CALCULATION ---
    
    # Total Earnings (Filtered by Asset, but usually we want Total All Time or Filtered Period?)
    # Let's make the "Total Earnings" card respect the Time Filter too, or maybe keep it All Time?
    # Usually "Total Earnings" implies All Time. "Earnings (Period)" implies Filter.
    # But for a standard dashboard, often top cards update with filters. 
    # Let's align with "Earnings (This Month)" replacement -> "Earnings (Selected Period)"
    
    # 1. Total Earnings (All Time, but filtered by Asset if selected)
    total_earnings_query = db.session.query(func.sum(Purchase.amount_paid)).join(DigitalAsset).filter(
        DigitalAsset.creator_id == g.creator.id,
        Purchase.status == PurchaseStatus.COMPLETED
    )
    if asset_id:
        total_earnings_query = total_earnings_query.filter(Purchase.asset_id == asset_id)
    total_earnings = total_earnings_query.scalar() or decimal.Decimal(0)

    # 2. Earnings (Selected Period)
    period_earnings_query = base_query
    if start_date:
        period_earnings_query = period_earnings_query.filter(Purchase.purchase_date >= start_date)
    if end_date and period == 'custom':
        period_earnings_query = period_earnings_query.filter(Purchase.purchase_date <= end_date)
    period_earnings = period_earnings_query.with_entities(func.sum(Purchase.amount_paid)).scalar() or decimal.Decimal(0)

    # 3. Total Sales (Selected Period)
    period_sales = period_earnings_query.with_entities(func.count(Purchase.id)).scalar() or 0

    # 4. Supporters (Total Unique, filtered by Asset if selected)
    # Note: Supporters count usually refers to total unique customers all time for the creator/asset
    supporters_query = db.session.query(func.count(Customer.id.distinct())).join(Purchase).join(DigitalAsset).filter(
        DigitalAsset.creator_id == g.creator.id,
        Purchase.status == PurchaseStatus.COMPLETED
    )
    if asset_id:
        supporters_query = supporters_query.filter(Purchase.asset_id == asset_id)
    supporters_count = supporters_query.scalar() or 0

    # New Supporters (Selected Period) - Customers whose *first* purchase was in this period? 
    # Or just unique customers who bought in this period?
    # Let's do unique customers who bought in this period for simplicity as "Active Supporters"
    # period_supporters = period_earnings_query.with_entities(func.count(Purchase.customer_id.distinct())).scalar() or 0
    
    stats = {
        'total_earnings': total_earnings,
        'period_earnings': period_earnings,
        'period_sales': period_sales,
        'supporters_count': supporters_count,
        'period': period
    }
    
    # --- RECENT ACTIVITY (SALES) with PAGINATION ---
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    per_page = 10
    
    activity_query = Purchase.query.join(DigitalAsset).filter(
        DigitalAsset.creator_id == g.creator.id
    )
    
    if asset_id:
        activity_query = activity_query.filter(Purchase.asset_id == asset_id)
        
    if start_date:
        activity_query = activity_query.filter(Purchase.purchase_date >= start_date)
    if end_date and period == 'custom':
        activity_query = activity_query.filter(Purchase.purchase_date <= end_date)

    if search:
        activity_query = activity_query.join(Customer).filter(
            or_(
                Customer.whatsapp_number.ilike(f"%{search}%"),
                DigitalAsset.title.ilike(f"%{search}%")
            )
        )
        
    recent_activity = activity_query.order_by(Purchase.purchase_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Fetch all assets for the filter dropdown
    all_assets = DigitalAsset.query.filter_by(creator_id=g.creator.id).with_entities(DigitalAsset.id, DigitalAsset.title).all()

    return render_template(
        'admin/dashboard.html', 
        stats=stats, 
        activity=recent_activity,
        assets=all_assets,
        current_filters={
            'period': period,
            'asset_id': asset_id,
            'search': search
        }
    )

@admin_bp.route('/assets')
@creator_login_required
def list_assets():
    # --- FILTERS & PAGINATION ---
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '').strip()
    per_page = 20

    query = DigitalAsset.query.filter_by(creator_id=g.creator.id)

    if search:
        query = query.filter(DigitalAsset.title.ilike(f"%{search}%"))
    
    if status and status in [s.value for s in AssetStatus]:
        query = query.filter(DigitalAsset.status == AssetStatus(status))
    
    pagination = query.order_by(DigitalAsset.updated_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    creator_assets = pagination.items

    assets_data = [{
        'id': a.id, 
        'title': a.title, 
        'description': a.description, 
        'cover': a.cover_image_url, 
        'type': a.asset_type.name, 
        'status': a.status.value, 
        'sales': a.total_sales, 
        'revenue': float(a.total_revenue), 
        'updated_at': a.updated_at
    } for a in creator_assets]
    
    # --- STATS ---
    stats = {
        'total_assets': DigitalAsset.query.filter_by(creator_id=g.creator.id).count(),
        'published_count': DigitalAsset.query.filter_by(creator_id=g.creator.id, status=AssetStatus.PUBLISHED).count(),
        'total_revenue': db.session.query(func.sum(DigitalAsset.total_revenue)).filter_by(creator_id=g.creator.id).scalar() or 0.0,
        'total_sales': db.session.query(func.sum(DigitalAsset.total_sales)).filter_by(creator_id=g.creator.id).scalar() or 0
    }

    return render_template(
        'admin/assets.html', 
        assets_json=json.dumps(assets_data, default=json_serial),
        assets=assets_data,
        pagination=pagination,
        stats=stats,
        current_filters={'search': search, 'status': status}
    )

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
            return redirect(url_for('admin.asset_edit', asset_id=new_asset.id))
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
    return render_template('admin/asset_view.html', asset=asset, recent_purchases=recent_purchases, recent_comments=recent_comments, statuses=[s.value for s in AssetStatus])

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
        statuses=[s.value for s in AssetStatus]
    )

@admin_bp.route('/assets/save', methods=['POST'])
@creator_login_required
def save_asset():
    try:
        if 'asset_data' not in request.form:
            raise ValueError("Form submission incomplete.")
        
        form_data = json.loads(request.form['asset_data'])
        asset_id = form_data.get('asset', {}).get('id')
        
        if asset_id:
            asset = DigitalAsset.query.filter_by(id=asset_id, creator_id=g.creator.id).first_or_404()
        else:
            asset = DigitalAsset(creator_id=g.creator.id)
            
        save_asset_from_form(asset, request)
        
        if not asset_id:
            db.session.add(asset)
            
        db.session.commit()
        
        if request.headers.get('Accept') == 'application/json':
            return jsonify({'success': True, 'message': f"Asset '{asset.title}' saved successfully!"})
            
        flash(f"Asset '{asset.title}' saved successfully!", "success")
        return redirect(url_for('admin.asset_edit', asset_id=asset.id))
        
    except ValueError as e:
        if request.headers.get('Accept') == 'application/json':
            return jsonify({'success': False, 'message': str(e)}), 400
        flash(str(e), 'danger')
        return redirect(url_for('admin.asset_new'))
    except Exception as e:
        current_app.logger.error(f"Error saving asset: {e}")
        if request.headers.get('Accept') == 'application/json':
            return jsonify({'success': False, 'message': 'A server error occurred.'}), 500
        flash("An error occurred while saving the asset.", "danger")
        return redirect(url_for('admin.list_assets'))

@main_bp.route('/content/<int:file_id>')
def serve_content(file_id):
    # Check if user is logged in
    customer_phone = session.get('customer_phone')
    # STRICT SESSION CHECK: Ensure the session is fully verified
    if not customer_phone or not session.get('is_verified'):
        abort(403)
        
    # Get the file
    asset_file = AssetFile.query.get_or_404(file_id)
    
    # Check if user purchased the asset
    customer = Customer.query.filter_by(whatsapp_number=customer_phone).first()
    if not customer:
        abort(403)
        
    purchase = Purchase.query.filter_by(
        customer_id=customer.id,
        asset_id=asset_file.asset_id,
        status=PurchaseStatus.COMPLETED
    ).order_by(Purchase.purchase_date.desc()).first()
    
    # Allow creator to view their own assets
    creator_id = session.get('creator_id')
    is_creator = creator_id and asset_file.asset.creator_id == creator_id
    
    if not purchase and not is_creator:
        abort(403)
        
    # Check subscription status
    if purchase and purchase.asset.is_subscription:
        is_active, expiry_date = check_subscription_status(purchase)
        if not is_active:
            flash(f"Your subscription expired on {expiry_date.strftime('%Y-%m-%d')}. Please renew to access this content.", "warning")
            return redirect(url_for('main.asset_detail', slug=purchase.asset.slug))
        
    # Serve the file
    # storage_path is stored as "secure_uploads/filename"
    if asset_file.storage_path.startswith('secure_uploads/'):
        filename = asset_file.storage_path.replace('secure_uploads/', '')
        directory = os.path.join(current_app.instance_path, 'secure_uploads')
        return send_from_directory(directory, filename)
    else:
        # It's an external link, redirect to it
        return redirect(asset_file.storage_path)



def check_subscription_status(purchase):
    """
    Checks if a subscription purchase is still active.
    Returns (is_active, expiry_date).
    """
    if not purchase.asset.is_subscription:
        return True, None
        
    start_date = purchase.purchase_date
    interval = purchase.asset.subscription_interval.name.lower() if purchase.asset.subscription_interval else 'monthly'
    
    # Override interval if tier is selected
    if purchase.ticket_data and 'tier' in purchase.ticket_data:
        interval = purchase.ticket_data['tier'].get('interval', interval).lower()
        
    if interval == 'weekly':
        delta = timedelta(days=7)
    elif interval == 'quarterly':
        delta = timedelta(days=90)
    elif interval == 'yearly':
        delta = timedelta(days=365)
    else: # monthly
        delta = timedelta(days=30)
        
    expiry_date = start_date + delta
    is_active = datetime.utcnow() < expiry_date
    return is_active, expiry_date

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
    
    # Ensure details is a dictionary and create a copy to modify
    asset.details = dict(asset.details or {})
    
    # Store UZA Product ID for the asset
    uza_product_id = asset_details.get('uza_product_id', '').strip()
    if uza_product_id:
        asset.details['uza_product_id'] = uza_product_id
    
    # Handle Subscription Tiers (which may also have UZA Product IDs)
    if asset.is_subscription:
        asset.details['subscription_tiers'] = pricing_data.get('tiers', [])

    if asset.asset_type == AssetType.TICKET:
        event_details = form_data.get('eventDetails', {})
        asset.event_location, asset.custom_fields = event_details.get('link'), form_data.get('customFields', [])
        if event_details.get('date') and event_details.get('time'):
            try: asset.event_date = datetime.strptime(f"{event_details['date']} {event_details['time']}", '%Y-%m-%d %H:%M')
            except (ValueError, TypeError): asset.event_date = None
        asset.max_attendees = int(event_details.get('maxAttendees')) if event_details.get('maxAttendees') else None
        
        # Store post-purchase instructions
        asset.details['postPurchaseInstructions'] = event_details.get('postPurchaseInstructions', '')
        
    elif asset.asset_type == AssetType.SUBSCRIPTION: 
        # Merge existing details with subscription details
        asset.details.update(form_data.get('subscriptionDetails', {}))
    elif asset.asset_type == AssetType.NEWSLETTER: 
        # Merge existing details with newsletter details
        asset.details.update(form_data.get('newsletterDetails', {}))
    
    # Explicitly flag details as modified to ensure SQLAlchemy saves the JSON changes
    flag_modified(asset, 'details')
    
    # Preserve existing file paths if not re-uploaded
    existing_files_map = {}
    if asset.id:
        existing_files = AssetFile.query.filter_by(asset_id=asset.id).all()
        for f in existing_files:
            existing_files_map[f.id] = {'path': f.storage_path, 'type': f.file_type}
            
    AssetFile.query.filter_by(asset_id=asset.id).delete()
    
    secure_upload_dir = os.path.join(current_app.instance_path, 'secure_uploads')
    os.makedirs(secure_upload_dir, exist_ok=True)
    
    for i, item in enumerate(form_data.get('contentItems', [])):
        # Check for uploaded file
        file_key = f'content_file_{i}'
        uploaded_file = req.files.get(file_key)
        
        storage_path = item.get('link', '')
        file_type = None
        
        if uploaded_file and uploaded_file.filename:
            # Save new file
            filename = secure_filename(uploaded_file.filename)
            unique_filename = f"{int(datetime.now().timestamp())}_{filename}"
            uploaded_file.save(os.path.join(secure_upload_dir, unique_filename))
            storage_path = f"secure_uploads/{unique_filename}"
            
            # Infer type from filename
            extension = filename.split('.')[-1].lower()
        elif storage_path:
            # Check if it's a secure link that needs resolving
            if storage_path.startswith('/content/'):
                try:
                    old_file_id = int(storage_path.split('/')[-1])
                    if old_file_id in existing_files_map:
                        storage_path = existing_files_map[old_file_id]['path']
                        file_type = existing_files_map[old_file_id]['type']
                except (ValueError, IndexError):
                    pass # Keep as is if parsing fails
            
            # If we resolved it (or it was external), infer type if missing
            if not file_type:
                extension = storage_path.split('.')[-1].lower().split('?')[0]
        else:
            extension = ''

        # Infer file type if not already set (from existing file)
        if not file_type:
            if extension in ['pdf']:
                file_type = 'pdf'
            elif extension in ['mp3', 'wav', 'ogg', 'm4a', 'aac']:
                file_type = 'audio'
            elif extension in ['mp4', 'webm', 'mov', 'avi']:
                file_type = 'video'
            elif extension in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg']:
                file_type = 'image'
            else:
                file_type = 'other'
        
        db.session.add(AssetFile(
            asset=asset, 
            title=item.get('title'), 
            description=item.get('description'), 
            storage_path=storage_path,
            file_type=file_type,
            order_index=i
        ))

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
        new_asset = DigitalAsset(
            creator_id=g.creator.id, 
            title=f"Copy of {original.title}", 
            status=AssetStatus.DRAFT, 
            description=original.description, 
            story=original.story, 
            cover_image_url=original.cover_image_url, 
            asset_type=original.asset_type, 
            price=original.price, 
            is_subscription=original.is_subscription, 
            subscription_interval=original.subscription_interval, 
            event_date=original.event_date, 
            event_location=original.event_location, 
            max_attendees=original.max_attendees, 
            custom_fields=original.custom_fields, 
            details=original.details
        )
        db.session.add(new_asset)
        db.session.flush() # Get the ID for the new asset
        
        # Duplicate files
        for file in original.files:
            db.session.add(AssetFile(
                asset_id=new_asset.id,
                title=file.title,
                description=file.description,
                storage_path=file.storage_path,
                file_type=file.file_type,
                order_index=file.order_index
            ))
            
        db.session.commit()
        return jsonify({'success': True, 'message': f"'{original.title}' was duplicated successfully."})
    except Exception as e:
        db.session.rollback(); current_app.logger.error(f"Duplication error: {e}"); return jsonify({'success': False, 'message': 'A server error occurred.'}), 500

@admin_bp.route('/supporters')
@creator_login_required
def supporters():
    """Fetches all customers and their aggregated data for the admin supporters page."""
    
    # --- FILTERS & PAGINATION ---
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    asset_id = request.args.get('asset_id', type=int)
    per_page = 20

    # 1. Base Query to Find Supporter IDs (Efficient Filtering)
    # Start with Customer to facilitate search on phone number
    query = db.session.query(Customer.id).distinct().join(Purchase).join(DigitalAsset).filter(
        DigitalAsset.creator_id == g.creator.id
    )

    if search:
        # Search by phone number (whatsapp_number)
        query = query.filter(Customer.whatsapp_number.ilike(f"%{search}%"))
        
    if asset_id:
        query = query.filter(Purchase.asset_id == asset_id)

    # 2. Get TOTAL COUNT for pagination (before slicing logic, but wait, distinct makes count tricky)
    # The clean way with distinct is query.count() which SQLAlchemy handles well usually, 
    # but for manual pagination we need IDs first.
    
    # Execute query to get ALL matching IDs (for this creator/filter)
    # Optimization: If listing is huge, this list might be big, but for < 10k items it's fine.
    # For true scalability we'd paginate the subquery, but let's grab IDs for now.
    all_supporter_ids = [item[0] for item in query.all()]
    
    total_items = len(all_supporter_ids)
    
    # Slice IDs for current page
    start = (page - 1) * per_page
    end = start + per_page
    page_supporter_ids = all_supporter_ids[start:end]

    # 3. Fetch full objects for the current page
    if page_supporter_ids:
        all_customers = db.session.query(Customer).filter(
            Customer.id.in_(page_supporter_ids)
        ).options(
            db.selectinload(Customer.purchases).joinedload(Purchase.asset), # Load asset for creator check
            db.selectinload(Customer.subscriptions),
            db.selectinload(Customer.ambassador_profile)
        ).all()
        
    else:
        all_customers = []

    # 4. Serialize each customer
    supporters_data = [customer.to_dict_detailed(creator_id=g.creator.id) for customer in all_customers]

    # Create a simple pagination object to mimic SQLAlchemy's Pagination
    class SimplePagination:
        def __init__(self, page, per_page, total, items):
            self.page = page
            self.per_page = per_page
            self.total = total
            self.items = items
            self.pages = int((total + per_page - 1) / per_page)
            self.has_prev = page > 1
            self.has_next = page < self.pages
            self.prev_num = page - 1
            self.next_num = page + 1
            
        def iter_pages(self, left_edge=2, left_current=2, right_current=5, right_edge=2):
            last = 0
            for num in range(1, self.pages + 1):
                if num <= left_edge or \
                   (num > self.page - left_current - 1 and num < self.page + right_current) or \
                   num > self.pages - right_edge:
                    if last + 1 != num:
                        yield None
                    yield num
                    last = num

    pagination = SimplePagination(page, per_page, total_items, supporters_data)
    
    # Fetch all assets for filter
    all_assets = DigitalAsset.query.filter_by(creator_id=g.creator.id).with_entities(DigitalAsset.id, DigitalAsset.title).all()

    # --- STATS ---
    total_supporters = db.session.query(func.count(distinct(Customer.id))).join(Purchase).join(DigitalAsset).filter(DigitalAsset.creator_id == g.creator.id).scalar() or 0
    
    total_revenue = db.session.query(func.sum(Purchase.amount_paid)).join(DigitalAsset).filter(DigitalAsset.creator_id == g.creator.id, Purchase.status == PurchaseStatus.COMPLETED).scalar() or 0.0
    
    affiliate_count = db.session.query(func.count(distinct(Customer.id))).join(Purchase).join(DigitalAsset).outerjoin(Ambassador, Customer.id == Ambassador.customer_id).filter(DigitalAsset.creator_id == g.creator.id, Ambassador.id != None).scalar() or 0
    
    avg_ltv = (total_revenue / total_supporters) if total_supporters > 0 else 0.0

    stats = {
        'total_supporters': total_supporters,
        'total_revenue': total_revenue,
        'affiliate_count': affiliate_count,
        'avg_ltv': avg_ltv
    }

    return render_template(
        'admin/supporters.html', 
        supporters_json=json.dumps(supporters_data, default=json_serial),
        supporters=supporters_data,
        pagination=pagination,
        assets=all_assets,
        stats=stats,
        current_filters={'search': search, 'asset_id': asset_id}
    )

@admin_bp.route('/supporters/<int:id>')
@creator_login_required
def supporter_detail(id):
    customer = Customer.query.get_or_404(id)
    
    # Calculate stats
    purchases = Purchase.query.join(DigitalAsset).filter(
        Purchase.customer_id == id,
        DigitalAsset.creator_id == g.creator.id
    ).order_by(Purchase.purchase_date.desc()).all()
    
    total_spent = sum(p.amount_paid for p in purchases if p.status == PurchaseStatus.COMPLETED)
    purchase_count = len([p for p in purchases if p.status == PurchaseStatus.COMPLETED])
    avg_order = (total_spent / purchase_count) if purchase_count > 0 else 0
    
    stats = {
        'total_spent': total_spent,
        'purchase_count': purchase_count,
        'avg_order': avg_order
    }
    
    return render_template(
        'admin/supporter_detail.html',
        supporter=customer,
        purchases=purchases,
        stats=stats
    )

# --- TOOLTIP API ENDPOINTS ---

@admin_bp.route('/api/tooltip/customer/<int:id>')
@creator_login_required
def tooltip_customer(id):
    customer = Customer.query.get_or_404(id)
    currency_symbol = g.creator.get_setting('currency_symbol', 'TZS')
    
    # Creator-specific stats
    query = db.session.query(
        func.sum(Purchase.amount_paid),
        func.count(Purchase.id),
        func.max(Purchase.purchase_date)
    ).join(DigitalAsset).filter(
        Purchase.customer_id == id,
        DigitalAsset.creator_id == g.creator.id,
        Purchase.status == PurchaseStatus.COMPLETED
    )
    
    total_spent, count, last_active = query.first()
    
    return jsonify({
        'title': customer.whatsapp_number,
        'items': [
            {'label': 'Joined', 'value': customer.created_at.strftime('%b %Y')},
            {'label': 'Total Spent', 'value': f"{currency_symbol} {total_spent:,.2f}" if total_spent else f"{currency_symbol} 0.00"},
            {'label': 'Purchases', 'value': str(count or 0)},
            {'label': 'Last Active', 'value': last_active.strftime('%b %d') if last_active else 'N/A'}
        ]
    })

@admin_bp.route('/api/tooltip/asset/<int:id>')
@creator_login_required
def tooltip_asset(id):
    asset = DigitalAsset.query.get_or_404(id)
    if asset.creator_id != g.creator.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    currency_symbol = g.creator.get_setting('currency_symbol', 'TZS')
        
    return jsonify({
        'title': asset.title,
        'items': [
            {'label': 'Price', 'value': f"{currency_symbol} {asset.price:,.2f}"},
            {'label': 'Status', 'value': asset.status.value},
            {'label': 'Sales', 'value': str(asset.total_sales)},
            {'label': 'Revenue', 'value': f"{currency_symbol} {asset.total_revenue:,.2f}"}
        ]
    })

@admin_bp.route('/api/tooltip/purchase/<int:id>')
@creator_login_required
def tooltip_purchase(id):
    purchase = Purchase.query.get_or_404(id)
    # Ensure creator owns the asset involved
    if purchase.asset.creator_id != g.creator.id:
        return jsonify({'error': 'Unauthorized'}), 403
        
    return jsonify({
        'title': f"Order #{purchase.id}",
        'items': [
            {'label': 'Date', 'value': purchase.purchase_date.strftime('%b %d, %I:%M %p')},
            {'label': 'Gateway Ref', 'value': purchase.payment_gateway_ref or 'N/A'},
            {'label': 'Status', 'value': purchase.status.value},
            {'label': 'Transaction', 'value': purchase.transaction_token[:8] + '...'}
        ]
    })
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
        
        # --- A DEFINITIVE LIST OF ALL POSSIBLE SETTING KEYS FROM THE TEMPLATE ---
        setting_keys = [
            'store_bio', 'social_twitter', 'social_instagram', 'contact_email', 'contact_phone',
            'appearance_storefront_theme', 'admin_theme',
            
            # Notifications
            'telegram_enabled', 'telegram_bot_token', 'telegram_chat_id', 
            'telegram_payments', 'telegram_ratings', 'telegram_comments',
            'whatsapp_enabled', 'whatsapp_phone_id', 'whatsapp_access_token',
            'sms_provider', 'twilio_sid', 'twilio_token', 'twilio_phone',
            'beem_api_key', 'beem_secret_key', 'beem_sender_name',

            # Payments
            'payment_uza_enabled', 'payment_uza_pk', 'payment_uza_secret', 'payment_uza_refcode', 'payment_uza_source', 'payment_uza_currency',
            'stripe_enabled', 'paypal_enabled',

            # AI & Automation
            'ai_enabled', 'ai_provider', 'groq_api_key', 'ai_temperature',
            'ai_content_suggestions', 'ai_seo_optimization', 'ai_email_templates', 'ai_analytics',

            # Social
            'instagram_connected', 'instagram_ai_enabled', 'instagram_keywords', 
            'ig_response_delay', 'ig_ai_personality',

            # Productivity
            'google_connected', 'google_calendar_id', 'sync_events', 'send_reminders', 'check_conflicts',
            
            # Email Delivery
            'email_smtp_enabled', 'smtp_host', 'smtp_port', 'smtp_user', 'smtp_pass', 
            'smtp_encryption', 'smtp_sender_email', 'smtp_sender_name'
        ]

        # Iterate and save each setting
        for key in setting_keys:
            # Handle checkboxes, which are only present in form data if checked
            if key.endswith('_enabled') or key.endswith('_connected') or key.startswith('telegram_') or key.startswith('ai_feature_') or key in ['sync_events', 'send_reminders', 'check_conflicts']:
                value = True if request.form.get(key) == 'on' else False
            else:
                value = request.form.get(key)
            
            # Don't save empty password/token fields if a value already exists
            if ('token' in key or 'pass' in key or '_sk' in key or '_pk' in key or '_secret' in key) and not value:
                continue
            
            g.creator.set_setting(key, value)
        
        # Handle file upload for store logo
        if 'store_logo' in request.files:
            file = request.files['store_logo']
            if file and file.filename:
                filename = f"logo_{g.creator.id}_{int(time.time())}_{secure_filename(file.filename)}"
                upload_path = os.path.join(current_app.root_path, 'static/uploads/logos')
                os.makedirs(upload_path, exist_ok=True)
                file.save(os.path.join(upload_path, filename))
                g.creator.set_setting('store_logo_url', f'/static/uploads/logos/{filename}')

        db.session.commit()
        flash("Settings saved successfully!", "success")
        return redirect(url_for('admin.manage_settings'))

    # --- DISPLAY SETTINGS LOGIC (GET request) ---
    all_settings = CreatorSetting.query.filter_by(creator_id=g.creator.id).all()
    settings_dict = {setting.key: setting.value for setting in all_settings}
    
    settings_dict['store_name'] = g.creator.store_name
    settings_dict['store_handle'] = g.creator.store_handle
    settings_json = json.dumps(settings_dict, default=json_serial)

    return render_template('admin/settings.html', settings_json=settings_json)

# ==============================================================================
# == MAIN (PUBLIC) BLUEPRINT
# ==============================================================================
# NOTE: This section uses mock data and will need to be updated later.
# It is preserved to prevent the public-facing pages from crashing.

# Enhanced SSE Manager with Persistent Channels
# Using standard logger to avoid application context issues in background threads/generators
import logging
sse_logger = logging.getLogger(__name__)

class SseManager:
    def __init__(self):
        self.channels = {}
        self.lock = threading.Lock()

    def subscribe(self, channel_id):
        """Subscribe to a channel. Creates it if it doesn't exist, reuses if it does."""
        with self.lock:
            if channel_id in self.channels:
                # Channel already exists, reuse it (for reconnections)
                sse_logger.info(f"Reconnecting to existing SSE channel: {channel_id}")
                return self.channels[channel_id]
            else:
                # Create new channel
                q = queue.Queue(10)  # Increased queue size for reliability
                self.channels[channel_id] = q
                sse_logger.info(f"Created new SSE channel: {channel_id}")
                return q

    def unsubscribe(self, channel_id):
        """Unsubscribe from a channel. Only removes if no active connections."""
        with self.lock:
            # Don't immediately remove - keep for potential reconnections
            # Channels will be cleaned up by a background task or timeout
            sse_logger.info(f"Unsubscribe called for channel: {channel_id} (keeping alive for reconnections)")
            pass

    def cleanup_channel(self, channel_id):
        """Explicitly remove a channel (called after payment success/failure)"""
        with self.lock:
            removed = self.channels.pop(channel_id, None)
            if removed:
                sse_logger.info(f"Cleaned up SSE channel: {channel_id}")

    def publish(self, channel_id, data):
        with self.lock:
            if channel_id in self.channels:
                try:
                    # Format data as a Server-Sent Event
                    message = f"data: {json.dumps(data)}\n\n"
                    self.channels[channel_id].put_nowait(message)
                    sse_logger.info(f"Published to SSE channel {channel_id}: {data.get('status')}")
                except queue.Full:
                    sse_logger.warning(f"SSE channel {channel_id} queue is full. Message dropped.")
            else:
                sse_logger.warning(f"Attempted to publish to non-existent channel: {channel_id}")

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
@limiter.limit("60 per minute")
def landing_page():
    creator = Creator.query.first()
    if not creator:
        # Redirect to admin setup if store is not initialized
        return redirect(url_for('admin.admin_home'))

    # Get query parameters for search and filter
    search_query = request.args.get('q', '').strip()
    filter_type = request.args.get('type', '').strip().upper()

    # Base query
    query = DigitalAsset.query.filter_by(status=AssetStatus.PUBLISHED)

    # Apply Search
    if search_query:
        query = query.filter(or_(
            DigitalAsset.title.ilike(f'%{search_query}%'),
            DigitalAsset.description.ilike(f'%{search_query}%')
        ))



    # Apply Type Filter
    if filter_type and filter_type in AssetType.__members__:
        query = query.filter(DigitalAsset.asset_type == AssetType[filter_type])

    # Fetch all matching assets
    all_assets = query.all()

    # Dynamic Filters: Find which types actually exist in the DB (for the tabs)
    # We query ALL published assets to determine available tabs, regardless of current search/filter
    available_types_query = db.session.query(DigitalAsset.asset_type).filter_by(status=AssetStatus.PUBLISHED).distinct()
    available_types = [row[0] for row in available_types_query]
    
    # Sort available types to match Enum order or custom order if needed
    # AssetType is an Enum, so we can sort by name or value if we want consistent ordering
    # Let's sort by the order they are defined in the Enum
    available_types.sort(key=lambda x: list(AssetType).index(x))

    # Get user's purchase history for "Unpurchased First" logic
    # Only consider the user "logged in" for this purpose if they are verified
    customer_phone = session.get('customer_phone') if session.get('is_verified') else None
    purchased_asset_ids = set()
    user_purchases = {} # Map asset_id -> status
    
    if customer_phone:
        customer = Customer.query.filter_by(whatsapp_number=customer_phone).first()
        if customer:
            purchases = Purchase.query.filter_by(customer_id=customer.id).all()
            for p in purchases:
                purchased_asset_ids.add(p.asset_id)
                # Store the most "advanced" status (COMPLETED > PENDING > FAILED)
                current_status = user_purchases.get(p.asset_id)
                if p.status == PurchaseStatus.COMPLETED:
                    user_purchases[p.asset_id] = 'COMPLETED'
                elif p.status == PurchaseStatus.PENDING and current_status != 'COMPLETED':
                    user_purchases[p.asset_id] = 'PENDING'
                elif p.status == PurchaseStatus.FAILED and current_status not in ['COMPLETED', 'PENDING']:
                    user_purchases[p.asset_id] = 'FAILED'

    # Smart Sorting Logic in Python (easier to handle complex custom weights)
    # Priority:
    # 1. Subscriptions (is_subscription=True)
    # 2. Unpurchased Items (not in purchased_asset_ids)
    # 3. Recency (created_at desc) - Assuming ID is a proxy for recency or added date
    
    def sort_key(asset):
        # Higher score = appears first
        score = 0
        
        # 1. Subscription Priority
        if asset.is_subscription:
            score += 1000
            
        # 2. Unpurchased Priority
        if asset.id not in purchased_asset_ids:
            score += 100
            
        # 3. Recency (using ID as proxy for now, assuming auto-increment)
        # Normalize ID to a small fraction to break ties without overriding main priorities
        score += (asset.id or 0) / 100000.0
        
        return score

    sorted_assets = sorted(all_assets, key=sort_key, reverse=True)

    # Check for "New" items (e.g., created in the last 7 days)
    # For now, we'll just mark the top 3 newest unpurchased items as "New" if we don't have created_at
    # If you have created_at, use: asset.created_at > datetime.now() - timedelta(days=7)
    new_asset_ids = set()
    # Simple heuristic: Top 3 sorted assets that are unpurchased are "New" / "Featured"
    count = 0
    for asset in sorted_assets:
        if asset.id not in purchased_asset_ids:
            new_asset_ids.add(asset.id)
            count += 1
            if count >= 3: break

    # --- Dynamic Metadata for Social Sharing ---
    # Use a random published asset to make social previews dynamic and engaging
    random_asset = DigitalAsset.query.filter_by(status=AssetStatus.PUBLISHED).order_by(func.random()).first()
    
    meta_title = creator.store_name or "Nyota ✨ Store"
    meta_description = creator.get_setting('store_bio') or f"Discover amazing digital content on {creator.store_name}."
    meta_image = url_for('static', filename='img/default-og.jpg', _external=True)
    
    if random_asset:
        # Build persuasive meta from random asset
        meta_title = f"{random_asset.title} | {creator.store_name}"
        
        # Create description with CTA
        desc_text = random_asset.description or ""
        if len(desc_text) > 140:
            desc_text = desc_text[:137] + "..."
        meta_description = f"{desc_text} 🛒 Get instant access at {creator.store_name}!"
        
        # Ensure absolute URL for image
        if random_asset.cover_image_url:
            if random_asset.cover_image_url.startswith('http'):
                meta_image = random_asset.cover_image_url
            else:
                # Relative URL - make it absolute
                meta_image = url_for('static', filename=random_asset.cover_image_url.lstrip('/'), _external=True)

    return render_template(
        'user/index.html',
        creator=creator,
        store_name=creator.store_name,
        assets=sorted_assets,
        user_purchases=user_purchases,
        new_asset_ids=new_asset_ids,
        search_query=search_query,
        filter_type=filter_type,
        available_types=available_types,
        meta_title=meta_title,
        meta_description=meta_description,
        meta_image=meta_image
    )

@main_bp.route('/set-language/<lang_code>')
def set_language(lang_code):
    if lang_code in ['en', 'sw']:
        session['language'] = lang_code
    return redirect(request.referrer or url_for('main.landing_page'))

@main_bp.route('/sitemap.xml')
def sitemap():
    """Generate dynamic XML sitemap for search engines"""
    from flask import make_response
    from datetime import datetime
    
    # Get all published assets
    assets = DigitalAsset.query.filter_by(status=AssetStatus.PUBLISHED).all()
    
    # Build sitemap XML
    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    # Landing page
    xml.append('  <url>')
    xml.append(f'    <loc>{url_for("main.landing_page", _external=True)}</loc>')
    xml.append('    <changefreq>daily</changefreq>')
    xml.append('    <priority>1.0</priority>')
    xml.append('  </url>')
    
    # All published assets
    for asset in assets:
        xml.append('  <url>')
        xml.append(f'    <loc>{url_for("main.asset_detail", slug=asset.slug, _external=True)}</loc>')
        if asset.updated_at:
            xml.append(f'    <lastmod>{asset.updated_at.strftime("%Y-%m-%d")}</lastmod>')
        xml.append('    <changefreq>weekly</changefreq>')
        xml.append('    <priority>0.8</priority>')
        xml.append('  </url>')
    
    xml.append('</urlset>')
    
    response = make_response('\n'.join(xml))
    response.headers['Content-Type'] = 'application/xml; charset=utf-8'
    return response

@main_bp.route('/robots.txt')
def robots():
    """Generate robots.txt to allow search engine indexing"""
    from flask import make_response
    
    txt = [
        'User-agent: *',
        'Allow: /',
        f'Sitemap: {url_for("main.sitemap", _external=True)}'
    ]
    
    response = make_response('\n'.join(txt))
    response.headers['Content-Type'] = 'text/plain; charset=utf-8'
    return response

@main_bp.route('/asset/<slug>')
@limiter.limit("60 per minute")
def asset_detail(slug):
    # Fetch asset without status filter first
    asset_obj = DigitalAsset.query.filter_by(slug=slug).first_or_404()
    
    # Permission Logic
    is_creator = 'creator_id' in session and session['creator_id'] == asset_obj.creator_id
    customer_phone = session.get('customer_phone')
    has_purchased = False
    
    if customer_phone:
        customer = Customer.query.filter_by(whatsapp_number=customer_phone).first()
        if customer:
            # Check for completed purchase logic
            has_purchased = Purchase.query.filter_by(
                customer_id=customer.id, 
                asset_id=asset_obj.id, 
                status=PurchaseStatus.COMPLETED
            ).first() is not None

    # Visibility Rules
    if asset_obj.status == AssetStatus.PUBLISHED:
        pass # Public
    elif asset_obj.status == AssetStatus.ARCHIVED:
        # Visible only to Owners (Purchasers) and Creator
        if not (has_purchased or is_creator):
            abort(404)
    else: # DRAFT or others
        # Visible only to Creator
        if not is_creator:
            abort(404)
            
    asset_json = json.dumps(asset_obj.to_dict(), default=json_serial)
    creator = Creator.query.get(asset_obj.creator_id)
    latest_purchase = None
    
    if customer_phone:
        customer = Customer.query.filter_by(whatsapp_number=customer_phone).first()
        if customer:
            # Re-query for latest purchase attempt (might be pending/failed)
            # We already checked purchase status for permission, but this logic
            # is used for the UI state (e.g. "Processing", "Buy Now")
            latest_purchase = Purchase.query.filter_by(
                customer_id=customer.id, 
                asset_id=asset_obj.id
            ).order_by(Purchase.purchase_date.desc()).first()

    # Metadata Generation
    store_name = creator.store_name if creator else "Creator Store"
    meta_title = f"{asset_obj.title} | {store_name}"
    # Ensure the meta image URL is absolute for social previews
    if asset_obj.cover_image_url:
        if asset_obj.cover_image_url.startswith('http'):
            meta_image = asset_obj.cover_image_url
        else:
            # Assume it's a static path relative to the static folder
            meta_image = url_for('static', filename=asset_obj.cover_image_url, _external=True)
        # Append a short random query string to bust caches on platforms
        import uuid
        meta_image = f"{meta_image}?v={uuid.uuid4().hex[:8]}"
    else:
        meta_image = url_for('static', filename='img/default-og.jpg', _external=True)
    
    # Description with persuasive CTA and price
    desc_text = asset_obj.description or ""
    if len(desc_text) > 130:
        desc_text = desc_text[:127] + "..."
    
    # Add price info for better conversion
    price_text = ""
    if asset_obj.is_subscription and asset_obj.details and asset_obj.details.get('subscription_tiers'):
        min_price = min(float(tier.get('price', 0)) for tier in asset_obj.details['subscription_tiers'])
        currency = creator.get_setting('payment_uza_currency', 'TZS')
        price_text = f" From {currency} {min_price:,.0f}/month."
    elif asset_obj.price:
        currency = creator.get_setting('payment_uza_currency', 'TZS')
        price_text = f" {currency} {float(asset_obj.price):,.0f}."
    
    meta_description = f"{desc_text}{price_text} 🚀 Get instant access at {store_name}!"

    return render_template(
        'user/asset_detail.html',
        asset=asset_obj,
        asset_obj=asset_obj,
        asset_json=asset_json,
        latest_purchase=latest_purchase, 
        store_name=store_name,
        meta_title=meta_title,
        meta_description=meta_description,
        meta_image=meta_image
    )

@main_bp.route('/checkout/<slug>')
def checkout(slug):
    asset = DigitalAsset.query.filter_by(slug=slug, status=AssetStatus.PUBLISHED).first_or_404()
    return render_template('user/checkout.html', asset=asset.to_dict(), channel_id=str(uuid.uuid4()))

@main_bp.route('/api/initiate-payment', methods=['POST'])
@limiter.limit("10 per minute")
def initiate_payment():
    """
    Handles the initial payment request from a customer's browser.
    Creates a pending purchase record and calls the UZA payment gateway API.
    """
    data = request.get_json()
    phone_number = str(data.get('phone_number', '')).strip() # Cast to string and strip
    asset_id = data.get('asset_id')
    channel_id = data.get('channel_id') # The unique ID for the user's browser tab

    # 1. Validate incoming data
    if not all([phone_number, asset_id, channel_id]):
        return jsonify({'success': False, 'message': 'Missing required data.'}), 400
    
    tier = data.get('tier')  # Extract selected tier

    asset = DigitalAsset.query.get_or_404(asset_id)
    
    # Determine price based on tier
    amount = asset.price
    ticket_data = {}
    
    if tier:
        # Get tier price and validate it
        tier_price = tier.get('price')
        if tier_price is None or tier_price == '' or (isinstance(tier_price, str) and not str(tier_price).strip()):
            # Fallback to asset price if tier price is invalid
            amount = asset.price
        else:
            try:
                # Convert to Decimal, handling both string and numeric inputs
                amount = decimal.Decimal(str(tier_price).strip())
                ticket_data['tier'] = tier # Only set tier data if price is valid
            except (decimal.InvalidOperation, ValueError):
                # If conversion fails, use asset price as fallback
                amount = asset.price
    
            
    # Create a pending purchase
    customer = Customer.query.filter_by(whatsapp_number=phone_number).first()
    if not customer:
        customer = Customer(whatsapp_number=phone_number)
        db.session.add(customer)
        db.session.flush() # Flush to get customer.id if it's a new customer

    purchase = Purchase(
        customer_id=customer.id,
        asset_id=asset.id,
        amount_paid=amount,
        status=PurchaseStatus.PENDING,
        sse_channel_id=channel_id,
        ticket_data=ticket_data if ticket_data else None
    )
    db.session.add(purchase)
    db.session.commit()

    creator = asset.creator
    uza_pk = creator.get_setting('payment_uza_pk')
    if not uza_pk:
        current_app.logger.error(f"UZA Payment for creator {creator.id} failed: Public Key (PK) not configured.")
        return jsonify({'success': False, 'message': 'This store is not configured to accept payments.'}), 500
    
    # Store the customer's phone in the session for library access later
    # BUT mark as unverified until payment is successful
    
    # CRITICAL FIX: If the user is changing numbers (e.g. paying for someone else or fixing a typo),
    # we MUST ensure the session is completely effectively checking out the old user and checking in the new one.
    # We remove old keys to prevent any "verified" state from leaking.
    if session.get('customer_phone') and str(session.get('customer_phone')).strip() != str(phone_number).strip():
        session.pop('customer_phone', None)
        session.pop('is_verified', None)
        
    session['customer_phone'] = str(phone_number).strip()
    session['is_verified'] = False
    session.permanent = True # Ensure cookie persists across requests
    session.modified = True

    
    # Determine which UZA Product ID to use
    # Priority: 1. Tier's UZA Product ID, 2. Asset's UZA Product ID, 3. Default fallback ID
    uza_product_id = None
    if tier and tier.get('uza_product_id'):
        uza_product_id_str = str(tier.get('uza_product_id')).strip()
        if uza_product_id_str:
            try:
                uza_product_id = int(uza_product_id_str)
            except (ValueError, TypeError):
                current_app.logger.warning(f"Invalid tier UZA Product ID: {uza_product_id_str}")
    
    if not uza_product_id and asset.details and asset.details.get('uza_product_id'):
        uza_product_id_str = str(asset.details.get('uza_product_id')).strip()
        if uza_product_id_str:
            try:
                uza_product_id = int(uza_product_id_str)
            except (ValueError, TypeError):
                current_app.logger.warning(f"Invalid asset UZA Product ID: {uza_product_id_str}")
    
    # If no UZA Product ID is configured, use a default/placeholder
    if not uza_product_id:
        uza_product_id = 8069  # Default fallback ID
    
    # 4. Construct the payload for the UZA API
    uza_payload = {
        "products": [{"id": uza_product_id, "name": asset.title, "quantity": 1, "price": float(amount)}],
        "payment": {"type": "payby.selcom", "walletid": phone_number},
        "reference": purchase.transaction_token, # Our internal unique ID
        "pk": uza_pk,
        "totalAmount": str(amount),
        "currency": creator.get_setting('payment_uza_currency', 'TZS'),
        "meta": {
            "refcode": creator.get_setting('payment_uza_refcode', '#web'), 
            "source": creator.get_setting('payment_uza_source', '#nyota')
        }
    }
    
    # Log the request payload for debugging
    current_app.logger.info(f"UZA API Request Payload: {json.dumps(uza_payload, indent=2)}")

    # 5. Call the UZA API and handle the response
    try:
        response = requests.post("https://uza.co.tz/api/interface/embeddable/order", json=uza_payload, timeout=30)
        
        # Log response for debugging
        current_app.logger.info(f"UZA API Response Status: {response.status_code}")
        current_app.logger.info(f"UZA API Response Body: {response.text}")
        
        response.raise_for_status() # Raise an exception for HTTP error codes (4xx or 5xx)
        response_data = response.json()
        
        if 'data' in response_data and 'order' in response_data['data']:
            # Capture the `deal_id` from UZA's successful response
            uza_deal_id = response_data['data']['order'].get('id')
            if not uza_deal_id:
                raise Exception("UZA API response did not contain a 'deal_id'.")

            # Link our purchase record to UZA's deal_id
            purchase.payment_gateway_ref = uza_deal_id
            db.session.commit()

            # Respond to the user's browser
            return jsonify({
                'success': True,
                'message': response_data['data']['order'].get('payment_message', 'Check your phone to complete payment.'),
                'purchase_id': purchase.id,
                'deal_id': uza_deal_id
            })
        else: 
            # Handle cases where UZA returns a 200 OK but with an error message
            raise Exception(response_data.get('message', 'Unknown UZA API error'))

    except Exception as e:
        # If the API call fails, mark our purchase record as FAILED
        purchase.status = PurchaseStatus.FAILED
        db.session.commit()
        current_app.logger.error(f"UZA API call failed for transaction {purchase.transaction_token}: {e}")
        return jsonify({'success': False, 'message': 'Could not connect to the payment provider. Please try again.'}), 500

@main_bp.route('/api/retry-payment', methods=['POST'])
@limiter.limit("10 per minute")
def retry_payment():
    """
    Handles retrying a payment for an existing FAILED or PENDING purchase
    using the deal_id from the frontend.
    """
    data = request.get_json()
    deal_id = data.get('deal_id')
    new_phone_number = data.get('phone_number')
    purchase_id = data.get('purchase_id') # To find the purchase record

    if not all([deal_id, new_phone_number, purchase_id]):
        return jsonify({'success': False, 'message': 'Missing data for retry.'}), 400

    purchase = Purchase.query.get(purchase_id)
    if not purchase: 
        return jsonify({'success': False, 'message': 'Original purchase not found.'}), 404

    creator = purchase.asset.creator
    uza_pk = creator.get_setting('payment_uza_pk')
    if not uza_pk: 
        return jsonify({'success': False, 'message': 'Payment provider not configured.'}), 500
    
    # Reset status to PENDING
    purchase.status = PurchaseStatus.PENDING
    db.session.commit()
    
    uza_payload = {
        "pk": uza_pk,
        "payment_method_id": "payby.selcom",
        "deal_id": deal_id,
        "email": f"{deal_id}@uza.co.tz",
        "walletid": new_phone_number # UZA API might need this for the new push
    }

    try:
        response = requests.put("https://uza.co.tz/api/interface/embeddable/retry-payment", json=uza_payload, timeout=30)
        response.raise_for_status()
        
        # Update the session with the new number
        session['customer_phone'] = new_phone_number
        
        return jsonify({'success': True, 'message': 'New payment request sent! Check your phone.'})

    except Exception as e:
        purchase.status = PurchaseStatus.FAILED
        db.session.commit()
        current_app.logger.error(f"UZA Retry failed: {e}")
        return jsonify({'success': False, 'message': 'Could not retry payment.'}), 500

@main_bp.route('/api/payment-status/<int:purchase_id>', methods=['GET'])
@limiter.limit("10 per minute")
def payment_status(purchase_id):
    """
    Polling endpoint to check the status of a payment.
    Used as a fallback when SSE fails or times out.
    """
    purchase = Purchase.query.get_or_404(purchase_id)
    
    # Security: 
    # 1. If user is strictly logged in, phone must match.
    # 2. If user is in "pending payment" state (unverified session), phone must match session.
    # 3. If session has no phone, we might technically deny, BUT for better UX on same-device flow,
    #    we could allow if the purchase is very recent (e.g. < 10 mins) to support "lost session" edge cases,
    #    but that's risky. Let's stick to session phone matching.
    
    session_phone = session.get('customer_phone')
    
    if not session_phone:
        # Edge case: If session is empty, but we are polling a valid purchase ID. 
        # For security, we return 403. The frontend should have the cookie.
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    if not purchase.customer or str(purchase.customer.whatsapp_number).strip() != str(session_phone).strip():
        # Strict check: Phone in session MUST match phone on purchase
        return jsonify({'success': False, 'message': 'Unauthorized owner'}), 403
    
    # Return the current status
    redirect_url = None
    if purchase.status == PurchaseStatus.COMPLETED:
         redirect_url = url_for('main.finalize_session', purchase_id=purchase.id)

    return jsonify({
        'success': True,
        'status': purchase.status.name,
        'redirect_url': redirect_url
    })



@main_bp.route('/api/uza-callback', methods=['POST'])
def uza_payment_callback():
    """
    Handles the asynchronous payment confirmation webhook from UZA.
    This endpoint is stateless and must be publicly accessible.
    """
    data = request.get_json()
    
    # 0. Security Check: Verify the callback secret
    # We fetch the creator (assuming single tenant/admin for now)
    creator = Creator.query.first()
    if creator:
        expected_secret = creator.get_setting('payment_uza_secret')
        if expected_secret:
            # If a secret is configured, we MUST verify it.
            incoming_secret = request.args.get('secret')
            if not incoming_secret or incoming_secret != expected_secret:
                current_app.logger.warning(f"UZA Callback: Invalid or missing secret. Expected verification.")
                return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
        else:
            # If no secret is configured, we log a warning but allow it (legacy mode)
            # OR we could reject it. Given the user's request to "secure" it, 
            # we should encourage setting it. For now, we'll log.
            current_app.logger.warning("UZA Callback: No secret configured in settings. Endpoint is insecure.")
    
    # 1. Basic validation of the incoming payload
    if not data or 'data' not in data:
        current_app.logger.error("UZA Callback: Received an invalid or empty JSON payload.")
        return jsonify({'status': 'error', 'message': 'Invalid payload'}), 400

    # 2. Extract the `deal_id` which is our primary key for this transaction
    uza_deal_id = data['data'].get('deal_id')
    if not uza_deal_id:
        current_app.logger.error("UZA Callback: Payload received without a 'deal_id'.")
        return jsonify({'status': 'error', 'message': 'Missing deal_id'}), 400
        
    # Note: The UZA callback for a successful transaction might not contain a 'status' field.
    # We will assume a valid callback to this endpoint implies success unless UZA documentation specifies otherwise.
    # If UZA sends different callbacks for success/failure, you would add an if/else here.

    # 3. Find the original purchase record using the `deal_id`
    purchase = Purchase.query.filter_by(payment_gateway_ref=uza_deal_id).first()
    if not purchase:
        current_app.logger.error(f"UZA Callback: Received callback for an unknown deal_id: {uza_deal_id}")
        return jsonify({'status': 'error', 'message': 'Transaction not found'}), 404
        
    # 4. Idempotency check: If we've already processed this, don't do it again.
    if purchase.status == PurchaseStatus.COMPLETED:
        current_app.logger.info(f"UZA Callback: Received duplicate success callback for already completed deal_id: {uza_deal_id}")
        return jsonify({'status': 'ok', 'message': 'Transaction already processed'}), 200

    # 5. Update our database records
    try:
        purchase.status = PurchaseStatus.COMPLETED
        
        # Update the asset's performance statistics
        asset = purchase.asset
        asset.total_sales = (asset.total_sales or 0) + 1
        asset.total_revenue = (asset.total_revenue or 0) + purchase.amount_paid
        
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"DB Error processing UZA callback for deal_id {uza_deal_id}: {e}")
        return jsonify({'status': 'error', 'message': 'Database processing failed'}), 500

    # 6. Bridge to the frontend: Notify the waiting browser via Server-Sent Events
    if purchase.sse_channel_id:
        sse_manager.publish(purchase.sse_channel_id, {
            'status': 'SUCCESS', 
            'message': 'Payment confirmed! Accessing your content...',
            'redirect_url': url_for('main.finalize_session', purchase_id=purchase.id) 
        })
        current_app.logger.info(f"Successfully processed payment for deal_id {uza_deal_id} and notified SSE channel {purchase.sse_channel_id}")
        
        # Cleanup the channel now that we're done
        sse_manager.cleanup_channel(purchase.sse_channel_id)
    else:
        # This is not a fatal error, but it's important to log for debugging.
        current_app.logger.warning(f"Payment for deal_id {uza_deal_id} was successful, but no SSE channel was found to notify the user's browser.")

    # 7. Acknowledge receipt to UZA's servers
    return jsonify({'status': 'ok', 'message': 'Payment processed successfully'}), 200


# DEPRECATED: Session recovery is now unified in the /library route
# Users provide phone + date directly on the library page
@main_bp.route('/access/verify', methods=['GET', 'POST'])
def session_recovery():
    """
    DEPRECATED: Redirect to library page.
    Session recovery is now handled directly on /library with phone + date.
    """
    return redirect(url_for('main.library'))

    
    # POST: Process verification attempt
    phone_suffix = request.form.get('phone_suffix', '').strip()
    purchase_date_str = request.form.get('purchase_date', '').strip()
    
    # Get requester IP
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ',' in ip_address:
        ip_address = ip_address.split(',')[0].strip()
    
    # Rate limiting check
    fifteen_min_ago = datetime.utcnow() - timedelta(minutes=15)
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    
    # Count recent failed attempts from this IP
    recent_failures = AccessAttempt.query.filter(
        AccessAttempt.ip_address == ip_address,
        AccessAttempt.success == False,
        AccessAttempt.attempt_time >= fifteen_min_ago
    ).count()
    
    hourly_failures = AccessAttempt.query.filter(
        AccessAttempt.ip_address == ip_address,
        AccessAttempt.success == False,
        AccessAttempt.attempt_time >= one_hour_ago
    ).count()
    
    # Apply throttling
    if recent_failures >= 3:
        return render_template('user/session_recovery.html', 
                             error='Too many failed attempts. Please wait 15 minutes.',
                             throttled=True), 429
    
    if hourly_failures >= 10:
        return render_template('user/session_recovery.html',
                             error='Too many failed attempts. Please wait 1 hour.',
                             throttled=True), 429
    
    # Validate input
    if not phone_suffix or len(phone_suffix) != 4 or not phone_suffix.isdigit():
        # Log failed attempt
        attempt = AccessAttempt(ip_address=ip_address, phone_suffix=phone_suffix[:4] if phone_suffix else '0000', success=False)
        db.session.add(attempt)
        db.session.commit()
        return render_template('user/session_recovery.html',
                             error='Please enter the last 4 digits of your phone number.')
    
    # Validate date format (YYYY-MM-DD)
    try:
        purchase_date = datetime.strptime(purchase_date_str, '%Y-%m-%d').date()
    except ValueError:
        attempt = AccessAttempt(ip_address=ip_address, phone_suffix=phone_suffix, success=False)
        db.session.add(attempt)
        db.session.commit()
        return render_template('user/session_recovery.html',
                             error='Please enter a valid date (YYYY-MM-DD).')
    
    # Search for matching purchase
    # Match: phone ends with suffix AND purchase was made on the specified date
    matching_purchases = Purchase.query.join(Customer).filter(
        Customer.whatsapp_number.like(f'%{phone_suffix}'),
        func.date(Purchase.purchase_date) == purchase_date,
        Purchase.status == PurchaseStatus.COMPLETED
    ).all()
    
    if not matching_purchases:
        # Log failed attempt
        attempt = AccessAttempt(ip_address=ip_address, phone_suffix=phone_suffix, success=False)
        db.session.add(attempt)
        db.session.commit()
        
        return render_template('user/session_recovery.html',
                             error='No matching purchase found. Please check your phone number and date.')
    
    # Success! Create session
    customer = matching_purchases[0].customer
    session.permanent = True
    session['customer_phone'] = customer.whatsapp_number
    session['customer_id'] = customer.id
    
    # Log successful attempt
    attempt = AccessAttempt(ip_address=ip_address, phone_suffix=phone_suffix, success=True)
    db.session.add(attempt)
    db.session.commit()
    
    flash('Access restored! Welcome back.', 'success')
    return redirect(url_for('main.library'))




@main_bp.route('/api/payment-stream/<channel_id>')
def payment_stream(channel_id):
    """
    Server-Sent Events endpoint for payment status updates.
    Supports reconnection - channels persist across multiple connections.
    Maintains an indefinite connection with heartbeats.
    """
    def event_stream():
        q = sse_manager.subscribe(channel_id)
        sse_logger.info(f"SSE connection started for channel {channel_id}")
        
        try:
            while True:
                try:
                    # Wait for a message with a short timeout to allow for heartbeats
                    # This blocks for up to 5 seconds
                    message = q.get(timeout=5)
                    yield message
                    
                    # If we sent a terminal status, we can stop the stream
                    if "SUCCESS" in message or "FAILED" in message:
                        sse_logger.info(f"Terminal event sent for {channel_id}, closing stream")
                        break
                        
                except queue.Empty:
                    # No message received in 5 seconds, send a heartbeat
                    # Comments (starting with :) keep the connection alive without triggering onmessage
                    yield f": heartbeat\n\n"
                    
        except GeneratorExit:
            # Client disconnected
            sse_logger.info(f"Client disconnected from SSE channel {channel_id}")
        except Exception as e:
            sse_logger.error(f"SSE error for channel {channel_id}: {e}")
        finally:
            # Don't unsubscribe - channel stays alive for reconnections
            # Only explicitly cleanup on payment success/failure via callback
            sse_logger.info(f"SSE connection closed for channel {channel_id}, but channel remains active")

    return Response(event_stream(), mimetype='text/event-stream')
    
@main_bp.route('/library', methods=['GET', 'POST'])
def library():
    customer_phone = session.get('customer_phone')
    # Library access logic:
    # - If customer_phone exists in session (even if not verified), allow access
    # - This supports users who just paid and are awaiting confirmation
    # - They can see their library (which may contain pending purchases)
    # - Verification is only required for the POST route (login without payment)
    
    if request.method == 'POST':
        # Get form data
        form_phone = request.form.get('phone_number', '').strip()
        purchase_date_str = request.form.get('purchase_date', '').strip()
        
        # Get requester IP for rate limiting
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ',' in ip_address:
            ip_address = ip_address.split(',')[0].strip()
        
        # Rate limiting check
        fifteen_min_ago = datetime.utcnow() - timedelta(minutes=15)
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        recent_failures = AccessAttempt.query.filter(
            AccessAttempt.ip_address == ip_address,
            AccessAttempt.success == False,
            AccessAttempt.attempt_time >= fifteen_min_ago
        ).count()
        
        hourly_failures = AccessAttempt.query.filter(
            AccessAttempt.ip_address == ip_address,
            AccessAttempt.success == False,
            AccessAttempt.attempt_time >= one_hour_ago
        ).count()
        
        # Apply throttling
        if recent_failures >= 3:
            flash('Too many failed attempts. Please wait 15 minutes.', 'error')
            return render_template('user/library.html', customer_phone=None, purchases=[], 
                                 store_name=Creator.query.first().store_name if Creator.query.first() else "Nyota",
                                 currency_symbol='TZS', throttled=True), 429
        
        if hourly_failures >= 10:
            flash('Too many failed attempts. Please wait 1 hour.', 'error')
            return render_template('user/library.html', customer_phone=None, purchases=[],
                                 store_name=Creator.query.first().store_name if Creator.query.first() else "Nyota",
                                 currency_symbol='TZS', throttled=True), 429
        
        # Validate both fields are provided
        if not form_phone or not purchase_date_str:
            flash('Please enter both your phone number and purchase date.', 'error')
            return redirect(url_for('main.library'))
        
        # Validate date format
        try:
            purchase_date = datetime.strptime(purchase_date_str, '%Y-%m-%d').date()
        except ValueError:
            # Log failed attempt
            phone_suffix = form_phone[-4:] if len(form_phone) >= 4 else '0000'
            attempt = AccessAttempt(ip_address=ip_address, phone_suffix=phone_suffix, success=False)
            db.session.add(attempt)
            db.session.commit()
            flash('Please enter a valid purchase date.', 'error')
            return redirect(url_for('main.library'))
        
        # Search for matching customer and purchase
        matching_purchases = Purchase.query.join(Customer).filter(
            Customer.whatsapp_number == form_phone,
            func.date(Purchase.purchase_date) == purchase_date,
            Purchase.status == PurchaseStatus.COMPLETED
        ).all()
        
        if not matching_purchases:
            # Log failed attempt
            phone_suffix = form_phone[-4:] if len(form_phone) >= 4 else '0000'
            attempt = AccessAttempt(ip_address=ip_address, phone_suffix=phone_suffix, success=False)
            db.session.add(attempt)
            db.session.commit()
            flash('No purchase found with this phone number and date. Please check your details.', 'error')
            return redirect(url_for('main.library'))
        
        # Success! Create session
        phone_suffix = form_phone[-4:] if len(form_phone) >= 4 else '0000'
        attempt = AccessAttempt(ip_address=ip_address, phone_suffix=phone_suffix, success=True)
        db.session.add(attempt)
        
        session.permanent = True
        session['customer_phone'] = form_phone
        session['customer_id'] = matching_purchases[0].customer_id
        session['is_verified'] = True # Grant full access
        db.session.commit()
        
        flash('Access granted! Welcome to your library.', 'success')
        return redirect(url_for('main.library'))

    purchases = []
    purchases_data = []
    if customer_phone:
        customer = Customer.query.filter_by(whatsapp_number=customer_phone).first()
        if customer:
            purchases = Purchase.query.filter_by(customer_id=customer.id).order_by(Purchase.purchase_date.desc()).all()
            # Serialize purchases with asset data
            for purchase in purchases:
                # Skip purchases with deleted/orphaned assets
                if not purchase.asset:
                    continue
                    
                is_active = True
                expiry_date = None
                if purchase.asset.is_subscription:
                    is_active, expiry_date = check_subscription_status(purchase)
                
                purchases_data.append({
                    'id': purchase.id,
                    'status': purchase.status.name,
                    'purchase_date': purchase.purchase_date.isoformat(),
                    'asset': {
                        'title': purchase.asset.title,
                        'slug': purchase.asset.slug,
                        'cover_image_url': purchase.asset.cover_image_url,
                        'description': purchase.asset.description,
                        'asset_type': purchase.asset.asset_type.name
                    },
                    'subscription': {
                        'is_active': is_active,
                        'expiry_date': expiry_date.isoformat() if expiry_date else None
                    } if purchase.asset.is_subscription else None
                })
    
    creator = Creator.query.first()
    return render_template(
        'user/library.html',
        customer_phone=customer_phone,
        purchases=purchases_data,
        store_name=creator.store_name if creator else "Nyota Store",
        currency_symbol=creator.get_setting('currency_symbol', 'TZS') if creator else "TZS",
        today_date=datetime.utcnow().strftime('%Y-%m-%d')
    )

@main_bp.route('/logout')
def logout():
    """Logs out the customer by clearing their phone from the session."""
    session.pop('customer_phone', None)
    session.pop('is_verified', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('main.library'))

@main_bp.route('/auth/finalize-session/<int:purchase_id>')
def finalize_session(purchase_id):
    """
    Route hit after successful payment to upgrade the session to 'verified'.
    """
    purchase = Purchase.query.get_or_404(purchase_id)
    
    # Security check: Ensure the session phone matches the purchase phone
    # This prevents someone from just guessing purchase IDs to verify a random session
    session_phone = session.get('customer_phone')
    if not session_phone or not purchase.customer or purchase.customer.whatsapp_number != session_phone:
        flash("Session mismatch. Please log in again.", "error")
        return redirect(url_for('main.library'))

    if purchase.status == PurchaseStatus.COMPLETED:
        session['is_verified'] = True
        session.permanent = True
        flash("Payment successful! Welcome to your library.", "success")
        return redirect(url_for('main.library'))
    else:
        flash("Payment not yet confirmed. Please wait or check your phone.", "warning")
        return redirect(url_for('main.asset_detail', slug=purchase.asset.slug))

@main_bp.route('/api/cancel-payment', methods=['POST'])
def cancel_payment():
    """
    Clears the unverified session data when a user cancels a pending payment.
    """
    # Only clear if not verified (to avoid logging out a valid user who just clicked cancel on a new purchase)
    if not session.get('is_verified'):
        session.pop('customer_phone', None)
        session.pop('customer_id', None)
        return jsonify({'success': True, 'message': 'Payment cancelled and session cleared.'})
    
    return jsonify({'success': True, 'message': 'Payment cancelled.'})