"""What a visitor is told a thing costs, before they commit to anything.

The storefront card, the asset page and the JSON-LD all price an asset through
utils.pricing. These tests pin the two things that must never drift: the mode
each asset shape resolves to, and the fact that the card's button uses the verb
of the button waiting on the asset page.
"""

from models.nyota import AssetStatus, AssetType

from utils.pricing import (
    DONATION,
    FREE,
    FREE_DONATION,
    PAID,
    asset_pricing,
    contribution_voice,
    offer_schema,
)

from .conftest import make_asset


def test_plain_price_reads_as_paid(creator):
    asset = make_asset(creator, price=15000)
    pricing = asset_pricing(asset)

    assert pricing['mode'] == PAID
    assert pricing['amount'] == 15000
    assert pricing['from_price'] is False
    assert pricing['badge_key'] is None
    assert pricing['cta_key'] == 'card_cta_buy'


def test_free_asset_is_labelled_free_on_the_card(creator):
    asset = make_asset(creator, price=0)
    pricing = asset_pricing(asset)

    assert pricing['mode'] == FREE
    assert pricing['is_free'] is True
    assert pricing['badge_key'] == 'free'
    assert pricing['cta_key'] == 'card_cta_get_free'


def test_optional_donation_stays_free_but_says_so(donation_asset):
    """min_amount is set but mandatory is False: still free to take."""
    pricing = asset_pricing(donation_asset)

    assert pricing['mode'] == FREE_DONATION
    assert pricing['is_free'] is True
    assert pricing['amount'] is None
    assert pricing['note_key'] == 'donations_welcome'
    assert pricing['badge_key'] == 'free'


def test_required_donation_advertises_its_minimum(creator):
    asset = make_asset(
        creator,
        price=0,
        details={'donation': {'enabled': True, 'mandatory': True, 'min_amount': 5000}},
    )
    pricing = asset_pricing(asset)

    # Never "Free" — checkout will refuse anything under the minimum.
    assert pricing['mode'] == DONATION
    assert pricing['is_free'] is False
    assert pricing['amount'] == 5000
    assert pricing['from_price'] is True
    assert pricing['cta_key'] == 'card_cta_donate'
    assert pricing['badge_key'] == 'label_donation'


def test_required_donation_without_a_minimum_quotes_no_number(creator):
    asset = make_asset(
        creator,
        price=0,
        details={'donation': {'enabled': True, 'mandatory': True, 'min_amount': 0}},
    )
    pricing = asset_pricing(asset)

    assert pricing['mode'] == DONATION
    assert pricing['amount'] is None
    assert pricing['note_key'] == 'donation_any_amount'


def test_subscription_shows_the_cheapest_tier_as_a_starting_price(creator):
    asset = make_asset(
        creator,
        price=0,
        is_subscription=True,
        asset_type=AssetType.SUBSCRIPTION,
        details={'subscription_tiers': [{'price': '25000'}, {'price': '10000'}]},
    )
    pricing = asset_pricing(asset)

    assert pricing['amount'] == 10000
    assert pricing['from_price'] is True
    assert pricing['cta_key'] == 'card_cta_subscribe'


def test_physical_variations_start_from_the_cheapest_option(creator):
    asset = make_asset(
        creator,
        price=5000,
        asset_type=AssetType.PHYSICAL,
        details={'variations': [{'name': 'S', 'price': None}, {'name': 'L', 'price': 8000}]},
    )
    pricing = asset_pricing(asset)

    # A variation without its own price falls back to the base price, as checkout does.
    assert pricing['amount'] == 5000
    assert pricing['from_price'] is True
    assert pricing['cta_key'] == 'card_cta_order'


def test_offer_schema_matches_the_displayed_price(creator):
    donation = make_asset(
        creator,
        price=0,
        details={'donation': {'enabled': True, 'mandatory': True, 'min_amount': 5000}},
    )
    offer = offer_schema(donation, 'TZS')

    # A minimum is a floor, not a range of things to pick between.
    assert offer['@type'] == 'Offer'
    assert offer['price'] == '5000.00'
    assert offer['priceCurrency'] == 'TZS'

    tiered = make_asset(
        creator,
        price=0,
        is_subscription=True,
        asset_type=AssetType.SUBSCRIPTION,
        details={'subscription_tiers': [{'price': '25000'}, {'price': '10000'}]},
    )
    aggregate = offer_schema(tiered, 'TZS')
    assert aggregate['@type'] == 'AggregateOffer'
    assert aggregate['lowPrice'] == '10000.00'
    assert aggregate['offerCount'] == 2


