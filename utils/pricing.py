"""
pricing.py

One place that decides how an asset's price reads to a visitor.

The storefront can charge in five different ways -- a fixed price, subscription
tiers, physical variations, an invited donation, a required donation -- and
three surfaces have to agree about them: the storefront card, the asset page,
and the JSON-LD a crawler reads. While each surface worked it out for itself
they drifted: a required-donation asset advertised "Free" on its card and
"Get this, Free!" on its button, then demanded a minimum contribution at
checkout.

`asset_pricing()` resolves an asset into ONE display mode plus the words that
belong to it, and every surface renders that. The card CTA it hands back is
deliberately the verb of the button waiting on the asset page, so the tap a
visitor is invited to make on the storefront is the tap they finish on the
next screen.
"""

# --- Display modes -----------------------------------------------------------
# FREE          costs nothing, nothing to contribute
# FREE_DONATION costs nothing, a contribution is invited but skippable
# DONATION      the contribution IS the charge (details.donation.mandatory)
# PAID          a real price; `from_price` marks it as the lowest of several
FREE = 'free'
FREE_DONATION = 'free_donation'
DONATION = 'donation'
PAID = 'paid'

# (paid CTA, free CTA) per asset type. Each mirrors the final CTA on the asset
# page -- cta_paid_<type> / cta_free_<type> -- in shorter, card-sized wording.
_CARD_CTA = {
    'video_series': ('card_cta_enroll', 'card_cta_start_free'),
    'ticket': ('card_cta_get_ticket', 'card_cta_reserve'),
    'digital_product': ('card_cta_buy', 'card_cta_get_free'),
    'physical': ('card_cta_order', 'card_cta_claim'),
    'subscription': ('card_cta_subscribe', 'card_cta_join_free'),
    'newsletter': ('card_cta_subscribe', 'card_cta_subscribe_free'),
}
_DEFAULT_CTA = ('card_cta_buy', 'card_cta_get_free')


def asset_type_key(asset):
    """Lowercase asset-type slug used to build translation keys."""
    a_type = getattr(asset, 'asset_type', None)
    name = getattr(a_type, 'name', None) or str(a_type or '')
    return name.lower() or 'digital_product'


def donation_config(asset):
    """The asset's donation block, or None when donations are off."""
    details = getattr(asset, 'details', None) or {}
    cfg = details.get('donation')
    if isinstance(cfg, dict) and cfg.get('enabled'):
        return cfg
    return None


def _to_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _tier_prices(asset):
    details = getattr(asset, 'details', None) or {}
    tiers = details.get('subscription_tiers') or []
    prices = [_to_float((t or {}).get('price')) for t in tiers if isinstance(t, dict)]
    return sorted(p for p in prices if p is not None)


def _variation_prices(asset, base_price):
    """Prices a physical buyer can actually pick. A variation without its own
    price falls back to the asset's base price, exactly as checkout does."""
    details = getattr(asset, 'details', None) or {}
    variations = [v for v in (details.get('variations') or []) if isinstance(v, dict)]
    sellable = [v for v in variations if not v.get('sold_out')]
    # Everything sold out still needs a price to show, so fall back to the lot.
    for group in (sellable, variations):
        prices = [
            _to_float(v.get('price'), base_price) if v.get('price') not in (None, '') else base_price
            for v in group
        ]
        prices = sorted(p for p in prices if p is not None)
        if prices:
            return prices
    return []


