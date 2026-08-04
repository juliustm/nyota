"""End-to-end checks on /api/initiate-payment — the point where a visitor hands
over money after giving us nothing but a phone number.

Covers each pricing shape (fixed price, subscription tier, physical order,
donation) plus the phone handling that fronts all of them.
"""

import decimal

import pytest

from models.nyota import (
    AssetStatus,
    AssetType,
    Customer,
    Purchase,
    PurchaseStatus,
    db,
)

from .conftest import make_asset

UZA_ORDER_URL = 'https://uza.co.tz/api/interface/embeddable/order'


def initiate(client, asset, **overrides):
    payload = {
        'phone_number': '0712345678',
        'asset_id': asset.id,
        'channel_id': 'channel-abc',
        'language': 'sw',
    }
    payload.update(overrides)
    return client.post('/api/initiate-payment', json=payload)


def order_payload(uza_calls):
    """The payload of the last order we sent to the gateway."""
    orders = [payload for url, payload in uza_calls if url == UZA_ORDER_URL]
    assert orders, 'no order was sent to the gateway'
    return orders[-1]


# ---------------------------------------------------------------------------
# Fixed-price assets — the baseline that must not regress
# ---------------------------------------------------------------------------

def test_fixed_price_asset_charges_the_asset_price(client, asset, uza):
    response = initiate(client, asset)
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True
    assert body['deal_id'] == 'deal_123'

    purchase = Purchase.query.get(body['purchase_id'])
    assert purchase.amount_paid == decimal.Decimal('10000.00')
    assert purchase.status == PurchaseStatus.PENDING
    assert purchase.sse_channel_id == 'channel-abc'

    payload = order_payload(uza)
    assert payload['totalAmount'] == '10000.00'
    assert payload['products'][0]['quantity'] == 1
    assert payload['products'][0]['price'] == 10000.0


def test_unpublished_asset_cannot_be_bought_by_id(client, creator, uza):
    draft = make_asset(creator, slug='draft-asset', status=AssetStatus.DRAFT)
    response = initiate(client, draft)

    assert response.status_code == 404
    assert Purchase.query.count() == 0
    assert uza == []


def test_missing_channel_id_is_rejected(client, asset, uza):
    response = initiate(client, asset, channel_id=None)

    assert response.status_code == 400
    assert Purchase.query.count() == 0


# ---------------------------------------------------------------------------
# Phone handling — whatever shape arrives, one customer record
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('typed', [
    '0712345678',            # what checkout sends after the +255 field
    '712345678',             # national part alone
    '255712345678',
    '+255 712 345 678',
    '0712 345 678',          # the format older clients stored
])
def test_any_phone_format_resolves_to_one_customer(client, asset, uza, typed):
    response = initiate(client, asset, phone_number=typed)

    assert response.status_code == 200
    customers = Customer.query.all()
    assert len(customers) == 1
    assert customers[0].whatsapp_number == '0712345678'
    # The gateway is always given the canonical number, never what was typed.
    assert order_payload(uza)['payment']['walletid'] == '0712345678'


def test_repeat_buyer_is_not_duplicated_across_formats(client, creator, uza):
    first = make_asset(creator, slug='first-asset')
    second = make_asset(creator, slug='second-asset')

    initiate(client, first, phone_number='+255 712 345 678')
    initiate(client, second, phone_number='0712345678')

    assert Customer.query.count() == 1
    assert Purchase.query.count() == 2


def test_empty_phone_is_rejected(client, asset, uza):
    response = initiate(client, asset, phone_number='')

    assert response.status_code == 400
    assert Purchase.query.count() == 0
    assert uza == []


# ---------------------------------------------------------------------------
# Donations — flexible amounts, suggested amounts, minimums
# ---------------------------------------------------------------------------

