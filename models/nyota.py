# models/nyota.py

"""
nyota.py

This file defines the entire database schema for the Nyota ✨ application using SQLAlchemy.
It is the single source of truth for all data structures, combining a comprehensive feature set
with a professional, scalable model for creator settings and preferences.
"""

import enum
import uuid
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from slugify import slugify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy.types import JSON

from utils.recurrence import (
    DEFAULT_DURATION,
    normalize_recurrence,
    next_occurrence,
    occurrences,
)
from utils import i18n

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
    PHYSICAL = "Physical Product"

class AssetStatus(enum.Enum):
    DRAFT = "Draft"
    PUBLISHED = "Published"
    # Reachable by direct link and fully purchasable, but never listed, searched,
    # recommended or indexed. The link IS the access control.
    UNLISTED = "Unlisted"
    ARCHIVED = "Archived"

class SubscriptionInterval(enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    HALFYEARLY = "halfyearly"
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
# 'store_profile_enabled': (boolean) Toggle for public profile section
# 'store_photo_url': (string) URL to the creator's photo
# 'store_bio': (string) Short bio (meta description)
# 'store_bio_long': (string) Extended fun/engaging bio
# 'store_signature': (string) Creator's signature/tagline
# 'social_twitter': (string) Full URL to Twitter/X profile
# 'social_instagram': (string) Full URL to Instagram profile
# 'social_tiktok': (string) Full URL to TikTok profile
# 'social_youtube': (string) Full URL to YouTube profile
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
#
# --- Integrations: Marketing & Analytics ---
# 'marketing_meta_pixel_enabled': (boolean)
# 'marketing_meta_pixel_id': (string) Facebook/Meta Pixel ID (e.g. "1234567890")
# 'marketing_ga_enabled': (boolean)
# 'marketing_ga_measurement_id': (string) Google Analytics 4 Measurement ID (e.g. "G-XXXXXXXXXX")
#
# --- Store Preferences ---
# 'creator_timezone': (string) IANA timezone name, e.g. "Africa/Nairobi" or "Europe/London"
# 'asset_sort_mode': (string) How assets are ordered on public page:
#                   "manual" | "date_listed" | "date_modified" | "sales" | "alphabetical"
#
# --- Footer & Trust (rendered by utils/site_meta.py + user/partials/footer.html) ---
# Every '*_visibility' key is one of "public" | "session" | "verified", and gates the
# block against the reader's session strength. Anything not "public" is withheld from
# the JSON-LD too, because crawlers are anonymous.
#
# 'footer_enabled': (boolean) Master switch. Absent == on.
# 'footer_tagline': (string) One-line pitch under the footer logo
# 'footer_credit_enabled': (boolean) Show "Powered by Nyota". Absent == on.
#
# 'footer_about_enabled': (boolean)
# 'footer_about_text': (string) Falls back to 'store_bio' when blank
# 'footer_about_visibility': (string)
#
# 'footer_links_enabled': (boolean)
# 'footer_links': (list) Max 3 of {title, description, url}. Posted as one JSON field.
#
# 'footer_contact_enabled': (boolean) Renders 'contact_email' / 'contact_phone'
# 'footer_contact_whatsapp': (string) Phone number for the wa.me link
# 'footer_contact_visibility': (string)
#
# 'footer_address_enabled': (boolean)
# 'business_street', 'business_city', 'business_region',
# 'business_postal_code', 'business_country': (string) schema.org PostalAddress parts.
#                   A PUBLIC address promotes the markup from Organization to LocalBusiness.
# 'business_map_url': (string)
# 'footer_address_visibility': (string)
#
# 'footer_hours_enabled': (boolean)
# 'business_hours': (dict) {mon..sun: {closed: bool, open: "09:00", close: "17:00"}}.
#                   Posted as one JSON field. Days left blank are omitted.
# 'business_hours_note': (string)
# 'footer_hours_visibility': (string)
#
# 'footer_social_enabled': (boolean) Reuses the 'social_*' keys; also emitted as sameAs
#
# 'footer_trust_enabled': (boolean) Master switch for the trust strip
# 'footer_trust_secure_payment_enabled': (boolean)
# 'footer_trust_instant_delivery_enabled': (boolean)
# 'footer_trust_support_enabled': (boolean)
# 'footer_trust_support_text': (string)
# 'footer_stats_enabled': (boolean) Live social proof (customers, ratings) read from the DB
#
# 'footer_legal_name': (string) Registered business name
# 'footer_tax_id': (string) Registration / TIN, emitted as schema taxID
# 'footer_founding_year': (string) Emitted as schema foundingDate
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
    language = db.Column(db.String(5), default='en') # 'en' or 'sw'
    # Last delivery details from a physical-product order, reused to prefill the
    # next order's delivery questionnaire: {"answers": {<question>: <value>}, "updated_at": iso}
    saved_delivery = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    purchases = db.relationship('Purchase', back_populates='customer')
    subscriptions = db.relationship('Subscription', back_populates='customer')
    comments = db.relationship('Comment', back_populates='customer')
    ratings = db.relationship('Rating', back_populates='customer')
    ambassador_profile = db.relationship('Ambassador', back_populates='customer', uselist=False)

    def to_dict_detailed(self, creator_id=None):
        """Serializes the customer with aggregated purchase and status data."""
        
        # Calculate total spent and number of purchases
        total_spent = 0
        purchase_count = 0
        for p in self.purchases:
            # Skip if asset is missing (deleted or data integrity issue)
            if not p.asset:
               continue
               
            # Filter by creator if specified to ensure isolation
            if creator_id and p.asset.creator_id != creator_id:
                continue
                
            if p.status == PurchaseStatus.COMPLETED:
                total_spent += p.amount_paid
                purchase_count += 1
        
        # Determine status (e.g., is they an active subscriber?)
        is_subscriber = any(s.status == 'active' for s in self.subscriptions)

        # Determine how this customer was first acquired
        first_successful_refcode = None
        first_source = None
        for p in sorted(self.purchases, key=lambda x: x.purchase_date):
            if not p.asset:
                continue
            if creator_id and p.asset.creator_id != creator_id:
                continue
            if p.status == PurchaseStatus.COMPLETED and p.refcode_outcome == 'customer_success':
                if first_successful_refcode is None:
                    first_successful_refcode = p.refcode_used
            if p.status == PurchaseStatus.COMPLETED and p.source_used:
                if first_source is None:
                    first_source = p.source_used

        return {
            'id': self.id,
            'name': self.whatsapp_number, # Using phone number as name for now
            'whatsapp_number': self.whatsapp_number,
            'email': self.whatsapp_number, # Placeholder
            'avatar': f'https://i.pravatar.cc/48?u={self.whatsapp_number}', # Placeholder
            'join_date': self.created_at.strftime('%b %d, %Y'),
            'total_spent': float(total_spent),
            'purchases': purchase_count,
            'is_affiliate': self.ambassador_profile is not None,
            'is_subscriber': is_subscriber,
            'location': 'Unknown',
            'notes': '',
            'acquisition_refcode': first_successful_refcode,
            'acquisition_source': first_source,
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
    allow_download = db.Column(db.Boolean, default=True) # New field for download control
    
    # Type-Specific Fields
    event_date = db.Column(db.DateTime, nullable=True)
    event_location = db.Column(db.String(512), nullable=True)
    max_attendees = db.Column(db.Integer, nullable=True)
    custom_fields = db.Column(JSON)
    details = db.Column(JSON, nullable=True)

    # --- The second language -------------------------------------------------
    # Everything above holds the creator's PRIMARY language — whatever they typed
    # when they made the asset. `translations` holds the other one, and only the
    # other one, so an asset made before this existed needs no backfill and reads
    # exactly as it always did.
    #
    #   {"en": {"title": ..., "description": ..., "cover_image_url": ...,
    #           "details": {"welcomeContent": ...,
    #                       "variations": {"<id>": {"name": ...}}},
    #           "custom_fields": {"<key>": {"question": ...}}}}
    #
    # Nested rows are keyed by their own stable id, never their position. See
    # utils/i18n.TRANSLATABLE_* for the manifest of what may appear here.
    translations = db.Column(JSON, nullable=True)
    # Which language the columns above are written in. Read ONLY by the admin
    # editor, to label its language switch — resolution never consults it, so a
    # wrong or missing value can never show a visitor the wrong words.
    primary_language = db.Column(db.String(5), nullable=True)

    # Performance & Future-proofing
    total_sales = db.Column(db.Integer, default=0)
    total_revenue = db.Column(db.Numeric(10, 2), default=0.0)
    ai_summary = db.Column(db.Text, nullable=True)
    ai_tags = db.Column(JSON, nullable=True)

    # Ordering & Pinning
    display_order = db.Column(db.Integer, default=0, nullable=False)
    is_pinned = db.Column(db.Boolean, default=False, nullable=False)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    creator = db.relationship('Creator', back_populates='assets')
    files = db.relationship('AssetFile', back_populates='asset', cascade="all, delete-orphan", lazy='dynamic') # Use lazy='dynamic' for files
    purchases = db.relationship('Purchase', back_populates='asset')
    ratings = db.relationship('Rating', back_populates='asset')
    comments = db.relationship('Comment', back_populates='asset')

    def creator_timezone(self):
        """(IANA name, ZoneInfo) for the creator, falling back to the store's region."""
        tz_name = None
        try:
            if self.creator:
                tz_name = self.creator.get_setting('creator_timezone')
        except Exception:
            tz_name = None
        tz_name = tz_name or 'Africa/Nairobi'  # sensible default for the store's region
        try:
            return tz_name, ZoneInfo(tz_name)
        except Exception:
            return 'Africa/Nairobi', ZoneInfo('Africa/Nairobi')

    # --- Localisation --------------------------------------------------------
    # Localisation is a PROJECTION, applied when an asset is rendered or
    # serialized for a visitor. The attributes themselves — title, description,
    # details, custom_fields — are always canonical, because they are also read
    # by things that write: checkout prices an order from `details`, the order
    # snapshot and the payment gateway's product line take `title`, and the CSV
    # export has to say the same words every time. Ask for the localised value
    # explicitly, at the point where a person is about to read it.

    @property
    def primary_lang(self):
        """The language the base columns are written in."""
        if self.primary_language:
            return self.primary_language
        try:
            if self.creator:
                setting = self.creator.get_setting('content_primary_language')
                if setting in i18n.SUPPORTED_LANGUAGES:
                    return setting
        except Exception:
            pass
        return i18n.DEFAULT_LANGUAGE

    def _base_value(self, path):
        """The canonical value at a dotted path ('title', 'details.benefits')."""
        parts = path.split('.')
        value = getattr(self, parts[0], None)
        for part in parts[1:]:
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value

    def localized(self, path, lang=None):
        """One field in the reader's language, falling back to the original."""
        lang = lang or i18n.current_lang()
        base = self._base_value(path)
        if lang == self.primary_lang:
            return base
        return i18n.resolve(self.translations, lang, path, base)

    @staticmethod
    def _with_stable_ids(rows, spec):
        """Copies of `rows`, each carrying the id its translation is filed under.

        The save route mints these, but the editor needs one the moment a row is
        drawn — including for an asset that hasn't been saved since translations
        existed. Publishing the same id the server would compute keeps the two
        sides agreeing about which row a translation belongs to.
        """
        if not isinstance(rows, list):
            return rows
        out = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                out.append(row)
                continue
            row = dict(row)
            if spec['id_key'] == 'key':
                row['key'] = i18n.custom_field_key(row, index)
            elif not row.get('id'):
                row['id'] = f'{spec["path"].rsplit(".", 1)[-1][:1]}{index}'
            out.append(row)
        return out

    def _localize_rows(self, rows, spec, lang):
        """Localise a list of repeating rows (variations, tiers, slots) in place.

        `rows` must already be a private copy — this mutates it.
        """
        slot = ((self.translations or {}).get(lang) or {})
        for part in spec['path'].split('.'):
            if not isinstance(slot, dict):
                return
            slot = slot.get(part)
        if not isinstance(slot, dict):
            return
        id_key = spec['id_key']
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            row_id = (i18n.custom_field_key(row, i) if id_key == 'key'
                      else str(row.get(id_key) or ''))
            entry = slot.get(row_id)
            if not isinstance(entry, dict):
                continue
            for field in spec['fields']:
                value = entry.get(field['key'])
                if field['widget'] == 'list':
                    # Choices are index-aligned with the canonical list; a short
                    # or ragged translation falls back per position, never
                    # shifting a label onto the wrong choice.
                    canonical = row.get(field['key'])
                    if not isinstance(canonical, list) or not isinstance(value, list):
                        continue
                    row[field['key'] + '_display'] = [
                        str(value[j]).strip() if j < len(value) and str(value[j] or '').strip()
                        else canonical[j]
                        for j in range(len(canonical))
                    ]
                elif value is not None and str(value).strip():
                    if id_key == 'key':
                        # The question string is a storage key — never overwrite
                        # it, publish the reader's version beside it.
                        row[field['key'] + '_display'] = str(value).strip()
                    else:
                        row[field['key']] = str(value).strip()

    def event_recurrence(self):
        """The normalized repeating schedule, or None when this is a one-off event."""
        return normalize_recurrence((self.details or {}).get('recurrence'))

    def next_event_occurrence(self, now=None):
        """
        The occurrence a repeating event should currently advertise (None for a
        one-off, or once a series has run past its end date).
        """
        recurrence = self.event_recurrence()
        if not recurrence:
            return None
        _, tz = self.creator_timezone()
        return next_occurrence(recurrence, tz, now=now)

    def to_dict(self, lang=None, include_translations=False):
        """Serializes the asset object to a dictionary for JSON conversion.

        `lang=None` is the canonical payload — the creator's own words, byte for
        byte what this returned before translations existed. That is what the
        admin editor, the CSV exports and anything that writes an order want.

        Pass `lang` to get the payload a visitor should read: every creator-written
        string resolved into that language, with the original standing in wherever
        they haven't translated yet. The SHAPE is identical either way, so a
        template can render one without knowing which it was handed.

        `include_translations` adds the raw blob and the primary language, for the
        one caller that edits them.
        """
        localize = bool(lang) and lang != self.primary_lang

        # A repeating event ("every Thursday") has no fixed event_date — the date
        # shown everywhere is the NEXT occurrence, recomputed on each render. It is
        # published through the same eventDetails keys as a one-off, so the asset
        # page, countdown, calendar files and QR all roll forward untouched.
        recurrence = self.event_recurrence()
        # Localise the schedule HERE, before anything reads it. normalize_recurrence
        # hands back a fresh dict, so mutating it can't touch stored data — and
        # doing it now means the occurrences computed below carry the translated
        # session names, and `details` and `eventDetails` go on sharing one set of
        # slot objects. That sharing is load-bearing: the asset route redacts a
        # private per-session join link once and expects both copies covered.
        if localize and recurrence:
            for spec in i18n.translatable_collections(self.asset_type):
                if spec['path'] == 'details.recurrence.slots':
                    self._localize_rows(recurrence['slots'], spec, lang)
        occurrence = None
        upcoming = []
        tz_name, tz = (None, None)
        if recurrence or self.event_date:
            tz_name, tz = self.creator_timezone()
        if recurrence:
            # Every repeating day must appear at least once: the frontend anchors
            # one calendar rule per slot on that slot's first upcoming session.
            upcoming = occurrences(recurrence, tz, limit=max(6, 2 * len(recurrence['slots'])))
            occurrence = upcoming[0] if upcoming else None

        # event_date is stored as a NAIVE datetime holding the creator's wall-clock
        # time (what the admin typed); a recurrence supplies the same shape.
        if occurrence:
            event_dt = occurrence['start_local']
        else:
            event_dt = None if recurrence else self.event_date
        event_date_str = event_dt.strftime('%Y-%m-%d') if event_dt else None
        event_time_str = event_dt.strftime('%H:%M') if event_dt else None

        # Resolve the event against the creator's configured timezone so the public
        # always sees the SAME canonical wall-clock the admin set, while the calendar
        # files / "your local time" hints can be anchored to a real UTC instant.
        event_utc_str = None        # absolute instant, e.g. "2026-06-27T18:32:00Z"
        event_end_utc_str = None    # end of the session, drives calendar duration
        event_tz_name = None        # IANA name, e.g. "Africa/Nairobi"
        event_tz_label = None       # friendly label, e.g. "EAT" or "GMT+3"
        event_tz_offset_min = None  # creator offset from UTC at the event, e.g. 180
        event_duration_min = None
        if event_dt:
            aware = event_dt.replace(tzinfo=tz)
            event_utc_str = aware.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            event_duration_min = occurrence['duration'] if occurrence else DEFAULT_DURATION
            event_end_utc_str = (occurrence['end_utc'] if occurrence else
                                 (aware + timedelta(minutes=event_duration_min))
                                 .astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
            event_tz_name = tz_name
            offset = aware.utcoffset()
            event_tz_offset_min = int(offset.total_seconds() // 60) if offset else 0
            abbrev = aware.tzname() or ''
            # Some zones report a numeric abbrev like "+03"; fall back to a GMT label.
            if abbrev and abbrev.isalpha():
                event_tz_label = abbrev
            else:
                sign = '+' if event_tz_offset_min >= 0 else '-'
                hrs, mins = divmod(abs(event_tz_offset_min), 60)
                event_tz_label = f"GMT{sign}{hrs}" + (f":{mins:02d}" if mins else "")

        # A slot may override the join link / venue for its own day (e.g. a
        # Thursday Zoom room and a Saturday studio address).
        event_link = self.event_location
        # Only a real venue is worth translating. When the location IS the private
        # join URL, leave it exactly as stored: `isOnline` below is derived from
        # this string and drives whether the route redacts it, and a translated
        # URL would be both meaningless and a needless way to get that wrong.
        if localize and not str(event_link or '').startswith('http'):
            event_link = self.localized('event_location', lang) or event_link
        if occurrence and occurrence['slot'].get('link'):
            event_link = occurrence['slot']['link']

        # A copy of details, with the raw stored schedule swapped for the
        # normalized one published under eventDetails. They share slot objects on
        # purpose: a caller redacting a private per-session link (the asset page
        # does this for non-buyers) then covers both copies, and never mutates
        # the model's own JSON.
        details_out = dict(self.details or {})
        if 'recurrence' in details_out:
            if recurrence:
                details_out['recurrence'] = recurrence
            else:
                details_out.pop('recurrence')

        # Repeating rows go out carrying the id their translation is filed under,
        # in BOTH modes: the editor needs it to address a row, and the reader needs
        # it to have been the same id when the translation was written.
        custom_fields_out = self.custom_fields or []
        for spec in i18n.translatable_collections(self.asset_type):
            if spec['path'] == 'custom_fields':
                custom_fields_out = self._with_stable_ids(custom_fields_out, spec)
            elif spec['path'].startswith('details.') and spec['path'] != 'details.recurrence.slots':
                key = spec['path'].split('.', 1)[1]
                if isinstance(details_out.get(key), list):
                    details_out[key] = self._with_stable_ids(details_out[key], spec)

        if localize:
            # Single-value fields that live inside details (welcome message,
            # after-purchase instructions, ...).
            for spec in i18n.translatable_fields(self.asset_type):
                path = spec['path']
                if not path.startswith('details.'):
                    continue
                key = path.split('.', 1)[1]
                value = self.localized(path, lang)
                if value is not None:
                    details_out[key] = value

            # Repeating rows. Each list is copied before it is touched, so the
            # model's own JSON is never mutated. The schedule is skipped — it was
            # localised above and must keep sharing its slots with eventDetails.
            for spec in i18n.translatable_collections(self.asset_type):
                path = spec['path']
                if path == 'details.recurrence.slots':
                    continue
                if path.startswith('details.'):
                    key = path.split('.', 1)[1]
                    rows = details_out.get(key)
                    if isinstance(rows, list):
                        rows = [dict(r) if isinstance(r, dict) else r for r in rows]
                        self._localize_rows(rows, spec, lang)
                        details_out[key] = rows
                elif path == 'custom_fields' and isinstance(custom_fields_out, list):
                    custom_fields_out = [
                        dict(f) if isinstance(f, dict) else f for f in custom_fields_out
                    ]
                    self._localize_rows(custom_fields_out, spec, lang)

        asset_data = {
            'id': self.id,
            'title': self.localized('title', lang) if localize else self.title,
            'description': self.localized('description', lang) if localize else self.description,
            'story': self.localized('story', lang) if localize else self.story,
            'slug': self.slug,
            'price': float(self.price or 0.0),
            'status': self.status.value if self.status else None,
            'asset_type': self.asset_type.name if self.asset_type else None,
            'is_subscription': self.is_subscription,
            'subscription_interval': self.subscription_interval.name if self.subscription_interval else None,
            'allow_download': self.allow_download,
            'cover_image_url': (self.localized('cover_image_url', lang) if localize
                                else self.cover_image_url),
            'total_sales': self.total_sales or 0,
            'total_revenue': float(self.total_revenue or 0.0),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'display_order': self.display_order or 0,
            'is_pinned': self.is_pinned or False,
            'custom_fields': custom_fields_out,
            'uza_product_id': (self.details or {}).get('uza_product_id', ''),

            # Use the to_dict method from AssetFile for clean serialization
            'files': [f.to_dict(lang if localize else None) for f in self.files.all()],
            # This will be an array of review dictionaries
            'reviews': [r.to_dict() for r in self.ratings],
            # Create nested objects that the frontend component expects
            'eventDetails': {
                'link': event_link,
                # A URL location is a private join link (the deliverable for a webinar);
                # the route redacts the actual URL for non-buyers but keeps this flag so
                # the public view can still show "Online event".
                'isOnline': bool(event_link and str(event_link).startswith('http')),
                'date': event_date_str,
                'time': event_time_str,
                'maxAttendees': self.max_attendees,
                # Timezone context so the frontend can show the canonical creator time
                # and compute the buyer's local equivalent / offset.
                'utc': event_utc_str,
                'endUtc': event_end_utc_str,
                'durationMinutes': event_duration_min,
                'timezone': event_tz_name,
                'tzLabel': event_tz_label,
                'tzOffsetMinutes': event_tz_offset_min,
                # --- Repeating series ------------------------------------------
                # `recurrence` describes the cadence (so the page can say "Every
                # Thursday" and the ICS can carry an RRULE); `occurrences` lists the
                # next few resolved sessions. Both are absent for a one-off event.
                'isRecurring': bool(recurrence),
                'recurrence': recurrence,
                'occurrences': [{
                    'date': o['date'],
                    'time': o['time'],
                    'utc': o['utc'],
                    'endUtc': o['end_utc'],
                    'durationMinutes': o['duration'],
                    'label': o['slot'].get('label') or '',
                    'link': o['slot'].get('link') or '',
                    'note': o['slot'].get('note') or '',
                    'slotId': o['slot'].get('id'),
                    'inProgress': o['in_progress'],
                } for o in upcoming],
                # A series whose end date has passed: no date to advertise, and the
                # frontend should say so rather than silently hide the card.
                'seriesEnded': bool(recurrence and not upcoming),
                'inProgress': bool(occurrence and occurrence['in_progress']),
                'sessionLabel': (occurrence['slot'].get('label') if occurrence else '') or '',
                'sessionNote': (occurrence['slot'].get('note') if occurrence else '') or '',
            },
            
            # The 'details' column is JSON, so it can be used directly.
            # Provide a default empty dict to prevent frontend errors.
            'details': details_out
        }
        if include_translations:
            # The editor needs the raw other-language blob to put in its boxes,
            # and needs to know which side its language switch calls "original".
            asset_data['translations'] = self.translations or {}
            asset_data['primary_language'] = self.primary_lang
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
    position = db.Column(db.Integer, default=0)
    # {"en": {"title": ..., "description": ...}} — same contract as the asset's:
    # only the non-primary language, the columns hold the original.
    translations = db.Column(JSON, nullable=True)
    asset = db.relationship('DigitalAsset', back_populates='files')

    def localized(self, field, lang=None):
        """Title or description in the reader's language, else the original."""
        base = getattr(self, field, None)
        if not lang:
            return base
        return i18n.resolve(self.translations, lang, field, base)

    def to_dict(self, lang=None):
        link = self.storage_path
        if link and link.startswith('secure_uploads/'):
            link = f"/content/{self.id}"
        
        # Compute file_type if not set (for legacy files)
        file_type = self.file_type
        if not file_type and self.storage_path:
            # Extract extension from storage_path
            ext = self.storage_path.split('.')[-1].lower().split('?')[0] if '.' in self.storage_path else ''
            if ext in ['pdf']:
                file_type = 'pdf'
            elif ext in ['mp3', 'wav', 'ogg', 'm4a', 'aac']:
                file_type = 'audio'
            elif ext in ['mp4', 'webm', 'mov', 'avi']:
                file_type = 'video'
            elif ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg']:
                file_type = 'image'
            else:
                file_type = 'other'
            
        return {
            'id': self.id,
            'title': self.localized('title', lang),
            'description': self.localized('description', lang),
            'link': link,
            'file_type': file_type or 'other',
            'storage_path': self.storage_path
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
    # Referral & Source Attribution — all nullable to preserve existing records
    visitor_refcode  = db.Column(db.String(100), nullable=True, index=True)
    visitor_source   = db.Column(db.String(100), nullable=True)
    refcode_used     = db.Column(db.String(100), nullable=True, index=True)
    source_used      = db.Column(db.String(100), nullable=True)
    refcode_outcome  = db.Column(db.String(20), nullable=True)
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
            "payment_gateway_ref": self.payment_gateway_ref,
            "customer_phone": self.customer.whatsapp_number if self.customer else None
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

class AccessAttempt(db.Model):
    """
    Tracks session recovery attempts for rate limiting and security monitoring.
    Prevents brute force attacks on the session recovery mechanism.
    """
    __tablename__ = 'access_attempt'
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False, index=True)
    phone_suffix = db.Column(db.String(4), nullable=False)
    attempt_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    success = db.Column(db.Boolean, default=False, nullable=False)

    def __repr__(self):
        return f'<AccessAttempt {self.ip_address} at {self.attempt_time}>'


class SMSMagicLink(db.Model):
    """
    Tracks magic links sent to phone numbers to restore library access on a new browser
    and to enforce SMS rate limiting when a customer re-attempts checkout for an item
    they already own.
    """
    __tablename__ = 'sms_magic_link'
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(25), nullable=False, index=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('digital_asset.id'), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True,
                      default=lambda: secrets.token_urlsafe(22))
    opens_remaining = db.Column(db.Integer, default=3)
    sms_count = db.Column(db.Integer, default=0)
    last_sms_sent_at = db.Column(db.DateTime, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    asset = db.relationship('DigitalAsset')


class SMSCampaignStatus(enum.Enum):
    DRAFT = "Draft"
    SCHEDULED = "Scheduled"
    SENDING = "Sending"
    SENT = "Sent"
    FAILED = "Failed"


class SMSCampaign(db.Model):
    """
    Stores SMS marketing campaign definitions. Target groups are stored as JSON
    to avoid a complex many-to-many schema and remain schema-flexible.
    """
    __tablename__ = 'sms_campaign'
    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('creator.id'), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.Enum(SMSCampaignStatus), default=SMSCampaignStatus.DRAFT, nullable=False)
    # targeting JSON example:
    # {"groups": ["past_buyers", "active_subscribers", "expired_subscribers"],
    #  "asset_ids": [1, 2],  # empty = all creator assets
    #  "imported_phones": ["255712...", "255713..."]}
    targeting = db.Column(JSON, nullable=False, default=dict)
    total_recipients = db.Column(db.Integer, default=0)
    sent_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)
    scheduled_at = db.Column(db.DateTime, nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    # Recurring campaign support
    is_recurring = db.Column(db.Boolean, default=False)
    recurrence_interval_days = db.Column(db.Integer, nullable=True)
    next_run_at = db.Column(db.DateTime, nullable=True)
    smart_exclude_recent_buyers = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    creator = db.relationship('Creator')


class SMSCampaignLog(db.Model):
    """Per-recipient delivery log for each campaign send."""
    __tablename__ = 'sms_campaign_log'
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('sms_campaign.id'), nullable=False, index=True)
    phone_number = db.Column(db.String(25), nullable=False)
    status = db.Column(db.String(20), default='pending')  # 'pending', 'sent', 'failed'
    error_message = db.Column(db.Text, nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    campaign = db.relationship('SMSCampaign')


class SMSLogType(enum.Enum):
    PURCHASE = "purchase"
    MAGIC_LINK = "magic_link"
    REMINDER = "reminder"
    CAMPAIGN = "campaign"


class SMSLog(db.Model):
    """Global audit log for every SMS sent through Nyota."""
    __tablename__ = 'sms_log'
    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('creator.id'), nullable=False, index=True)
    phone_number = db.Column(db.String(25), nullable=False)
    message_preview = db.Column(db.String(200), nullable=True)
    log_type = db.Column(db.Enum(SMSLogType), nullable=False)
    status = db.Column(db.String(10), default='sent')  # 'sent' / 'failed'
    campaign_id = db.Column(db.Integer, db.ForeignKey('sms_campaign.id'), nullable=True, index=True)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    error_message = db.Column(db.Text, nullable=True)