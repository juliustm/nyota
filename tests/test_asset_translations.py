"""How an asset carries its second language, and what it refuses to carry.

The load-bearing promise is at the top: an asset with no translations serializes
exactly as it did before any of this existed. Everything after that is about the
translated payload staying honest — falling back per field, keeping the model's
own JSON untouched, and never letting a translation land on the wrong row.
"""

import json

from models.nyota import AssetStatus, AssetType, DigitalAsset

from .conftest import make_asset


# --- Nothing changes for an asset that has no translations -------------------

def test_an_untranslated_asset_serializes_exactly_as_before(asset):
    """The regression net for every existing asset in every existing store."""
    assert asset.translations is None
    assert asset.to_dict(lang='sw') == asset.to_dict()
    assert asset.to_dict(lang='en') == asset.to_dict()


def test_the_canonical_payload_is_the_default(bilingual_asset):
    """Callers that don't ask for a language get the creator's own words —
    which is what the admin, the CSV exports and the order records want."""
    canonical = bilingual_asset.to_dict()
    assert canonical['title'] == 'Coffee Masterclass'
    assert canonical['description'] == 'Learn to roast at home'


def test_asking_for_the_primary_language_is_the_canonical_payload(bilingual_asset):
    assert bilingual_asset.to_dict(lang='en') == bilingual_asset.to_dict()


# --- The translated payload --------------------------------------------------

def test_a_reader_gets_the_translated_asset(bilingual_asset):
    sw = bilingual_asset.to_dict(lang='sw')
    assert sw['title'] == 'Darasa Kuu la Kahawa'
    assert sw['description'] == 'Jifunze kuchoma kahawa nyumbani'
    assert sw['cover_image_url'] == '/media/covers/sw.webp'


def test_fallback_is_per_field_not_per_asset(bilingual_asset):
    """`story` was never translated. The rest of the page must not fall back
    with it, and it must not render blank."""
    sw = bilingual_asset.to_dict(lang='sw')
    assert sw['title'] == 'Darasa Kuu la Kahawa'
    assert sw['story'] == '# About this course'


def test_a_translated_row_does_not_touch_its_untranslated_sibling(bilingual_physical):
    sw = bilingual_physical.to_dict(lang='sw')
    names = {v['id']: v['name'] for v in sw['details']['variations']}
    assert names == {'v1': 'Nyekundu', 'v2': 'Blue'}


def test_a_type_only_translates_what_it_actually_has(creator):
    """Options belong to physical products. A digital product carrying a stray
    `variations` key is not a translatable surface, and the manifest — not the
    shape of the JSON that happens to be there — decides that."""
    asset = make_asset(
        creator, primary_language='en',
        details={'variations': [{'id': 'v1', 'name': 'Red'}]},
        translations={'sw': {'details': {'variations': {'v1': {'name': 'Nyekundu'}}}}},
    )
    assert asset.to_dict(lang='sw')['details']['variations'][0]['name'] == 'Red'


def test_serializing_never_mutates_the_model(bilingual_asset, bilingual_physical):
    bilingual_asset.to_dict(lang='sw')
    bilingual_physical.to_dict(lang='sw')

    assert bilingual_asset.title == 'Coffee Masterclass'
    assert bilingual_asset.custom_fields[0]['question'] == 'Your name'
    assert bilingual_physical.details['variations'][0]['name'] == 'Red'


def test_the_editor_gets_the_raw_blob(bilingual_asset):
    payload = bilingual_asset.to_dict(include_translations=True)
    assert payload['title'] == 'Coffee Masterclass'
    assert payload['primary_language'] == 'en'
    assert payload['translations']['sw']['title'] == 'Darasa Kuu la Kahawa'
    # ...and a payload that didn't ask for them doesn't leak them.
    assert 'translations' not in bilingual_asset.to_dict()


def test_rows_are_published_with_the_id_their_translation_is_filed_under(creator):
    """The editor has to address a row the moment it draws it, including on an
    asset that hasn't been saved since translations existed."""
    asset = make_asset(creator, custom_fields=[{'type': 'text', 'question': 'Your name'}])
    assert asset.to_dict()['custom_fields'][0]['key'] == 'your-name'