def test_donation_charges_the_contribution_not_the_price(client, donation_asset, uza):
    response = initiate(client, donation_asset, contribution=24000)
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True

    purchase = Purchase.query.get(body['purchase_id'])
    assert purchase.amount_paid == decimal.Decimal('24000')

    # Donations bill as quantity <contribution> x unit price 1.
    payload = order_payload(uza)
    assert payload['totalAmount'] == '24000'
    assert payload['products'][0] == {
        'id': 8069,
        'name': 'Support the work',
        'quantity': 24000,
        'price': 1,
    }


def test_donation_accepts_an_amount_typed_as_a_string(client, donation_asset, uza):
    response = initiate(client, donation_asset, contribution='15000')

    assert response.status_code == 200
    assert Purchase.query.one().amount_paid == decimal.Decimal('15000')


def test_optional_donation_of_zero_grants_access_for_free(client, donation_asset, uza):
    response = initiate(client, donation_asset, contribution=0)
    body = response.get_json()

    assert response.status_code == 200
    assert body['is_free'] is True

    purchase = Purchase.query.get(body['purchase_id'])
    assert purchase.status == PurchaseStatus.COMPLETED
    assert purchase.amount_paid == decimal.Decimal('0')


def test_optional_donation_below_the_minimum_is_refused(client, donation_asset, uza):
    response = initiate(client, donation_asset, contribution=3000)

    assert response.status_code == 400
    assert 'minimum' in response.get_json()['message'].lower()
    assert Purchase.query.count() == 0
    assert uza == []


def test_mandatory_donation_cannot_be_skipped(client, creator, uza):
    asset = make_asset(
        creator,
        slug='mandatory-donation',
        price=0,
        details={'donation': {'enabled': True, 'min_amount': 6000, 'mandatory': True,
                              'suggested_amounts': [12000]}},
    )
    response = initiate(client, asset, contribution=0)

    assert response.status_code == 400
    assert Purchase.query.count() == 0


def test_mandatory_donation_with_no_minimum_still_needs_an_amount(client, creator, uza):
    asset = make_asset(
        creator,
        slug='mandatory-no-min',
        price=0,
        details={'donation': {'enabled': True, 'min_amount': 0, 'mandatory': True}},
    )

    assert initiate(client, asset, contribution=0).status_code == 400
    assert initiate(client, asset, contribution=500).status_code == 200


def test_negative_contribution_is_floored_not_credited(client, creator, uza):
    """A negative amount must never become a negative charge."""
    asset = make_asset(
        creator,
        slug='no-minimum-donation',
        price=0,
        details={'donation': {'enabled': True, 'min_amount': 0, 'mandatory': False}},
    )
    response = initiate(client, asset, contribution=-5000)
    body = response.get_json()

    assert response.status_code == 200
    assert body['is_free'] is True
    assert Purchase.query.one().amount_paid == decimal.Decimal('0')


def test_garbled_contribution_falls_back_to_zero(client, creator, uza):
    asset = make_asset(
        creator,
        slug='garbled-donation',
        price=0,
        details={'donation': {'enabled': True, 'min_amount': 0, 'mandatory': False}},
    )
    response = initiate(client, asset, contribution='abc')

    assert response.status_code == 200
    assert response.get_json()['is_free'] is True


def test_donation_ignores_a_price_left_on_the_asset(client, creator, uza):
    """Donation assets are free at base — a stale price must not be charged."""
    asset = make_asset(
        creator,
        slug='priced-donation',
        price=50000,
        details={'donation': {'enabled': True, 'min_amount': 0, 'mandatory': False}},
    )
    response = initiate(client, asset, contribution=7000)

    assert Purchase.query.one().amount_paid == decimal.Decimal('7000')
    assert order_payload(uza)['totalAmount'] == '7000'


