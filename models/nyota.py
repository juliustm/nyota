"""
nyota.py

This file defines the entire database schema for the Nyota Digital application using SQLAlchemy.
It includes models for Creators, Customers, Digital Assets, Purchases, Subscriptions, and more,
all designed to support the core features outlined in the project vision.
"""

import enum
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()

# --- Enums for Standardized Field Choices ---

class AssetType(enum.Enum):
    """Defines the different kinds of digital assets a creator can sell."""
    DIGITAL_PRODUCT = "Digital Product"  # Generic catch-all
    VIDEO_SERIES = "Video Series"
    AUDIO_ALBUM = "Audio Album"
    EBOOK = "E-Book / Magazine"
    PHOTO_PACK = "Photo Pack"
    TEMPLATE = "Template / File"
    TICKET = "Event Ticket"

class SubscriptionInterval(enum.Enum):
    """Defines recurring payment intervals."""
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUALLY = "annually"

class SubscriptionStatus(enum.Enum):
    """Defines the state of a customer's subscription."""
    ACTIVE = "active"
    CANCELED = "canceled"
    PAST_DUE = "past_due"

class TicketStatus(enum.Enum):
    """Defines the state of a purchased event ticket."""
    VALID = "valid"
    USED = "used"
    EXPIRED = "expired"


# --- Core Models ---

class Creator(db.Model):
    """
    Represents the Creator/Admin of the Nyota Digital store.
    Authentication is handled via TOTP, not passwords.
    """
    __tablename__ = 'creator'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    totp_secret = db.Column(db.String(32), nullable=False)
    
    # Creator-specific settings
    store_name = db.Column(db.String(120), default="My Digital Store")
    currency_symbol = db.Column(db.String(10), default="$")

    # Relationships
    assets = db.relationship('DigitalAsset', back_populates='creator', lazy='dynamic')

    def __repr__(self):
        return f'<Creator {self.username}>'

class Customer(db.Model):
    """
    Represents a buyer, identified uniquely by their WhatsApp number.
    This model is the central hub for a customer's purchases and engagement.
    """
    __tablename__ = 'customer'
    id = db.Column(db.Integer, primary_key=True)
    whatsapp_number = db.Column(db.String(25), unique=True, nullable=False, index=True)
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    purchases = db.relationship('Purchase', back_populates='customer', lazy='dynamic')
    subscriptions = db.relationship('Subscription', back_populates='customer', lazy='dynamic')
    comments = db.relationship('Comment', back_populates='customer', lazy='dynamic')
    ambassador_profile = db.relationship('Ambassador', back_populates='customer', uselist=False)

    def __repr__(self):
        return f'<Customer {self.whatsapp_number}>'

class DigitalAsset(db.Model):
    """
    The core model representing any digital product, from a video series to an event ticket.
    Designed for flexibility with self-referencing for series and JSON for custom fields.
    """
    __tablename__ = 'digital_asset'
    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('creator.id'), nullable=False)
    
    # Core Details
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)  # Short summary
    story = db.Column(db.Text)  # The long-form "Context"
    cover_image_url = db.Column(db.String(512))
    asset_type = db.Column(db.Enum(AssetType), nullable=False, default=AssetType.DIGITAL_PRODUCT)
    
    # Pricing & Publishing
    price = db.Column(db.Numeric(10, 2), nullable=False)
    is_published = db.Column(db.Boolean, default=False, index=True)
    release_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # --- Special Fields based on AssetType ---
    # For Series (e.g., Video Courses, Audio Series)
    parent_id = db.Column(db.Integer, db.ForeignKey('digital_asset.id'), nullable=True)
    order_index = db.Column(db.Integer, default=0) # Order of episodes in a series
    
    # For Tickets
    custom_fields = db.Column(db.JSON) # e.g., [{"name": "t_shirt_size", "label": "T-Shirt Size", "type": "select", "options": ["S", "M", "L"]}]

    # Relationships
    creator = db.relationship('Creator', back_populates='assets')
    files = db.relationship('AssetFile', back_populates='asset', cascade="all, delete-orphan")
    parent = db.relationship('DigitalAsset', remote_side=[id], backref='children')

    def __repr__(self):
        return f'<DigitalAsset {self.id}: {self.title}>'

class AssetFile(db.Model):
    """
    Represents a single downloadable file associated with a DigitalAsset.
    An asset (like a course) can have many files (videos, PDFs, etc.).
    """
    __tablename__ = 'asset_file'
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('digital_asset.id'), nullable=False)
    
    file_name = db.Column(db.String(255)) # User-facing filename
    storage_path = db.Column(db.String(1024), nullable=False) # Secure path in storage
    file_type = db.Column(db.String(50)) # e.g., 'pdf', 'mp4', 'zip'
    order_index = db.Column(db.Integer, default=0) # Order of files within an asset

    # Relationship
    asset = db.relationship('DigitalAsset', back_populates='files')

    def __repr__(self):
        return f'<AssetFile {self.file_name}>'

# --- Transactional & Engagement Models ---

class Purchase(db.Model):
    """
    Records a one-time purchase, linking a Customer to a DigitalAsset.
    This is the "key" to customer access.
    """
    __tablename__ = 'purchase'
    id = db.Column(db.Integer, primary_key=True)
    transaction_token = db.Column(db.String(36), unique=True, nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey('digital_asset.id'), nullable=False)
    
    amount_paid = db.Column(db.Numeric(10, 2), nullable=False)
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    payment_gateway_ref = db.Column(db.String(255)) # Reference from payment provider (e.g., Stripe, M-Pesa)
    
    # --- Special Fields for Tickets ---
    ticket_status = db.Column(db.Enum(TicketStatus), nullable=True)
    ticket_data = db.Column(db.JSON) # Stores the filled-out custom form, e.g., {"t_shirt_size": "L"}

    # Relationships
    customer = db.relationship('Customer', back_populates='purchases')
    asset = db.relationship('DigitalAsset')

    def __repr__(self):
        return f'<Purchase {self.id} by Customer {self.customer_id}>'

class Subscription(db.Model):
    """Records a recurring subscription for a Customer to a DigitalAsset."""
    __tablename__ = 'subscription'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey('digital_asset.id'), nullable=False)

    status = db.Column(db.Enum(SubscriptionStatus), nullable=False, default=SubscriptionStatus.ACTIVE, index=True)
    interval = db.Column(db.Enum(SubscriptionInterval), nullable=False)
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    next_billing_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime, nullable=True) # Date of cancellation
    payment_gateway_sub_id = db.Column(db.String(255)) # ID from Stripe, etc.

    # Relationships
    customer = db.relationship('Customer', back_populates='subscriptions')
    asset = db.relationship('DigitalAsset')

class Comment(db.Model):
    """
    Represents a single comment in the "Social Like feed" for an asset.
    Supports threaded replies via a self-referencing relationship.
    """
    __tablename__ = 'comment'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey('digital_asset.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    
    # Relationships
    customer = db.relationship('Customer', back_populates='comments')
    asset = db.relationship('DigitalAsset')
    parent = db.relationship('Comment', remote_side=[id], backref='replies')

# --- Ambassador/Affiliate Model ---

class Ambassador(db.Model):
    """
    Represents a customer who has joined the ambassador/affiliate program.
    Linked one-to-one with a Customer.
    """
    __tablename__ = 'ambassador'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), unique=True, nullable=False)
    affiliate_code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    commission_rate = db.Column(db.Float, default=0.10) # Default 10%
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationship
    customer = db.relationship('Customer', back_populates='ambassador_profile')