"""
site_meta.py

Builds the public storefront footer and the structured data (JSON-LD) that goes
with it.

Two rules drive everything in here:

1. One source of truth. The footer HTML and the schema.org markup are generated
   from the same resolved dict, so a detail can never be visible on the page but
   missing from the markup (or worse, the other way round).

2. Private details never reach a crawler. Search engines browse anonymously, so
   any block the creator has gated behind a reader session is dropped from BOTH
   the rendered HTML and the JSON-LD. Gating is done server-side -- gated blocks
   are never sent to the browser at all, rather than hidden with CSS.
"""

import time
from datetime import datetime

from flask import session, url_for

from models.nyota import (
    AssetStatus,
    CreatorSetting,
    DigitalAsset,
    Purchase,
    PurchaseStatus,
    Rating,
    db,
)

# Visibility levels a creator can pick per footer block, ordered weakest viewer
# to strongest. A block shows when the viewer's level is at least the block's.
VISIBILITY_PUBLIC = 'public'
VISIBILITY_SESSION = 'session'
VISIBILITY_VERIFIED = 'verified'

_VIEWER_RANK = {VISIBILITY_PUBLIC: 0, VISIBILITY_SESSION: 1, VISIBILITY_VERIFIED: 2}

WEEKDAYS = [
    ('mon', 'Monday'),
    ('tue', 'Tuesday'),
    ('wed', 'Wednesday'),
    ('thu', 'Thursday'),
    ('fri', 'Friday'),
    ('sat', 'Saturday'),
    ('sun', 'Sunday'),
]

# schema.org expects full day URIs in openingHoursSpecification.
_SCHEMA_DAY = {k: f'https://schema.org/{name}' for k, name in WEEKDAYS}

MAX_FOOTER_LINKS = 3

# Social proof counts hit the DB, so they are cached process-wide for a few
# minutes. They are approximate trust signals, not live figures.
_STATS_TTL_SECONDS = 300
_stats_cache = {'at': 0.0, 'value': None}


def _viewer_level():
    """How much the current visitor has proven about themselves.

    A phone in session is a *claim* (it can be set by claiming a free asset),
    while `is_verified` is only granted by payment, magic link, or phone+date.
    Treat them as separate tiers so a creator can reserve, say, a physical
    address for people who have actually bought something.
    """
    if session.get('is_verified'):
        return VISIBILITY_VERIFIED
    if session.get('customer_phone'):
        return VISIBILITY_SESSION
    return VISIBILITY_PUBLIC


def _can_view(required, viewer):
    return _VIEWER_RANK.get(viewer, 0) >= _VIEWER_RANK.get(required, 0)


def _load_settings(creator):
    """Every setting for the creator in a single query.

    `creator.get_setting()` runs one query per key; the footer reads ~30 of
    them on every page, so it loads the whole set at once instead.
    """
    rows = CreatorSetting.query.filter_by(creator_id=creator.id).all()
    return {row.key: row.value for row in rows}


def _clean(value):
    """Settings are free text; treat blanks and legacy 'None' strings as unset."""
    if value is None:
        return ''
    text = str(value).strip()
    return '' if text.lower() in ('none', 'null') else text


def _truthy(value):
    """Settings written by different code paths store booleans inconsistently."""
    if isinstance(value, bool):
        return value
    return _clean(value).lower() in ('true', 'on', '1', 'yes')


def _visibility(settings, key):
    value = _clean(settings.get(key)) or VISIBILITY_PUBLIC
    return value if value in _VIEWER_RANK else VISIBILITY_PUBLIC


def absolute_media_url(url):
    """Turn a stored media path (/static/…, /media/…) into a full URL.

    Cover paths are already root-relative, so passing them through
    `url_for('static', …)` produced /static/static/… — which is what social
    previews and JSON-LD were pointing at. Everything that publishes a media URL
    goes through here instead.
    """
    return _absolute(url)


def _absolute(url):
    """Make a stored media path absolute; schema.org requires full URLs."""
    url = _clean(url)
    if not url:
        return ''
    if url.startswith(('http://', 'https://')):
        return url
    try:
        return url_for('main.landing_page', _external=True).rstrip('/') + '/' + url.lstrip('/')
    except RuntimeError:
        return url


