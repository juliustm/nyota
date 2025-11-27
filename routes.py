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
from werkzeug.utils import secure_filename
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import func # Added func import

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, session, g,
    jsonify, current_app, Response, send_from_directory, abort
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
        activity=recent_activity
    )

@admin_bp.route('/assets')
@creator_login_required
def list_assets():
    creator_assets = DigitalAsset.query.filter_by(creator_id=g.creator.id).order_by(DigitalAsset.updated_at.desc()).all()
    assets_data = [{'id': a.id, 'title': a.title, 'description': a.description, 'cover': a.cover_image_url, 'type': a.asset_type.name, 'status': a.status.value, 'sales': a.total_sales, 'revenue': float(a.total_revenue), 'updated_at': a.updated_at} for a in creator_assets]
    return render_template('admin/assets.html', assets=json.dumps(assets_data, default=json_serial))

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
        return redirect(url_for('admin.list_assets'))
        
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
    if not customer_phone:
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
    
    # Handle Subscription Tiers
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
        supporters=json.dumps(supporters_data, default=json_serial)
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
            'payment_uza_enabled', 'payment_uza_pk', 'payment_uza_refcode', 'payment_uza_source', 'payment_uza_currency',
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
            if ('token' in key or 'pass' in key or '_sk' in key or '_pk' in key) and not value:
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
    )

@main_bp.route('/set-language/<lang_code>')
def set_language(lang_code):
    if lang_code in ['en', 'sw']:
        session['language'] = lang_code
    return redirect(request.referrer or url_for('main.landing_page'))

@main_bp.route('/asset/<slug>')
def asset_detail(slug):
    asset_obj = DigitalAsset.query.filter_by(slug=slug, status=AssetStatus.PUBLISHED).first_or_404()
    asset_json = json.dumps(asset_obj.to_dict(), default=json_serial)
    creator = Creator.query.get(asset_obj.creator_id)
    latest_purchase = None
    customer_phone = session.get('customer_phone')
    if customer_phone:
        customer = Customer.query.filter_by(whatsapp_number=customer_phone).first()
        if customer:
            # Find the most recent purchase attempt for this asset by this customer
            latest_purchase = Purchase.query.filter_by(
                customer_id=customer.id, 
                asset_id=asset_obj.id
            ).order_by(Purchase.purchase_date.desc()).first()

    return render_template(
        'user/asset_detail.html',
        asset_obj=asset_obj,
        asset_json=asset_json,
        latest_purchase=latest_purchase, 
        store_name=creator.store_name if creator else "Creator Store"
    )

@main_bp.route('/checkout/<slug>')
def checkout(slug):
    asset = DigitalAsset.query.filter_by(slug=slug, status=AssetStatus.PUBLISHED).first_or_404()
    return render_template('user/checkout.html', asset=asset.to_dict(), channel_id=str(uuid.uuid4()))

@main_bp.route('/api/initiate-payment', methods=['POST'])
def initiate_payment():
    """
    Handles the initial payment request from a customer's browser.
    Creates a pending purchase record and calls the UZA payment gateway API.
    """
    data = request.get_json()
    phone_number = data.get('phone_number')
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
    session['customer_phone'] = phone_number
    
    # 4. Construct the payload for the UZA API
    uza_payload = {
        "products": [{"id": 8069, "name": asset.title, "quantity": 1, "price": float(amount)}],
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

    # 5. Call the UZA API and handle the response
    try:
        response = requests.post("https://uza.co.tz/api/interface/embeddable/order", json=uza_payload, timeout=30)
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


@main_bp.route('/api/uza-callback', methods=['POST'])
def uza_payment_callback():
    """
    Handles the asynchronous payment confirmation webhook from UZA.
    This endpoint is stateless and must be publicly accessible.
    """
    data = request.get_json()
    
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
            'redirect_url': url_for('main.library') 
        })
        current_app.logger.info(f"Successfully processed payment for deal_id {uza_deal_id} and notified SSE channel {purchase.sse_channel_id}")
    else:
        # This is not a fatal error, but it's important to log for debugging.
        current_app.logger.warning(f"Payment for deal_id {uza_deal_id} was successful, but no SSE channel was found to notify the user's browser.")

    # 7. Acknowledge receipt to UZA's servers
    return jsonify({'status': 'ok', 'message': 'Callback processed successfully'}), 200

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
        currency_symbol=creator.get_setting('currency_symbol', 'TZS') if creator else "TZS"
    )

@main_bp.route('/logout')
def logout():
    """Logs out the customer by clearing their phone from the session."""
    session.pop('customer_phone', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('main.library'))