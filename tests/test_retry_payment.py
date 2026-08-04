"""/api/retry-payment — the second chance a buyer gets when the first push fails.

It sends the number straight to the gateway and stores it on the session, so it
has to normalize exactly like the initial checkout does.
"""

from models.nyota import Customer, Purchase, PurchaseStatus, db

UZA_RETRY_URL = 'https://uza.co.tz/api/interface/embeddable/retry-payment'


def make_pending_purchase(asset, phone='0712345678'):
    customer = Customer(whatsapp_number=phone, language='sw')
    db.session.add(customer)
    db.session.flush()
    purchase = Purchase(
        customer_id=customer.id,
        asset_id=asset.id,
        amount_paid=10000,
        status=PurchaseStatus.FAILED,
        payment_gateway_ref='deal_123',
    )
    db.session.add(purchase)
    db.session.commit()
    return purchase


def test_retry_sends_the_canonical_number_to_the_gateway(client, asset, uza):
    purchase = make_pending_purchase(asset)

    response = client.post('/api/retry-payment', json={
        'deal_id': 'deal_123',
        'purchase_id': purchase.id,
        # A number saved by an older client, spaces and all.
        'phone_number': '+255 712 345 678',
    })

    assert response.status_code == 200
    assert response.get_json()['success'] is True

    retries = [payload for url, payload in uza if url == UZA_RETRY_URL]
    assert len(retries) == 1
    assert retries[0]['walletid'] == '0712345678'
    assert retries[0]['deal_id'] == 'deal_123'


def test_retry_stores_the_canonical_number_on_the_session(client, asset, uza):
    purchase = make_pending_purchase(asset)

    with client:
        from flask import session

        client.post('/api/retry-payment', json={
            'deal_id': 'deal_123',
            'purchase_id': purchase.id,
            'phone_number': '0712 345 678',
        })
        # A spaced number here would never match a stored purchase again.
        assert session['customer_phone'] == '0712345678'


def test_retry_reopens_the_purchase_as_pending(client, asset, uza):
    purchase = make_pending_purchase(asset)

    client.post('/api/retry-payment', json={
        'deal_id': 'deal_123',
        'purchase_id': purchase.id,
        'phone_number': '0712345678',
    })

    assert db.session.get(Purchase, purchase.id).status == PurchaseStatus.PENDING


def test_retry_without_a_phone_number_is_rejected(client, asset, uza):
    purchase = make_pending_purchase(asset)

    response = client.post('/api/retry-payment', json={
        'deal_id': 'deal_123',
        'purchase_id': purchase.id,
        'phone_number': '',
    })

    assert response.status_code == 400
    assert uza == []


def test_retry_for_an_unknown_purchase_is_rejected(client, asset, uza):
    response = client.post('/api/retry-payment', json={
        'deal_id': 'deal_123',
        'purchase_id': 999999,
        'phone_number': '0712345678',
    })

    assert response.status_code == 404
    assert uza == []