def get_trust_stats():
    """Real social proof pulled from the DB, cached for a few minutes.

    Only genuine figures are ever surfaced. If a number is zero the template
    drops that stat rather than printing a "0 customers" anti-signal.
    """
    now = time.time()
    if _stats_cache['value'] is not None and now - _stats_cache['at'] < _STATS_TTL_SECONDS:
        return _stats_cache['value']

    try:
        customers = (
            db.session.query(db.func.count(db.distinct(Purchase.customer_id)))
            .filter(Purchase.status == PurchaseStatus.COMPLETED)
            .scalar()
        ) or 0
        assets = (
            db.session.query(db.func.count(DigitalAsset.id))
            .filter(DigitalAsset.status == AssetStatus.PUBLISHED)
            .scalar()
        ) or 0
        rating_count = db.session.query(db.func.count(Rating.id)).scalar() or 0
        rating_avg = db.session.query(db.func.avg(Rating.score)).scalar()

        stats = {
            'customers': int(customers),
            'assets': int(assets),
            'rating_count': int(rating_count),
            'rating_avg': round(float(rating_avg), 1) if rating_avg else 0.0,
        }
    except Exception:
        # A footer must never take a page down.
        stats = {'customers': 0, 'assets': 0, 'rating_count': 0, 'rating_avg': 0.0}

    _stats_cache['at'] = now
    _stats_cache['value'] = stats
    return stats


def invalidate_stats_cache():
    _stats_cache['at'] = 0.0
    _stats_cache['value'] = None


def get_footer_links(settings):
    """Normalise the stored link list, tolerating older/partial rows."""
    raw = settings.get('footer_links') or []
    if not isinstance(raw, list):
        return []

    links = []
    for item in raw[:MAX_FOOTER_LINKS]:
        if not isinstance(item, dict):
            continue
        title = _clean(item.get('title'))
        url = _clean(item.get('url'))
        if not title or not url:
            continue
        links.append({
            'title': title,
            'description': _clean(item.get('description')),
            'url': url,
            'external': url.startswith(('http://', 'https://')),
        })
    return links


def get_business_hours(settings):
    """Opening hours as an ordered Mon–Sun list, only for days that are set."""
    raw = settings.get('business_hours') or {}
    if not isinstance(raw, dict):
        return []

    hours = []
    for key, label in WEEKDAYS:
        day = raw.get(key)
        if not isinstance(day, dict):
            continue
        closed = _truthy(day.get('closed'))
        opens = _clean(day.get('open'))
        closes = _clean(day.get('close'))
        if not closed and not (opens and closes):
            continue  # Day left blank: creator simply didn't fill it in.
        hours.append({
            'key': key,
            'label': label,
            'closed': closed,
            'opens': opens,
            'closes': closes,
            'schema_day': _SCHEMA_DAY[key],
        })
    return hours


def _build_address(settings):
    parts = {
        'street': _clean(settings.get('business_street')),
        'city': _clean(settings.get('business_city')),
        'region': _clean(settings.get('business_region')),
        'postal_code': _clean(settings.get('business_postal_code')),
        'country': _clean(settings.get('business_country')),
        'map_url': _clean(settings.get('business_map_url')),
    }
    ordered = [parts['street'], parts['city'], parts['region'], parts['postal_code'], parts['country']]
    parts['one_line'] = ', '.join(p for p in ordered if p)
    parts['has_value'] = bool(parts['one_line'])
    return parts


def _build_socials(settings):
    networks = [
        ('instagram', 'social_instagram'),
        ('twitter', 'social_twitter'),
        ('tiktok', 'social_tiktok'),
        ('youtube', 'social_youtube'),
    ]
    return [
        {'network': name, 'url': _clean(settings.get(key))}
        for name, key in networks
        if _clean(settings.get(key))
    ]


