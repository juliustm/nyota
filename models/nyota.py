# models/nyota.py

"""
nyota.py

This file defines the entire database schema for the Nyota ✨ application using SQLAlchemy.
It is the single source of truth for all data structures, combining a comprehensive feature set
with a professional, scalable model for creator settings and preferences.
"""

import enum
import uuid
from datetime import datetime
from slugify import slugify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy.types import JSON

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()

# --- Enums for Standardized Field Choices ---
# (These enums are unchanged as they are solid)
class AssetType(enum.Enum):
    VIDEO_SERIES = "Video Course"
    TICKET = "Event & Webinar"
    DIGITAL_PRODUCT = "Digital Product"
    SUBSCRIPTION = "Subscription"
    NEWSLETTER = "Newsletter"

class AssetStatus(enum.Enum):
    DRAFT = "Draft"
    PUBLISHED = "Published"
    ARCHIVED = "Archived"

class SubscriptionInterval(enum.Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"

class SubscriptionStatus(enum.Enum):
    ACTIVE = "active"
    CANCELED = "canceled"
    PAST_DUE = "past_due"

class TicketStatus(enum.Enum):
    VALID = "valid"
    USED = "used"
    EXPIRED = "expired"

class PurchaseStatus(enum.Enum):
    PENDING = "Pending"
    COMPLETED = "Completed"
    FAILED = "Failed"

class CreatorSetting(db.Model):
    """
    A scalable, key-value store for all creator-specific settings.
    This prevents bloating the Creator model and avoids future database migrations
    when adding new settings. Each creator will have multiple rows in this table.
    """
    __tablename__ = 'creator_setting'
    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('creator.id'), nullable=False, index=True)
    key = db.Column(db.String(128), nullable=False, index=True)
    value = db.Column(JSON, nullable=True)

    __table_args__ = (db.UniqueConstraint('creator_id', 'key', name='_creator_key_uc'),)

    def __repr__(self):
        return f'<CreatorSetting {self.creator_id} - {self.key}>'

# ==============================================================================
# == OFFICIAL SETTINGS KEYS REFERENCE
# ==============================================================================
# This comment block serves as the definitive reference for all keys stored in the CreatorSetting table.
# It directly maps to the fields in the `admin/settings.html` template.
#
# --- Store Profile ---
# 'store_logo_url': (string) URL to the store's logo
# 'store_bio': (string) The creator's public biography
# 'social_twitter': (string) Full URL to Twitter profile
# 'social_instagram': (string) Full URL to Instagram profile
# 'contact_email': (string) Public contact email
# 'contact_phone': (string) Public contact phone number
#
# --- Appearance ---
# 'appearance_storefront_theme': (string) "modern", "classic", or "minimal"
#
# --- Integrations: Notifications ---
# 'telegram_enabled': (boolean)
# 'telegram_bot_token': (string) Encrypted API token for Telegram
# 'telegram_chat_id': (string)
# 'telegram_notify_payments': (boolean)
# 'telegram_notify_ratings': (boolean)
# 'telegram_notify_comments': (boolean)
#
# 'whatsapp_enabled': (boolean)
# 'whatsapp_phone_id': (string)
# 'whatsapp_access_token': (string) Encrypted token
#
# 'sms_provider': (string) "none", "twilio", "beem"
# 'sms_twilio_sid': (string)
# 'sms_twilio_token': (string) Encrypted token
# 'sms_twilio_phone': (string)
# 'sms_beem_api_key': (string)