def _contribution(creator, **donation):
    cfg = {'enabled': True, 'mandatory': True, 'min_amount': 6000}
    cfg.update(donation)
    return make_asset(creator, price=0, details={'donation': cfg})


def test_a_plain_donation_still_reads_exactly_as_it_always_did(creator):
    """No CTA chosen, or the default one: nothing about the wording changes."""
    voice = contribution_voice(_contribution(creator))

    assert voice['is_default'] is True
    assert voice['preset'] == 'donate'
    # Nothing overrides the translation keys the surfaces already use.
    assert asset_pricing(_contribution(creator))['cta_label'] is None


def test_a_preset_replaces_the_button_on_a_required_contribution(creator):
    asset = _contribution(creator, cta='coffee')
    voice = contribution_voice(asset)

    assert voice['is_default'] is False
    # Swahili is the default language, and that is what a visitor here reads.
    assert voice['cta'] == 'Ninunulie Kahawa'
    # Paying is the way in, so the creator's verb IS the button.
    pricing = asset_pricing(asset)
    assert pricing['cta_label'] == 'Ninunulie Kahawa'
    # ...and no "DONATION" tag left over the cover to contradict it.
    assert pricing['badge_key'] is None


def test_an_optional_contribution_keeps_its_free_button(creator):
    """The item is still free to take, so only the invitation line changes."""
    asset = _contribution(creator, mandatory=False, cta='coffee')
    pricing = asset_pricing(asset)

    assert pricing['mode'] == FREE_DONATION
    assert pricing['cta_label'] is None
    assert pricing['note_label'] == 'Ninunulie Kahawa'


def test_a_creator_written_label_beats_the_preset(creator):
    asset = _contribution(creator, cta='coffee', cta_custom={'en': 'Back the demo', 'sw': 'Fadhili Demo'})

    assert contribution_voice(asset)['cta'] == 'Fadhili Demo'
    assert contribution_voice(asset)['preset'] == 'custom'


def test_one_written_language_is_read_by_everyone(creator):
    """A creator who filled in one side meant it to be read, not to vanish."""
    asset = _contribution(creator, cta_custom={'en': 'Back the demo', 'sw': ''})

    assert contribution_voice(asset)['cta'] == 'Back the demo'


def test_an_unknown_preset_falls_back_to_donate(creator):
    """A stale or hand-edited id must not render an empty button."""
    voice = contribution_voice(_contribution(creator, cta='not_a_preset'))

    assert voice['is_default'] is True
    assert voice['cta']


def test_an_asset_that_takes_no_contribution_has_no_voice(creator):
    assert contribution_voice(make_asset(creator, price=10000)) is None


def test_a_required_contribution_asks_for_an_amount_not_a_decision(creator):
    """The visitor is past deciding — the heading only asks how much."""
    required = contribution_voice(_contribution(creator))
    optional = contribution_voice(_contribution(creator, mandatory=False))

    assert required['title'] != optional['title']


def test_a_chosen_verb_reaches_the_storefront_card(client, creator):
    make_asset(
        creator,
        title='Karani Demo',
        slug='karani-demo',
        price=0,
        details={'donation': {'enabled': True, 'mandatory': True, 'min_amount': 6000, 'cta': 'coffee'}},
    )

    body = client.get('/', headers=ENGLISH).get_data(as_text=True)

    assert 'Buy me a coffee' in body
    # The generic verb it replaced must not survive anywhere on the card.
    assert 'Donate' not in body


def test_sold_out_goods_are_marked_sold_out_for_crawlers(creator):
    asset = make_asset(
        creator,
        price=5000,
        asset_type=AssetType.PHYSICAL,
        details={'variations': [{'name': 'S', 'price': 4000, 'sold_out': True}]},
    )
    assert offer_schema(asset, 'TZS')['availability'] == 'https://schema.org/SoldOut'


# A visitor outside Tanzania gets the English storefront; the default is Swahili.
ENGLISH = {'CF-IPCountry': 'US'}


def test_storefront_card_shows_free_and_the_action_it_leads_to(client, creator):
    make_asset(creator, price=0, title='Free thing', slug='free-thing')

    body = client.get('/', headers=ENGLISH).get_data(as_text=True)

    assert 'Free thing' in body
    assert 'Get it Free' in body
    # The card commits to an action now, not to a detour through "View Details".
    assert 'View Details' not in body