def build_site_footer(creator):
    """Resolve every footer block against the current viewer.

    Returns a dict the footer partial and the JSON-LD builder both read. Blocks
    the viewer may not see are absent, not merely flagged -- so a template bug
    cannot leak a gated detail.
    """
    if not creator:
        return {'enabled': False}

    settings = _load_settings(creator)
    viewer = _viewer_level()

    # Default on: a brand new store still gets a real footer rather than a
    # broken-looking empty bar.
    if 'footer_enabled' in settings and not _truthy(settings.get('footer_enabled')):
        return {'enabled': False}

    footer = {
        'enabled': True,
        'viewer_level': viewer,
        'store_name': creator.store_name or 'Nyota',
        'logo_url': _clean(settings.get('store_logo_url')) or _clean(settings.get('store_photo_url')),
        'tagline': _clean(settings.get('footer_tagline')),
        'year': datetime.utcnow().year,
        'legal_name': _clean(settings.get('footer_legal_name')),
        'tax_id': _clean(settings.get('footer_tax_id')),
        'founding_year': _clean(settings.get('footer_founding_year')),
        'show_credit': _truthy(settings.get('footer_credit_enabled')) if 'footer_credit_enabled' in settings else True,
        'about': None,
        'links': [],
        'contact': None,
        'address': None,
        'hours': None,
        'socials': [],
        'trust': None,
        'stats': None,
    }

    # --- About / bio ---
    if _truthy(settings.get('footer_about_enabled')):
        required = _visibility(settings, 'footer_about_visibility')
        text = _clean(settings.get('footer_about_text')) or _clean(settings.get('store_bio'))
        if text and _can_view(required, viewer):
            footer['about'] = {'text': text, 'visibility': required}

    # --- Custom links ---
    if _truthy(settings.get('footer_links_enabled')):
        footer['links'] = get_footer_links(settings)

    # --- Contact ---
    if _truthy(settings.get('footer_contact_enabled')):
        required = _visibility(settings, 'footer_contact_visibility')
        contact = {
            'email': _clean(settings.get('contact_email')),
            'phone': _clean(settings.get('contact_phone')),
            'whatsapp': _clean(settings.get('footer_contact_whatsapp')),
            'visibility': required,
        }
        if any([contact['email'], contact['phone'], contact['whatsapp']]) and _can_view(required, viewer):
            footer['contact'] = contact

    # --- Address ---
    if _truthy(settings.get('footer_address_enabled')):
        required = _visibility(settings, 'footer_address_visibility')
        address = _build_address(settings)
        if address['has_value'] and _can_view(required, viewer):
            address['visibility'] = required
            footer['address'] = address

    # --- Opening hours ---
    if _truthy(settings.get('footer_hours_enabled')):
        required = _visibility(settings, 'footer_hours_visibility')
        hours = get_business_hours(settings)
        if hours and _can_view(required, viewer):
            footer['hours'] = {'days': hours, 'note': _clean(settings.get('business_hours_note')), 'visibility': required}

    # --- Socials (always public: they are public profiles by definition) ---
    if _truthy(settings.get('footer_social_enabled')):
        footer['socials'] = _build_socials(settings)

    # --- Trust badges ---
    if _truthy(settings.get('footer_trust_enabled')):
        badges = {
            'secure_payment': _truthy(settings.get('footer_trust_secure_payment_enabled')),
            'instant_delivery': _truthy(settings.get('footer_trust_instant_delivery_enabled')),
            'support': _truthy(settings.get('footer_trust_support_enabled')),
            'support_text': _clean(settings.get('footer_trust_support_text')),
        }
        if any([badges['secure_payment'], badges['instant_delivery'], badges['support']]):
            footer['trust'] = badges

    # --- Social proof (real numbers only) ---
    if _truthy(settings.get('footer_stats_enabled')):
        stats = get_trust_stats()
        if stats['customers'] or stats['assets'] or stats['rating_count']:
            footer['stats'] = stats

    return footer