# 'sms_beem_secret_key': (string) Encrypted key
# 'sms_beem_sender_name': (string)
#
# --- Integrations: Payments ---
# 'payment_stripe_enabled': (boolean)
# 'payment_stripe_pk': (string) Stripe Publishable Key
# 'payment_stripe_sk': (string) Encrypted Stripe Secret Key
# 'payment_paypal_enabled': (boolean)
# 'payment_paypal_client_id': (string)
# 'payment_paypal_secret': (string) Encrypted secret
#
# --- Integrations: AI & Automation ---
# 'ai_enabled': (boolean)
# 'ai_provider': (string) "groq", "openai", "anthropic", "local"
# 'ai_api_key': (string) Encrypted API key for the selected provider
# 'ai_model': (string) Specific model name, e.g., "llama3-8b-8192"
# 'ai_temperature': (float) 0.0 to 1.0
# 'ai_feature_content_suggestions': (boolean)
# 'ai_feature_seo_optimization': (boolean)
# 'ai_feature_email_templates': (boolean)
# 'ai_feature_smart_analytics': (boolean)
#
# --- Integrations: Social Media ---
# 'social_instagram_connected': (boolean)
# 'social_instagram_ai_enabled': (boolean)
# 'social_instagram_keywords': (string) Comma-separated list
# 'social_instagram_response_delay': (integer) Delay in minutes
# 'social_instagram_ai_personality': (string) "friendly", "professional", etc.
#
# --- Integrations: Productivity ---
# 'productivity_google_connected': (boolean)
# 'productivity_google_calendar_id': (string)
# 'productivity_google_sync_events': (boolean)
# 'productivity_google_send_reminders': (boolean)
# 'productivity_google_check_conflicts': (boolean)
#
# --- Integrations: Email Delivery ---
# 'email_smtp_enabled': (boolean)
# 'email_smtp_host': (string)
# 'email_smtp_port': (integer)
# 'email_smtp_user': (string)
# 'email_smtp_pass': (string) Encrypted password
# 'email_smtp_encryption': (string) "tls", "ssl", "none"
# 'email_smtp_sender_email': (string)
# 'email_smtp_sender_name': (string)
# ==============================================================================

# --- Core Models ---