# --- Content items -----------------------------------------------------------

def test_a_content_item_reads_in_the_visitors_language(creator):
    from models.nyota import AssetFile, db

    asset = make_asset(creator, primary_language='en')
    db.session.add(AssetFile(
        asset=asset, title='Workbook', description='A PDF',
        storage_path='secure_uploads/w.pdf',
        translations={'sw': {'title': 'Kitabu cha kazi'}},
    ))
    db.session.commit()

    sw = asset.to_dict(lang='sw')['files'][0]
    assert sw['title'] == 'Kitabu cha kazi'
    assert sw['description'] == 'A PDF'          # untranslated, falls back
    assert asset.to_dict()['files'][0]['title'] == 'Workbook'


# --- Repeating events: the aliasing redaction depends on ---------------------

def _recurring(creator, **overrides):
    fields = dict(
        asset_type=AssetType.TICKET,
        status=AssetStatus.PUBLISHED,
        primary_language='en',
        details={'recurrence': {
            'enabled': True, 'interval': 1,
            'slots': [{'id': 's1', 'day': 4, 'time': '19:00',
                       'label': 'Evening class', 'note': 'Bring a laptop',
                       'link': 'https://zoom.us/j/1'}],
        }},
        translations={'sw': {'details': {'recurrence': {'slots': {
            's1': {'label': 'Darasa la jioni'}}}}}},
    )
    fields.update(overrides)
    return make_asset(creator, **fields)


def test_a_session_name_is_translated_everywhere_it_appears(creator):
    asset = _recurring(creator)
    sw = asset.to_dict(lang='sw')

    assert sw['details']['recurrence']['slots'][0]['label'] == 'Darasa la jioni'
    assert sw['eventDetails']['occurrences'][0]['label'] == 'Darasa la jioni'
    assert sw['eventDetails']['sessionLabel'] == 'Darasa la jioni'
    # Untranslated note still reads.
    assert sw['details']['recurrence']['slots'][0]['note'] == 'Bring a laptop'


def test_the_schedule_is_one_object_in_two_places(creator):
    """Load-bearing: the asset route redacts a private per-session join link by
    blanking it ONCE and relies on both copies being the same object. Localise
    them independently and non-buyers start seeing the real link."""
    asset = _recurring(creator)
    sw = asset.to_dict(lang='sw')

    assert (sw['details']['recurrence']['slots'][0]
            is sw['eventDetails']['recurrence']['slots'][0])


def test_a_non_buyer_never_sees_the_join_link_in_either_language(client, creator):
    _recurring(creator, slug='weekly-class')

    for lang in ('en', 'sw'):
        body = client.get(f'/weekly-class?lang={lang}').get_data(as_text=True)
        assert 'zoom.us/j/1' not in body, f'join link leaked in {lang}'


# --- What the save route accepts ---------------------------------------------

def _login(client, creator):
    with client.session_transaction() as session:
        session['creator_id'] = creator.id


def _save(client, **overrides):
    payload = {
        'action': 'publish',
        'asset': {'title': 'Coffee', 'description': 'Roasting'},
        'assetTypeEnum': 'DIGITAL_PRODUCT',
        'pricing': {'type': 'one-time', 'amount': 1000},
        'contentItems': [],
        'customFields': [],
        'primary_language': 'en',
    }
    payload.update(overrides)
    return client.post('/admin/assets/save', data={'asset_data': json.dumps(payload)},
                       headers={'Accept': 'application/json'})


def test_a_translation_round_trips_through_a_save(client, creator):
    _login(client, creator)
    response = _save(client, translations={'sw': {'title': '  Kahawa  ', 'description': 'Kuchoma'}})

    assert response.status_code == 200, response.get_data(as_text=True)
    saved = DigitalAsset.query.filter_by(title='Coffee').one()
    assert saved.primary_language == 'en'
    assert saved.translations['sw']['title'] == 'Kahawa'      # trimmed
    assert saved.to_dict(lang='sw')['title'] == 'Kahawa'


