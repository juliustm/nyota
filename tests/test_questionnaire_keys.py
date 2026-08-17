"""The answer-storage key must never move, whatever language a buyer reads in.

`Purchase.ticket_data` is keyed by the question TEXT itself — the same string the
admin sees in the responses tab, the CSV export, and the buyer's saved delivery
details. Translating a question changes what a buyer READS and nothing else. Get
this wrong and answers to "Your name" and "Jina lako" become two different
columns for the same question, and no existing order can be read back.

The same applies to the snapshots inside an order: a variation or plan name is
recorded as the creator wrote it, not as the buyer happened to be reading it.
"""

import json

from models.nyota import (
    AssetStatus,
    AssetType,
    Purchase,
    PurchaseStatus,
    db,
)

from .conftest import make_asset, set_lang


QUESTIONS = [
    {'type': 'text', 'question': 'Your name', 'required': True},
    {'type': 'select', 'question': 'Size', 'options': ['Small', 'Large']},
]

TRANSLATIONS = {'sw': {'custom_fields': {
    'your-name': {'question': 'Jina lako'},
    'size': {'options': ['Ndogo', 'Kubwa']},
}}}


def _asset(creator, **overrides):
    fields = dict(
        title='Workshop', slug='workshop', price=0,
        asset_type=AssetType.TICKET, status=AssetStatus.PUBLISHED,
        primary_language='en', custom_fields=QUESTIONS, translations=TRANSLATIONS,
    )
    fields.update(overrides)
    return make_asset(creator, **fields)


# --- What the page publishes -------------------------------------------------

def test_the_question_text_is_never_replaced_by_its_translation(creator):
    """`question` is the key. The translated wording rides beside it."""
    asset = _asset(creator)
    field = asset.to_dict(lang='sw')['custom_fields'][0]

    assert field['question'] == 'Your name'
    assert field['question_display'] == 'Jina lako'


def test_choices_keep_their_values_and_only_change_their_labels(creator):
    asset = _asset(creator)
    field = asset.to_dict(lang='sw')['custom_fields'][1]

    assert field['options'] == ['Small', 'Large']
    assert field['options_display'] == ['Ndogo', 'Kubwa']


def test_a_partly_translated_choice_list_stays_aligned(creator):
    """Choices are matched by position. A short translation must fall back per
    position rather than sliding a label onto the wrong choice."""
    asset = _asset(creator, translations={'sw': {'custom_fields': {
        'size': {'options': ['Ndogo', '']},
    }}})
    field = asset.to_dict(lang='sw')['custom_fields'][1]

    assert field['options_display'] == ['Ndogo', 'Large']


def test_the_canonical_payload_has_no_display_wording(creator):
    """The admin's own view is the creator's words, full stop."""
    asset = _asset(creator)
    field = asset.to_dict()['custom_fields'][0]

    assert field['question'] == 'Your name'
    assert 'question_display' not in field


# --- What actually gets stored -----------------------------------------------

