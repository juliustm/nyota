"""The two surfaces where money changes hands have to render, with the phone
prefix and the donation controls actually present in the HTML."""

from .conftest import make_asset


def test_asset_page_renders_the_prefixed_phone_field(client, donation_asset):
    response = client.get(f'/{donation_asset.slug}')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    # Fixed country code, so a buyer types only the national digits.
    assert '+255' in html
    assert 'field-group__prefix' in html
    assert 'placeholder="712 345 678"' in html
    # The prefix owns its own space instead of floating over the input.
    assert 'formatPhoneNumber()' in html


def test_asset_page_renders_the_donation_controls(client, donation_asset):
    html = client.get(f'/{donation_asset.slug}').get_data(as_text=True)

    assert 'suggestedAmounts' in html      # quick picks come from the sanitized list
    assert 'pickAmount(amt)' in html
    assert 'amount-chip' in html
    assert 'formatAmount(donationMin)' in html


def test_checkout_page_renders_the_same_controls(client, donation_asset):
    response = client.get(f'/checkout/{donation_asset.slug}')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '+255' in html
    assert 'placeholder="712 345 678"' in html
    assert 'suggestedAmounts' in html
    assert 'pickAmount(amt)' in html


def test_checkout_page_renders_for_a_plain_paid_asset(client, asset):
    response = client.get(f'/checkout/{asset.slug}')

    assert response.status_code == 200
    assert '+255' in response.get_data(as_text=True)


def _coffee_asset(creator, **donation):
    """A contribution asset whose creator wrote their own button label."""
    cfg = {
        'enabled': True,
        'mandatory': True,
        'min_amount': 6000,
        'suggested_amounts': [6000, 12000],
        'cta': 'coffee',
        'cta_custom': {'en': "Let's grab a coffee", 'sw': 'Tunywe Kahawa'},
    }
    cfg.update(donation)
    return make_asset(creator, slug='karani-demo', price=0, details={'donation': cfg})


def test_asset_page_speaks_the_creators_chosen_verb(client, creator):
    asset = _coffee_asset(creator)
    html = client.get(f'/{asset.slug}').get_data(as_text=True)

    # Swahili is the default, so that is the side a visitor here reads.
    assert 'Tunywe Kahawa' in html
    assert 'Changia' not in html


def test_checkout_page_speaks_the_creators_chosen_verb(client, creator):
    asset = _coffee_asset(creator)
    html = client.get(f'/checkout/{asset.slug}').get_data(as_text=True)

    assert 'Tunywe Kahawa' in html


def test_an_apostrophe_in_the_label_cannot_break_the_button(client, creator):
    """The label goes into an Alpine expression, so it is escaped as JSON —
    "Let's grab a coffee" must not terminate the attribute's string."""
    asset = _coffee_asset(creator)
    html = client.get(f'/{asset.slug}', headers={'CF-IPCountry': 'US'}).get_data(as_text=True)

    assert "Let\\u0027s grab a coffee" in html
    # The raw apostrophe never lands inside the x-text expression.
    assert "x-text='Let's" not in html


def test_physical_asset_page_renders(client, creator):
    """Physical products share the phone field but never show donation controls."""
    from models.nyota import AssetType

    physical = make_asset(
        creator,
        slug='tshirt-page',
        asset_type=AssetType.PHYSICAL,
        price=20000,
        details={'variations': [{'id': 'v1', 'name': 'Small', 'price': 25000}]},
    )
    response = client.get(f'/{physical.slug}')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '+255' in html
    # The option picker and the quantity stepper live on the page itself, beside the
    # photos — a buyer must never have to open the payment form to discover them.
    assert 'opt-row' in html
    assert 'qty-btn' in html
    assert '$store.order.variations' in html


def test_non_physical_asset_page_has_no_option_picker(client, asset):
    """The picker is for goods only — nothing else has variations to choose."""
    html = client.get(f'/{asset.slug}').get_data(as_text=True)

    assert 'opt-row' not in html
    assert 'qty-btn' not in html