def test_repeat_donation_is_allowed_after_a_completed_one(client, donation_asset, uza):
    """Owning the asset must not block a second contribution."""
    first = initiate(client, donation_asset, contribution=12000).get_json()
    purchase = Purchase.query.get(first['purchase_id'])
    purchase.status = PurchaseStatus.COMPLETED
    db.session.commit()

    response = initiate(client, donation_asset, contribution=12000)
    body = response.get_json()

    assert response.status_code == 200
    assert body.get('already_owned') is not True
    assert Purchase.query.count() == 2


def test_a_selected_tier_disables_donation_pricing(client, creator, uza):
    """Subscription tiers and donations never apply at the same time."""
    asset = make_asset(
        creator,
        slug='tiered-donation',
        price=0,
        is_subscription=True,
        details={
            'donation': {'enabled': True, 'min_amount': 6000, 'mandatory': True},
            'subscription_tiers': [{'name': 'Monthly', 'price': '5000'}],
        },
    )
    response = initiate(client, asset, tier={'name': 'Monthly', 'price': '5000'}, contribution=0)

    assert response.status_code == 200
    assert Purchase.query.one().amount_paid == decimal.Decimal('5000')


# ---------------------------------------------------------------------------
# Subscription tiers and physical goods — unchanged by the donation work
# ---------------------------------------------------------------------------

def test_tier_price_is_charged_and_snapshotted(client, creator, uza):
    asset = make_asset(
        creator,
        slug='subscription-asset',
        price=1000,
        is_subscription=True,
        details={'subscription_tiers': [{'name': 'Yearly', 'price': '36000'}]},
    )
    response = initiate(client, asset, tier={'name': 'Yearly', 'price': '36000'})

    purchase = Purchase.query.get(response.get_json()['purchase_id'])
    assert purchase.amount_paid == decimal.Decimal('36000')
    assert purchase.ticket_data['tier']['name'] == 'Yearly'


def test_tier_without_a_price_falls_back_to_the_asset_price(client, creator, uza):
    asset = make_asset(
        creator,
        slug='broken-tier',
        price=8000,
        is_subscription=True,
        details={'subscription_tiers': [{'name': 'Odd'}]},
    )
    response = initiate(client, asset, tier={'name': 'Odd'})

    assert Purchase.query.one().amount_paid == decimal.Decimal('8000.00')


def test_physical_order_uses_our_variation_price_not_the_clients(client, creator, uza):
    asset = make_asset(
        creator,
        slug='tshirt',
        asset_type=AssetType.PHYSICAL,
        price=20000,
        details={'variations': [
            {'id': 'v1', 'name': 'Small', 'price': 25000},
            {'id': 'v2', 'name': 'Large', 'price': 30000, 'sold_out': True},
        ]},
    )
    response = initiate(client, asset, variation_id='v1', quantity=3)
    body = response.get_json()

    purchase = Purchase.query.get(body['purchase_id'])
    assert purchase.amount_paid == decimal.Decimal('75000')
    assert purchase.ticket_data['quantity'] == 3
    assert purchase.ticket_data['variation']['name'] == 'Small'

    payload = order_payload(uza)
    assert payload['products'][0]['quantity'] == 3
    assert payload['products'][0]['price'] == 25000.0


def test_sold_out_variation_is_refused(client, creator, uza):
    asset = make_asset(
        creator,
        slug='sold-out-tshirt',
        asset_type=AssetType.PHYSICAL,
        price=20000,
        details={'variations': [{'id': 'v2', 'name': 'Large', 'price': 30000, 'sold_out': True}]},
    )
    response = initiate(client, asset, variation_id='v2', quantity=1)

    assert response.status_code == 400
    assert Purchase.query.count() == 0


def test_physical_order_needs_a_variation_when_the_asset_has_them(client, creator, uza):
    asset = make_asset(
        creator,
        slug='pick-one-tshirt',
        asset_type=AssetType.PHYSICAL,
        price=20000,
        details={'variations': [{'id': 'v1', 'name': 'Small', 'price': 25000}]},
    )
    response = initiate(client, asset, quantity=1)

    assert response.status_code == 400
    assert Purchase.query.count() == 0