class Creator(db.Model):
    """
    Represents the Creator/Admin. Core identity fields are here.
    All preferences and configurations are now handled by the CreatorSetting model
    for scalability and maintainability.
    """
    __tablename__ = 'creator'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    totp_secret = db.Column(db.String(32), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Core store properties that are fundamental, not just settings
    store_name = db.Column(db.String(120), default="My Digital Store")
    store_handle = db.Column(db.String(80), unique=True, nullable=True)

    # Relationships
    assets = db.relationship('DigitalAsset', back_populates='creator', lazy='dynamic')
    settings = db.relationship('CreatorSetting', cascade="all, delete-orphan", lazy='dynamic')
    
    def get_setting(self, key, default=None):
        """
        Convenience method to retrieve a setting value for this creator.
        Example Usage: g.creator.get_setting('telegram_bot_token')
        """
        setting = self.settings.filter_by(key=key).first()
        return setting.value if setting else default

    def set_setting(self, key, value):
        """
        Convenience method to set or update a setting for this creator.
        Example Usage: g.creator.set_setting('telegram_bot_token', 'new_token')
        """
        setting = self.settings.filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            setting = CreatorSetting(creator_id=self.id, key=key, value=value)
            db.session.add(setting)

    def __repr__(self):
        return f'<Creator {self.username}>'

class Customer(db.Model):
    """Unchanged from your robust original design."""
    __tablename__ = 'customer'
    id = db.Column(db.Integer, primary_key=True)
    whatsapp_number = db.Column(db.String(25), unique=True, nullable=False, index=True)
    xp_points = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    purchases = db.relationship('Purchase', back_populates='customer')
    subscriptions = db.relationship('Subscription', back_populates='customer')
    comments = db.relationship('Comment', back_populates='customer')
    ratings = db.relationship('Rating', back_populates='customer')
    ambassador_profile = db.relationship('Ambassador', back_populates='customer', uselist=False)

    def to_dict_detailed(self):
        """Serializes the customer with aggregated purchase and status data."""
        
        # Calculate total spent and number of purchases
        total_spent = 0
        purchase_count = 0
        for p in self.purchases:
            if p.status == PurchaseStatus.COMPLETED:
                total_spent += p.amount_paid
                purchase_count += 1
        
        # Determine status (e.g., is they an active subscriber?)
        is_subscriber = any(s.status == 'active' for s in self.subscriptions)

        return {
            'id': self.id,
            'name': self.whatsapp_number, # Using phone number as name for now
            'email': self.whatsapp_number, # Placeholder
            'avatar': f'https://i.pravatar.cc/48?u={self.whatsapp_number}', # Placeholder
            'join_date': self.created_at.isoformat(),
            'total_spent': float(total_spent),
            'purchases': purchase_count,
            'is_affiliate': self.ambassador_profile is not None,
            'is_subscriber': is_subscriber,
            # Add more fields as needed, e.g., location, notes
            'location': 'Unknown', 
            'notes': '',
        }

# ... The rest of the models (DigitalAsset, AssetFile, Purchase, etc.) are unchanged ...
# They were solid and do not need modification. This section is omitted for brevity
# but would be included in the final file.

class DigitalAsset(db.Model):
    """
    The core model for any digital product. This schema supports every field in the
    multi-step asset creation form and includes future-proofing for engagement and AI.
    """
    __tablename__ = 'digital_asset'
    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('creator.id'), nullable=False)
    
    # Core Details
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    story = db.Column(db.Text)
    cover_image_url = db.Column(db.String(512), default='/static/images/placeholder-cover.jpg')
    asset_type = db.Column(db.Enum(AssetType), nullable=False, default=AssetType.DIGITAL_PRODUCT)
    
    # Pricing & Publishing
    price = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.Enum(AssetStatus), default=AssetStatus.DRAFT, nullable=False, index=True)
    is_subscription = db.Column(db.Boolean, default=False)
    subscription_interval = db.Column(db.Enum(SubscriptionInterval), nullable=True)
    
    # Type-Specific Fields
    event_date = db.Column(db.DateTime, nullable=True)
    event_location = db.Column(db.String(512), nullable=True)
    max_attendees = db.Column(db.Integer, nullable=True)
    custom_fields = db.Column(JSON)
    details = db.Column(JSON, nullable=True)
    
    # Performance & Future-proofing
    total_sales = db.Column(db.Integer, default=0)
    total_revenue = db.Column(db.Numeric(10, 2), default=0.0)
    ai_summary = db.Column(db.Text, nullable=True)
    ai_tags = db.Column(JSON, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    creator = db.relationship('Creator', back_populates='assets')
    files = db.relationship('AssetFile', back_populates='asset', cascade="all, delete-orphan", lazy='dynamic') # Use lazy='dynamic' for files
    purchases = db.relationship('Purchase', back_populates='asset')
    ratings = db.relationship('Rating', back_populates='asset')
    comments = db.relationship('Comment', back_populates='asset')

    def to_dict(self):
        """Serializes the asset object to a dictionary for JSON conversion."""
        
        # Helper to format date and time if they exist
        event_date_str = self.event_date.strftime('%Y-%m-%d') if self.event_date else None
        event_time_str = self.event_date.strftime('%H:%M') if self.event_date else None

        asset_data = {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'story': self.story,
            'slug': self.slug,
            'price': float(self.price or 0.0),
            'status': self.status.value if self.status else None,
            'asset_type': self.asset_type.name if self.asset_type else None,
            'cover_image_url': self.cover_image_url,
            'total_sales': self.total_sales or 0,
            'total_revenue': float(self.total_revenue or 0.0),
            
            # Use the to_dict method from AssetFile for clean serialization
            'files': [f.to_dict() for f in self.files.all()],
            # This will be an array of review dictionaries
            'reviews': [r.to_dict() for r in self.ratings],
            # Create nested objects that the frontend component expects
            'eventDetails': {
                'link': self.event_location,
                'date': event_date_str,
                'time': event_time_str,
                'maxAttendees': self.max_attendees
            },
            
            # The 'details' column is JSON, so it can be used directly.
            # Provide a default empty dict to prevent frontend errors.
            'details': self.details or {} 
        }
        return asset_data
        
    def __repr__(self):
        return f'<DigitalAsset {self.id}: {self.title}>'

# === THIS IS THE FIX: A SQLAlchemy event listener that runs before an insert. ===
@db.event.listens_for(DigitalAsset, 'before_insert')
def generate_slug(mapper, connection, target):
    """
    Automatically generate a slug from the title if one is not provided.
    This is guaranteed to run before a new asset is saved to the database.
    """
    if not target.slug and target.title:
        # Generate a base slug from the title
        base_slug = slugify(target.title)
        unique_slug = base_slug
        # Check for uniqueness and append a number if necessary to avoid collisions
        n = 1
        while db.session.query(DigitalAsset.id).filter_by(slug=unique_slug).first():
            unique_slug = f"{base_slug}-{n}"
            n += 1
        target.slug = unique_slug

class AssetFile(db.Model):
    __tablename__ = 'asset_file'
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('digital_asset.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    storage_path = db.Column(db.String(1024), nullable=False)
    file_type = db.Column(db.String(50), nullable=True)
    order_index = db.Column(db.Integer, default=0)
    asset = db.relationship('DigitalAsset', back_populates='files')
    def to_dict(self):
        return { 
            'id': self.id, 
            'title': self.title, 
            'description': self.description, 
            'link': self.storage_path,
            'file_type': self.file_type
        }

class Purchase(db.Model):
    __tablename__ = 'purchase'
    id = db.Column(db.Integer, primary_key=True)
    transaction_token = db.Column(db.String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid.uuid4()))
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey('digital_asset.id'), nullable=False)
    amount_paid = db.Column(db.Numeric(10, 2), nullable=False)
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.Enum(PurchaseStatus), nullable=False, default=PurchaseStatus.PENDING)
    payment_gateway_ref = db.Column(db.String(255), nullable=True)
    sse_channel_id = db.Column(db.String(36), nullable=True, index=True)
    ticket_status = db.Column(db.Enum(TicketStatus), nullable=True)
    ticket_data = db.Column(JSON, nullable=True)
    customer = db.relationship('Customer', back_populates='purchases')
    asset = db.relationship('DigitalAsset', back_populates='purchases')
    def to_dict(self):
        """Serializes the Purchase object to a dictionary."""
        return {
            "id": self.id,
            "asset_id": self.asset_id,
            "status": {
                "name": self.status.name,
                "value": self.status.value
            },
            "transaction_token": self.transaction_token,
            "payment_gateway_ref": self.payment_gateway_ref
        }

