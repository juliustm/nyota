"""Shared fixtures for the checkout tests.

The suite exercises the money path — /api/initiate-payment and /api/retry-payment —
against a throwaway SQLite file, with the UZA gateway stubbed out. Nothing here
touches the real database or the network.
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config  # noqa: E402
from main import create_app  # noqa: E402
from models.nyota import (  # noqa: E402
    AssetStatus,
    AssetType,
    Creator,
    DigitalAsset,
    db,
)


@pytest.fixture
def app():
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    class TestConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"
        # A test that walks the checkout twice must not hit "10 per minute".
        RATELIMIT_ENABLED = False
        SECRET_KEY = 'test-secret'

    application = create_app(TestConfig)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()
    os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def creator(app):
    """A creator with the payment gateway configured."""
    c = Creator(username='teststore', totp_secret='BASE32SECRET3232', store_name='Test Store')
    db.session.add(c)
    db.session.flush()
    c.set_setting('payment_uza_pk', 'pk_test_123')
    c.set_setting('payment_uza_currency', 'TZS')
    db.session.commit()
    return c


def make_asset(creator, **overrides):
    """A published, purchasable asset. Overrides map straight onto the model."""
    fields = dict(
        creator_id=creator.id,
        title='Test Asset',
        slug='test-asset-' + str(id(overrides)),
        description='A thing to buy',
        asset_type=AssetType.DIGITAL_PRODUCT,
        price=10000,
        status=AssetStatus.PUBLISHED,
    )
    fields.update(overrides)
    asset = DigitalAsset(**fields)
    db.session.add(asset)
    db.session.commit()
    return asset


@pytest.fixture
def asset(creator):
    return make_asset(creator)


@pytest.fixture
def donation_asset(creator):
    """Pay-what-you-want: free at base, the contribution is the charge."""
    return make_asset(
        creator,
        title='Support the work',
        slug='support-the-work',
        price=0,
        details={
            'donation': {
                'enabled': True,
                'min_amount': 6000,
                'mandatory': False,
                'suggested_amounts': [12000, 24000, 36000, 48000],
            }
        },
    )


class FakeUzaResponse:
    """Stand-in for the gateway's HTTP response."""

    status_code = 200

    def __init__(self, deal_id='deal_123'):
        self._deal_id = deal_id
        self.text = '{"data": {"order": {"id": "%s"}}}' % deal_id

    def json(self):
        return {
            'data': {
                'order': {
                    'id': self._deal_id,
                    'payment_message': 'Check your phone to complete payment.',
                }
            }
        }

    def raise_for_status(self):
        return None


@pytest.fixture
def uza(monkeypatch):
    """Capture what we send to the gateway instead of calling it.

    Yields a list of (url, payload) tuples in call order.
    """
    import routes

    calls = []

    def fake_post(url, json=None, timeout=None, **kwargs):
        calls.append((url, json))
        return FakeUzaResponse()

    def fake_put(url, json=None, timeout=None, **kwargs):
        calls.append((url, json))
        return FakeUzaResponse()

    monkeypatch.setattr(routes.requests, 'post', fake_post)
    monkeypatch.setattr(routes.requests, 'put', fake_put)
    return calls