def _buy_and_answer(client, creator, lang, phone='0712345678'):
    asset = _asset(creator, slug=f'workshop-{lang}')
    customer_phone = phone

    from models.nyota import Customer
    customer = Customer(whatsapp_number=customer_phone, language=lang)
    db.session.add(customer)
    db.session.flush()
    purchase = Purchase(customer_id=customer.id, asset_id=asset.id,
                        amount_paid=0, status=PurchaseStatus.COMPLETED)
    db.session.add(purchase)
    db.session.commit()

    set_lang(client, lang)
    with client.session_transaction() as session:
        session['customer_phone'] = customer_phone
        session['is_verified'] = True

    response = client.post(
        f'/api/purchases/{purchase.id}/ticket-data',
        json={'Your name': 'Amina', 'Size': 'Small'},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return Purchase.query.get(purchase.id)


def test_answers_are_stored_under_the_same_keys_in_both_languages(client, creator):
    """The invariant the whole design turns on."""
    english = _buy_and_answer(client, creator, 'en', phone='0712345678')
    english_keys = set(english.ticket_data)

    swahili = _buy_and_answer(client, creator, 'sw', phone='0787654321')

    assert english_keys == set(swahili.ticket_data) == {'Your name', 'Size'}
    assert swahili.ticket_data['Your name'] == 'Amina'


def test_the_admin_reads_answers_back_regardless_of_the_buyers_language(client, creator):
    from routes import ticket_answers

    purchase = _buy_and_answer(client, creator, 'sw')

    assert ticket_answers(purchase.ticket_data) == {'Your name': 'Amina', 'Size': 'Small'}


# --- Order snapshots ---------------------------------------------------------

def _login(client, creator):
    with client.session_transaction() as session:
        session['creator_id'] = creator.id


def test_an_order_records_the_option_name_the_creator_wrote(client, creator, uza):
    """The order is a record of what was sold, not of what the buyer's screen
    happened to say — a merchant reconciling it should see one name."""
    asset = make_asset(
        creator, title='Beans', slug='beans', price=8000,
        asset_type=AssetType.PHYSICAL, status=AssetStatus.PUBLISHED,
        primary_language='en',
        details={'variations': [{'id': 'v1', 'name': 'Red', 'price': 8000}]},
        translations={'sw': {'details': {'variations': {'v1': {'name': 'Nyekundu'}}}}},
    )
    set_lang(client, 'sw')

    response = client.post('/api/initiate-payment', json={
        'phone_number': '0712345678', 'asset_id': asset.id,
        'channel_id': 'abc', 'variation_id': 'v1', 'quantity': 1,
    })

    assert response.status_code == 200, response.get_data(as_text=True)
    purchase = Purchase.query.filter_by(asset_id=asset.id).one()
    assert purchase.ticket_data['variation']['name'] == 'Red'


def test_a_plan_is_priced_and_named_from_our_own_record(client, creator, uza):
    """The client says WHICH plan; the name and the price come from the asset."""
    asset = make_asset(
        creator, title='Club', slug='club', price=5000,
        asset_type=AssetType.SUBSCRIPTION, status=AssetStatus.PUBLISHED,
        is_subscription=True, primary_language='en',
        details={'subscription_tiers': [
            {'id': 't1', 'name': 'Monthly', 'price': 5000, 'interval': 'monthly'},
        ]},
        translations={'sw': {'details': {'subscription_tiers': {
            't1': {'name': 'Kila Mwezi'}}}}},
    )
    set_lang(client, 'sw')

    response = client.post('/api/initiate-payment', json={
        'phone_number': '0712345678', 'asset_id': asset.id, 'channel_id': 'abc',
        # A hand-edited payload claiming a different name and a free price.
        'tier': {'id': 't1', 'name': 'Kila Mwezi', 'price': 1},
    })

    assert response.status_code == 200, response.get_data(as_text=True)
    purchase = Purchase.query.filter_by(asset_id=asset.id).one()
    assert purchase.ticket_data['tier']['name'] == 'Monthly'
    assert float(purchase.amount_paid) == 5000.0


# --- Saving through the admin ------------------------------------------------

def test_a_saved_question_keeps_its_text_and_gains_a_translation_handle(client, creator):
    from models.nyota import DigitalAsset

    _login(client, creator)
    payload = {
        'action': 'publish',
        'asset': {'title': 'Signup', 'description': 'x'},
        'assetTypeEnum': 'TICKET',
        'pricing': {'type': 'one-time', 'amount': 0},
        'contentItems': [],
        'customFields': [{'type': 'text', 'question': 'Your name', 'required': True}],
        'primary_language': 'en',
        'translations': {'sw': {'custom_fields': {'your-name': {'question': 'Jina lako'}}}},
    }
    response = client.post('/admin/assets/save', data={'asset_data': json.dumps(payload)},
                           headers={'Accept': 'application/json'})

    assert response.status_code == 200, response.get_data(as_text=True)
    saved = DigitalAsset.query.filter_by(title='Signup').one()
    assert saved.custom_fields[0]['question'] == 'Your name'
    assert saved.custom_fields[0]['key'] == 'your-name'
    assert saved.translations['sw']['custom_fields']['your-name']['question'] == 'Jina lako'