def test_storefront_card_shows_a_required_donation_minimum(client, creator):
    make_asset(
        creator,
        title='Support us',
        slug='support-us',
        price=0,
        details={'donation': {'enabled': True, 'mandatory': True, 'min_amount': 5000}},
    )

    body = client.get('/', headers=ENGLISH).get_data(as_text=True)

    assert 'Donate' in body
    assert '5,000' in body
    # It is priced 0 at the base, but nothing on the card may offer it for free.
    assert 'Get it Free' not in body


def test_swahili_is_the_default_for_the_storefront_card(client, creator):
    make_asset(creator, price=0, title='Kitu cha bure', slug='kitu-bure')

    body = client.get('/').get_data(as_text=True)

    assert 'Jipatie Bure' in body


def test_landing_page_publishes_a_product_list_for_crawlers(client, creator):
    make_asset(creator, title='Listed thing', slug='listed-thing', price=12000)

    body = client.get('/').get_data(as_text=True)

    assert '"@type": "ItemList"' in body
    assert '"12000.00"' in body


def test_search_results_are_kept_out_of_the_index_but_still_crawled(client, creator):
    make_asset(creator, title='Findable', slug='findable', price=1000)

    body = client.get('/?q=Findable').get_data(as_text=True)

    assert 'noindex, follow' in body
    # Every slice of the catalogue credits the storefront itself.
    assert 'rel="canonical" href="http://localhost/"' in body


def test_unlisted_asset_page_still_refuses_crawlers_entirely(client, creator):
    make_asset(creator, title='Hidden', slug='hidden', price=1000, status=AssetStatus.UNLISTED)

    body = client.get('/hidden').get_data(as_text=True)

    assert 'noindex, nofollow' in body


# --- Saving the chosen verb from the admin -----------------------------------

def _login(client, creator):
    with client.session_transaction() as session:
        session['creator_id'] = creator.id


def test_the_admin_can_save_a_chosen_verb(client, creator):
    import json

    from models.nyota import DigitalAsset

    _login(client, creator)
    payload = {
        'action': 'publish',
        'asset': {'title': 'Karani Demo', 'description': 'Buy me coffee, I show you a demo'},
        'assetTypeEnum': 'DIGITAL_PRODUCT',
        'pricing': {'type': 'one-time', 'amount': 0},
        'contentItems': [],
        'customFields': [],
        'donation': {
            'enabled': True,
            'mandatory': True,
            'min_amount': 6000,
            'suggested_amounts': [6000, 12000],
            'cta': 'coffee',
            'cta_custom': {'en': '  Back the demo  ', 'sw': ''},
        },
    }
    response = client.post('/admin/assets/save', data={'asset_data': json.dumps(payload)},
                           headers={'Accept': 'application/json'})

    assert response.status_code == 200, response.get_data(as_text=True)
    saved = DigitalAsset.query.filter_by(title='Karani Demo').one().details['donation']
    assert saved['cta'] == 'coffee'
    # Stored trimmed, and the empty side stays empty so it can fall back.
    assert saved['cta_custom'] == {'en': 'Back the demo', 'sw': ''}


def test_a_hand_edited_preset_id_is_refused_at_the_door(client, creator):
    import json

    from models.nyota import DigitalAsset

    _login(client, creator)
    payload = {
        'action': 'publish',
        'asset': {'title': 'Bad Preset', 'description': 'x'},
        'assetTypeEnum': 'DIGITAL_PRODUCT',
        'pricing': {'type': 'one-time', 'amount': 0},
        'contentItems': [],
        'customFields': [],
        'donation': {'enabled': True, 'mandatory': True, 'min_amount': 1000, 'cta': '<script>'},
    }
    client.post('/admin/assets/save', data={'asset_data': json.dumps(payload)},
                headers={'Accept': 'application/json'})

    saved = DigitalAsset.query.filter_by(title='Bad Preset').one()
    assert saved.details['donation']['cta'] == 'donate'


def test_the_admin_asset_page_offers_the_pool(client, creator):
    _login(client, creator)
    asset = _contribution(creator, cta='coffee')

    html = client.get(f'/admin/assets/{asset.id}/edit').get_data(as_text=True)

    assert 'pickCtaPreset' in html          # the picker rendered
    assert 'id="cta-presets"' in html       # ...with the pool to pick from
    assert 'Buy me a coffee' in html