def build_structured_data(creator, footer, description=''):
    """schema.org @graph for the storefront: Organization + WebSite.

    Only what the current viewer can see is emitted, which for a crawler means
    only what the creator marked public. The Organization becomes a
    LocalBusiness when a public postal address exists, because that is what
    unlocks the local rich results (map pack, hours panel).
    """
    if not creator or not footer or not footer.get('enabled'):
        return None

    try:
        home = url_for('main.landing_page', _external=True)
    except RuntimeError:
        return None

    org_id = f'{home.rstrip("/")}/#organization'
    site_id = f'{home.rstrip("/")}/#website'

    address = footer.get('address')
    hours = footer.get('hours')
    contact = footer.get('contact')
    stats = footer.get('stats')

    org = {
        '@type': 'LocalBusiness' if address else 'Organization',
        '@id': org_id,
        'name': footer['store_name'],
        'url': home,
    }

    if footer.get('legal_name'):
        org['legalName'] = footer['legal_name']
    if footer.get('tax_id'):
        org['taxID'] = footer['tax_id']
    if footer.get('founding_year'):
        org['foundingDate'] = footer['founding_year']

    logo = _absolute(footer.get('logo_url')) or url_for('static', filename='img/default-og.jpg', _external=True)
    org['logo'] = logo
    org['image'] = logo

    if description:
        org['description'] = description
    elif footer.get('about'):
        org['description'] = footer['about']['text']

    if footer.get('socials'):
        org['sameAs'] = [s['url'] for s in footer['socials']]

    if contact:
        if contact.get('email'):
            org['email'] = contact['email']
        if contact.get('phone'):
            org['telephone'] = contact['phone']
            org['contactPoint'] = {
                '@type': 'ContactPoint',
                'telephone': contact['phone'],
                'contactType': 'customer support',
                **({'email': contact['email']} if contact.get('email') else {}),
            }

    if address:
        postal = {'@type': 'PostalAddress'}
        if address.get('street'):
            postal['streetAddress'] = address['street']
        if address.get('city'):
            postal['addressLocality'] = address['city']
        if address.get('region'):
            postal['addressRegion'] = address['region']
        if address.get('postal_code'):
            postal['postalCode'] = address['postal_code']
        if address.get('country'):
            postal['addressCountry'] = address['country']
        org['address'] = postal
        if address.get('map_url'):
            org['hasMap'] = address['map_url']

    if hours:
        spec = []
        for day in hours['days']:
            if day['closed']:
                continue
            spec.append({
                '@type': 'OpeningHoursSpecification',
                'dayOfWeek': day['schema_day'],
                'opens': day['opens'],
                'closes': day['closes'],
            })
        if spec:
            org['openingHoursSpecification'] = spec

    # Genuine ratings only -- inventing or padding an aggregateRating is exactly
    # what earns a structured-data manual action.
    if stats and stats.get('rating_count') and stats.get('rating_avg'):
        org['aggregateRating'] = {
            '@type': 'AggregateRating',
            'ratingValue': stats['rating_avg'],
            'ratingCount': stats['rating_count'],
            'bestRating': 5,
            'worstRating': 1,
        }

    website = {
        '@type': 'WebSite',
        '@id': site_id,
        'url': home,
        'name': footer['store_name'],
        'publisher': {'@id': org_id},
        # Lets Google render a sitelinks search box for the storefront.
        'potentialAction': {
            '@type': 'SearchAction',
            'target': {
                '@type': 'EntryPoint',
                'urlTemplate': f'{home.rstrip("/")}/?q={{search_term_string}}',
            },
            'query-input': 'required name=search_term_string',
        },
    }

    return {'@context': 'https://schema.org', '@graph': [org, website]}


def build_catalog_schema(assets, currency):
    """ItemList of the storefront's products, for the landing page.

    The Organization/WebSite graph tells a crawler who the store is; this tells
    it what the store sells, with the same price the card shows (via
    utils.pricing, so a donation asset can never be listed at a price the page
    never quotes). Emitted only for a listing a visitor actually sees.
    """
    if not assets:
        return None

    from utils.pricing import offer_schema

    try:
        home = url_for('main.landing_page', _external=True)
    except RuntimeError:
        return None

    elements = []
    for position, asset in enumerate(assets, start=1):
        try:
            item_url = url_for('main.asset_detail', slug=asset.slug, _external=True)
        except RuntimeError:
            continue
        product = {
            '@type': 'Product',
            'name': asset.title,
            'url': item_url,
            'offers': offer_schema(asset, currency, url=item_url),
        }
        if asset.description:
            product['description'] = _clean(asset.description)[:300]
        image = _absolute(asset.cover_image_url)
        if image:
            product['image'] = image
        elements.append({
            '@type': 'ListItem',
            'position': position,
            'item': product,
        })

    if not elements:
        return None

    return {
        '@context': 'https://schema.org',
        '@type': 'ItemList',
        '@id': f'{home.rstrip("/")}/#catalog',
        'url': home,
        'numberOfItems': len(elements),
        'itemListElement': elements,
    }
