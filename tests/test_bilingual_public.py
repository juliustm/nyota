"""What a visitor actually reads, in the language they picked.

Every one of these goes through a real request and asserts on rendered HTML,
because that is the only place the whole chain shows up at once: the locale
selector, the payload, the templates and the meta tags a share preview quotes.
"""

from .conftest import make_asset, set_lang


ENGLISH_TITLE = 'Coffee Masterclass'
SWAHILI_TITLE = 'Darasa Kuu la Kahawa'


# --- The asset page ----------------------------------------------------------

def test_the_asset_page_reads_in_the_visitors_language(client, bilingual_asset):
    set_lang(client, 'sw')
    body = client.get('/coffee-masterclass').get_data(as_text=True)

    assert SWAHILI_TITLE in body
    assert 'Jifunze kuchoma kahawa nyumbani' in body
    assert '/media/covers/sw.webp' in body


def test_the_same_page_reads_in_english_for_an_english_visitor(client, bilingual_asset):
    set_lang(client, 'en')
    body = client.get('/coffee-masterclass').get_data(as_text=True)

    assert ENGLISH_TITLE in body
    assert '/media/covers/en.webp' in body


def test_switching_language_reserves_the_page(client, bilingual_asset):
    """The whole promise: change language, get the content in that language."""
    set_lang(client, 'en')
    assert ENGLISH_TITLE in client.get('/coffee-masterclass').get_data(as_text=True)

    client.get('/set-language/sw')
    assert SWAHILI_TITLE in client.get('/coffee-masterclass').get_data(as_text=True)


def test_an_untranslated_field_still_reads(client, bilingual_asset):
    """`story` has no Swahili. The page must show the English rather than a gap."""
    set_lang(client, 'sw')
    body = client.get('/coffee-masterclass').get_data(as_text=True)

    assert SWAHILI_TITLE in body
    assert 'About this course' in body


# --- The storefront ----------------------------------------------------------

def test_the_storefront_card_reads_in_the_visitors_language(client, bilingual_asset):
    set_lang(client, 'sw')
    body = client.get('/').get_data(as_text=True)

    assert SWAHILI_TITLE in body
    assert ENGLISH_TITLE not in body, 'the English title leaked onto a Swahili page'


def test_search_finds_an_asset_by_the_words_the_visitor_can_see(client, bilingual_asset):
    """A Swahili visitor types Swahili. Searching only the base columns would
    hide an asset from the person who just typed its name."""
    set_lang(client, 'sw')

    assert SWAHILI_TITLE in client.get('/?q=Jifunze').get_data(as_text=True)
    assert SWAHILI_TITLE in client.get('/?q=Kahawa').get_data(as_text=True)


def test_search_still_matches_the_original_wording(client, bilingual_asset):
    set_lang(client, 'sw')
    assert SWAHILI_TITLE in client.get('/?q=Coffee').get_data(as_text=True)


# --- ?lang= and hreflang -----------------------------------------------------

def test_a_link_can_carry_its_own_language(client, bilingual_asset):
    """A storefront link shared into a Swahili group opens in Swahili."""
    body = client.get('/coffee-masterclass?lang=sw').get_data(as_text=True)
    assert SWAHILI_TITLE in body


def test_a_language_from_a_link_sticks_for_the_rest_of_the_visit(client, bilingual_asset):
    client.get('/coffee-masterclass?lang=sw')
    assert SWAHILI_TITLE in client.get('/coffee-masterclass').get_data(as_text=True)


def test_an_unsupported_language_is_ignored_rather_than_obeyed(client, bilingual_asset):
    set_lang(client, 'en')
    body = client.get('/coffee-masterclass?lang=fr').get_data(as_text=True)
    assert ENGLISH_TITLE in body


def test_both_languages_are_offered_to_crawlers(client, bilingual_asset):
    body = client.get('/coffee-masterclass').get_data(as_text=True)

    assert 'hreflang="sw"' in body
    assert 'hreflang="en"' in body
    assert 'hreflang="x-default"' in body


# --- Share previews and structured data --------------------------------------

def test_the_share_preview_quotes_the_page_it_links_to(client, bilingual_asset):
    """A card that says one thing and a page that says another is worse than
    either — these come from the same resolved values."""
    import re

    set_lang(client, 'sw')
    body = client.get('/coffee-masterclass').get_data(as_text=True)
    # The template wraps long meta tags across lines.
    flat = re.sub(r'\s+', ' ', body)

    assert f'property="og:title" content="{SWAHILI_TITLE}"' in flat
    assert f'property="twitter:title" content="{SWAHILI_TITLE}"' in flat
    assert '/media/covers/sw.webp' in body


def test_the_product_markup_matches_the_visible_page(client, bilingual_asset):
    import json
    import re

    set_lang(client, 'sw')
    body = client.get('/coffee-masterclass').get_data(as_text=True)

    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', body, re.S)
    products = [json.loads(b) for b in blocks if '"Product"' in b]
    assert products, 'no Product markup on the page'
    assert products[0]['name'] == SWAHILI_TITLE


# --- The buyer's own shelf ---------------------------------------------------

def test_the_library_reads_in_the_buyers_language(client, creator, bilingual_asset):
    from models.nyota import Customer, Purchase, PurchaseStatus, db

    customer = Customer(whatsapp_number='0712345678', language='sw')
    db.session.add(customer)
    db.session.flush()
    db.session.add(Purchase(customer_id=customer.id, asset_id=bilingual_asset.id,
                            amount_paid=15000, status=PurchaseStatus.COMPLETED))
    db.session.commit()

    set_lang(client, 'sw')
    with client.session_transaction() as session:
        session['customer_phone'] = '0712345678'
        session['is_verified'] = True

    body = client.get('/library').get_data(as_text=True)
    assert SWAHILI_TITLE in body


# --- Checkout ----------------------------------------------------------------

def test_checkout_shows_the_same_words_as_the_page_before_it(client, bilingual_asset):
    set_lang(client, 'sw')
    body = client.get('/checkout/coffee-masterclass').get_data(as_text=True)

    assert SWAHILI_TITLE in body


# --- Nothing changes for an untranslated store -------------------------------

def test_an_untranslated_asset_reads_the_same_in_both_languages(client, creator):
    make_asset(creator, title='Plain Thing', slug='plain-thing', description='As written')

    for lang in ('en', 'sw'):
        body = client.get(f'/plain-thing?lang={lang}').get_data(as_text=True)
        assert 'Plain Thing' in body
        assert 'As written' in body
