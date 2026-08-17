"""The admin always sees the creator's own words.

Localisation is a projection applied when an asset is rendered FOR A VISITOR.
Everything the creator manages by — their asset list, their exports, the record
of an order, the product line the payment gateway reconciles against — has to
say the same thing every time, whatever language the admin's browser happens to
be set to. These tests run the admin with a Swahili session on purpose.
"""

from models.nyota import (
    AssetStatus,
    Customer,
    Purchase,
    PurchaseStatus,
    db,
)

from .conftest import make_asset, set_lang


def _login_as_admin_reading_swahili(client, creator):
    set_lang(client, 'sw')
    with client.session_transaction() as session:
        session['creator_id'] = creator.id


def test_the_asset_list_shows_what_the_creator_wrote(client, creator, bilingual_asset):
    _login_as_admin_reading_swahili(client, creator)
    body = client.get('/admin/assets').get_data(as_text=True)

    assert 'Coffee Masterclass' in body
    assert 'Darasa Kuu la Kahawa' not in body


def test_the_editor_opens_on_the_original(client, creator, bilingual_asset):
    """The boxes start on the language the columns hold; the switch moves them."""
    _login_as_admin_reading_swahili(client, creator)
    body = client.get(f'/admin/assets/{bilingual_asset.id}/edit').get_data(as_text=True)

    assert '&#34;primary_language&#34;: &#34;en&#34;' in body or '"primary_language": "en"' in body
    assert 'Content language' in body


def test_the_tooltip_payload_stays_canonical(client, creator, bilingual_asset):
    _login_as_admin_reading_swahili(client, creator)
    payload = client.get(f'/admin/api/tooltip/asset/{bilingual_asset.id}').get_json()

    assert payload['title'] == 'Coffee Masterclass'


def test_an_export_says_the_same_thing_every_time(client, creator, bilingual_asset):
    """A spreadsheet is compared across months. If its rows changed language
    with whoever downloaded it, two exports of one month wouldn't reconcile."""
    customer = Customer(whatsapp_number='0712345678', language='sw')
    db.session.add(customer)
    db.session.flush()
    db.session.add(Purchase(customer_id=customer.id, asset_id=bilingual_asset.id,
                            amount_paid=15000, status=PurchaseStatus.COMPLETED))
    db.session.commit()

    _login_as_admin_reading_swahili(client, creator)
    body = client.get('/admin/dashboard/export').get_data(as_text=True)

    assert 'Coffee Masterclass' in body
    assert 'Darasa Kuu la Kahawa' not in body


def test_the_payment_gateway_is_told_one_product_name(client, creator, uza):
    """Otherwise the same product reconciles under two different names in the
    merchant's reports, depending on the buyer's browser language."""
    asset = make_asset(
        creator, title='Coffee Masterclass', slug='cm', price=15000,
        status=AssetStatus.PUBLISHED, primary_language='en',
        translations={'sw': {'title': 'Darasa Kuu la Kahawa'}},
    )
    set_lang(client, 'sw')

    response = client.post('/api/initiate-payment', json={
        'phone_number': '0712345678', 'asset_id': asset.id, 'channel_id': 'abc',
    })

    assert response.status_code == 200, response.get_data(as_text=True)
    _, payload = uza[0]
    assert payload['products'][0]['name'] == 'Coffee Masterclass'


def test_admin_search_matches_the_creators_own_words(client, creator, bilingual_asset):
    _login_as_admin_reading_swahili(client, creator)
    body = client.get('/admin/assets?search=Coffee').get_data(as_text=True)

    assert 'Coffee Masterclass' in body