def test_the_primary_language_is_never_stored_twice(client, creator):
    """It lives in the columns. A second home is a second thing to disagree."""
    _login(client, creator)
    _save(client, translations={'en': {'title': 'Something else'}, 'sw': {'title': 'Kahawa'}})

    saved = DigitalAsset.query.filter_by(title='Coffee').one()
    assert 'en' not in saved.translations
    assert saved.translations['sw']['title'] == 'Kahawa'


def test_an_unknown_language_is_dropped(client, creator):
    _login(client, creator)
    _save(client, translations={'fr': {'title': 'Café'}, 'sw': {'title': 'Kahawa'}})

    saved = DigitalAsset.query.filter_by(title='Coffee').one()
    assert set(saved.translations) == {'sw'}


def test_an_unknown_field_is_dropped(client, creator):
    """The manifest decides what may be stored; anything else is not saved."""
    _login(client, creator)
    _save(client, translations={'sw': {'title': 'Kahawa', 'slug': 'hacked', 'price': '1'}})

    saved = DigitalAsset.query.filter_by(title='Coffee').one()
    assert set(saved.translations['sw']) == {'title'}


def test_an_empty_translation_is_dropped_rather_than_stored_blank(client, creator):
    """Stored blank, it would render as a gap; dropped, the original shows."""
    _login(client, creator)
    _save(client, translations={'sw': {'title': 'Kahawa', 'description': '   '}})

    saved = DigitalAsset.query.filter_by(title='Coffee').one()
    assert 'description' not in saved.translations['sw']
    assert saved.to_dict(lang='sw')['description'] == 'Roasting'


def test_an_oversize_translation_is_clamped(client, creator):
    _login(client, creator)
    _save(client, translations={'sw': {'title': 'K' * 500}})

    saved = DigitalAsset.query.filter_by(title='Coffee').one()
    assert len(saved.translations['sw']['title']) == 200


def test_a_cover_translation_must_be_one_of_our_own_media_paths(client, creator):
    _login(client, creator)
    _save(client, translations={'sw': {'cover_image_url': 'https://evil.example/x.jpg'}})

    saved = DigitalAsset.query.filter_by(title='Coffee').one()
    assert saved.translations is None or 'cover_image_url' not in (saved.translations.get('sw') or {})


def test_a_deleted_option_takes_its_translation_with_it(client, creator):
    _login(client, creator)
    _save(client,
          assetTypeEnum='PHYSICAL',
          variations=[{'id': 'v1', 'name': 'Red'}, {'id': 'v2', 'name': 'Blue'}],
          translations={'sw': {'details': {'variations': {
              'v1': {'name': 'Nyekundu'}, 'v2': {'name': 'Bluu'}}}}})
    saved = DigitalAsset.query.filter_by(title='Coffee').one()
    assert set(saved.translations['sw']['details']['variations']) == {'v1', 'v2'}

    # Drop v2 and save again: its translation must not linger.
    _save(client,
          asset={'id': saved.id, 'title': 'Coffee', 'description': 'Roasting'},
          assetTypeEnum='PHYSICAL',
          variations=[{'id': 'v1', 'name': 'Red'}],
          translations={'sw': {'details': {'variations': {
              'v1': {'name': 'Nyekundu'}, 'v2': {'name': 'Bluu'}}}}})
    saved = DigitalAsset.query.get(saved.id)
    assert set(saved.translations['sw']['details']['variations']) == {'v1'}


def test_duplicating_an_asset_keeps_both_languages(client, creator, bilingual_asset):
    """Otherwise duplicating silently throws away half the work."""
    _login(client, creator)
    response = client.post(f'/admin/api/assets/{bilingual_asset.id}/duplicate')

    assert response.status_code == 200, response.get_data(as_text=True)
    copy = DigitalAsset.query.filter(DigitalAsset.title.like('Copy of%')).one()
    assert copy.translations['sw']['title'] == 'Darasa Kuu la Kahawa'
    assert copy.primary_language == 'en'