class Subscription(db.Model):
    __tablename__ = 'subscription'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey('digital_asset.id'), nullable=False)
    status = db.Column(db.Enum(SubscriptionStatus), nullable=False, default=SubscriptionStatus.ACTIVE, index=True)
    interval = db.Column(db.Enum(SubscriptionInterval), nullable=False)
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    next_billing_date = db.Column(db.DateTime, nullable=True)
    end_date = db.Column(db.DateTime, nullable=True)
    payment_gateway_sub_id = db.Column(db.String(255), nullable=True)
    customer = db.relationship('Customer', back_populates='subscriptions')
    asset = db.relationship('DigitalAsset')

class Comment(db.Model):
    __tablename__ = 'comment'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey('digital_asset.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    customer = db.relationship('Customer', back_populates='comments')
    asset = db.relationship('DigitalAsset', back_populates='comments')
    parent = db.relationship('Comment', remote_side=[id], backref='replies')

class Rating(db.Model):
    __tablename__ = 'rating'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey('digital_asset.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    review_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship('Customer', back_populates='ratings')
    asset = db.relationship('DigitalAsset', back_populates='ratings')

    def to_dict(self):
        """Serializes the rating object into a dictionary for the frontend."""
        return {
            'author': self.customer.whatsapp_number, # Using phone number as author for now
            # NOTE: This is a placeholder for avatars. You can implement a real avatar system later.
            'avatar': f'https://i.pravatar.cc/48?u={self.customer.whatsapp_number}', 
            'rating': self.score,
            'text': self.review_text,
            'date': self.created_at.isoformat() # Send date in a standard format
        }

class Ambassador(db.Model):
    __tablename__ = 'ambassador'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), unique=True, nullable=False)
    affiliate_code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    commission_rate = db.Column(db.Float, default=0.10)
    is_active = db.Column(db.Boolean, default=True)
    customer = db.relationship('Customer', back_populates='ambassador_profile')