def asset_pricing(asset):
    """Resolve how `asset` should present its price.

    Returns a dict:
      mode        one of FREE / FREE_DONATION / DONATION / PAID
      amount      the number to show, or None when there is nothing to show
      from_price  True when `amount` is the lowest of several (show "From")
      is_free     True when a visitor can get in without paying anything
      cta_key     translation key for the storefront card's button
      note_key    translation key for the small line under the price, or None
      badge_key   translation key for the cover badge, or None
    """
    type_key = asset_type_key(asset)
    paid_cta, free_cta = _CARD_CTA.get(type_key, _DEFAULT_CTA)
    base_price = _to_float(getattr(asset, 'price', 0), 0.0) or 0.0

    result = {
        'mode': PAID,
        'amount': base_price,
        'from_price': False,
        'is_free': False,
        'cta_key': paid_cta,
        'note_key': None,
        'badge_key': None,
        'type_key': type_key,
    }

    # 1. Donations. A donation asset is always priced 0 at the base (routes.py
    #    coerces it), so this has to be decided before the free/paid split.
    donation = donation_config(asset)
    if donation and base_price == 0:
        minimum = _to_float(donation.get('min_amount'), 0.0) or 0.0
        if donation.get('mandatory'):
            result.update({
                'mode': DONATION,
                'amount': minimum if minimum > 0 else None,
                'from_price': minimum > 0,
                'cta_key': 'card_cta_donate',
                'note_key': None if minimum > 0 else 'donation_any_amount',
                'badge_key': 'label_donation',
            })
        else:
            result.update({
                'mode': FREE_DONATION,
                'amount': None,
                'is_free': True,
                'cta_key': free_cta,
                'note_key': 'donations_welcome',
                'badge_key': 'free',
            })
        return result

    # 2. Several prices to choose from: subscription tiers, physical variations.
    options = []
    if getattr(asset, 'is_subscription', False):
        options = _tier_prices(asset)
    elif type_key == 'physical':
        options = _variation_prices(asset, base_price)

    if options:
        lowest = options[0]
        result['amount'] = lowest
        result['from_price'] = len(set(options)) > 1
        if lowest == 0:
            result.update({
                'mode': FREE, 'is_free': True, 'cta_key': free_cta,
                'badge_key': None if result['from_price'] else 'free',
            })
        return result

    # 3. Plain free / plain price.
    if base_price == 0:
        result.update({
            'mode': FREE,
            'amount': None,
            'is_free': True,
            'cta_key': free_cta,
            'badge_key': 'free',
        })
    return result


def offer_schema(asset, currency, url=None):
    """schema.org Offer (or AggregateOffer) matching what the page displays.

    Never advertises a price the storefront doesn't show: a required donation
    with no minimum has no honest number, so it is published as 0 with the
    contribution left to the buyer, and a range becomes an AggregateOffer with
    a real lowPrice.
    """
    pricing = asset_pricing(asset)
    amount = pricing['amount'] or 0
    sold_out = _is_sold_out(asset)
    availability = 'https://schema.org/{}'.format('SoldOut' if sold_out else 'InStock')

    # An AggregateOffer only makes sense where a buyer really picks between
    # priced options (tiers, variations). A donation minimum is one offer with a
    # floor, not a range, so it stays a plain Offer at that floor.
    option_count = _option_count(asset)
    aggregate = pricing['from_price'] and pricing['mode'] != DONATION and option_count > 1

    offer = {
        '@type': 'AggregateOffer' if aggregate else 'Offer',
        'priceCurrency': currency,
        'availability': availability,
    }
    if aggregate:
        offer['lowPrice'] = f'{amount:.2f}'
        offer['offerCount'] = option_count
    else:
        offer['price'] = f'{amount:.2f}'
    if url:
        offer['url'] = url
    return offer


def _option_count(asset):
    if getattr(asset, 'is_subscription', False):
        return max(1, len(_tier_prices(asset)))
    details = getattr(asset, 'details', None) or {}
    return max(1, len([v for v in (details.get('variations') or []) if isinstance(v, dict)]))


def _is_sold_out(asset):
    """True only when every pickable variation of a physical product is gone."""
    if asset_type_key(asset) != 'physical':
        return False
    details = getattr(asset, 'details', None) or {}
    variations = [v for v in (details.get('variations') or []) if isinstance(v, dict)]
    return bool(variations) and all(v.get('sold_out') for v in variations)
