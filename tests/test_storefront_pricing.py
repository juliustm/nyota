"""What a visitor is told a thing costs, before they commit to anything.

The storefront card, the asset page and the JSON-LD all price an asset through
utils.pricing. These tests pin the two things that must never drift: the mode
each asset shape resolves to, and the fact that the card's button uses the verb
of the button waiting on the asset page.
"""

from models.nyota import AssetStatus, AssetType

from utils.pricing import DONATION, FREE, FREE_DONATION, PAID, asset_pricing, offer_schema

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
