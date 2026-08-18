"""The two questions utils/i18n answers, and the catalogue cache under them.

These used to be answered longhand in a dozen places. The point of pinning them
here is that there is now exactly one ladder for creator-written label pairs and
one for asset fields, and everything else defers to them.
"""

import json

import pytest

from utils import i18n, translator


# --- The peer ladder: labels, donation verbs ---------------------------------

def test_a_reader_gets_their_own_language():
    assert i18n.pick_localized({'en': 'Course', 'sw': 'Kozi'}, 'sw') == 'Kozi'
    assert i18n.pick_localized({'en': 'Course', 'sw': 'Kozi'}, 'en') == 'Course'


def test_one_written_side_is_read_by_everyone():
    """A creator who filled in one box meant it to be read, not to vanish."""
    assert i18n.pick_localized({'en': 'Masterclass', 'sw': ''}, 'sw') == 'Masterclass'
    assert i18n.pick_localized({'en': '', 'sw': 'Darasa Kuu'}, 'en') == 'Darasa Kuu'


def test_whitespace_is_not_a_translation():
    """A stray space must not render an empty badge over a cover."""
    assert i18n.pick_localized({'en': 'Course', 'sw': '   '}, 'sw') == 'Course'


def test_nothing_written_reads_as_nothing():
    assert i18n.pick_localized({}, 'sw') == ''
    assert i18n.pick_localized(None, 'sw') == ''
    assert i18n.pick_localized('not a dict', 'sw') == ''


# --- The asset ladder: two rungs, never more ---------------------------------

def test_a_translation_wins_over_the_original():
    t = {'sw': {'title': 'Darasa'}}
    assert i18n.resolve(t, 'sw', 'title', 'Class') == 'Darasa'


def test_an_untranslated_field_falls_back_to_the_original():
    t = {'sw': {'title': 'Darasa'}}
    assert i18n.resolve(t, 'sw', 'story', 'The story') == 'The story'
    assert i18n.resolve(None, 'sw', 'title', 'Class') == 'Class'


def test_a_blank_translation_falls_back_rather_than_rendering_empty():
    t = {'sw': {'title': '   '}}
    assert i18n.resolve(t, 'sw', 'title', 'Class') == 'Class'


def test_nested_paths_resolve():
    t = {'sw': {'details': {'welcomeContent': 'Karibu'}}}
    assert i18n.resolve(t, 'sw', 'details.welcomeContent', 'Welcome') == 'Karibu'
    assert i18n.resolve(t, 'sw', 'details.benefits', 'Perks') == 'Perks'


# --- Language codes ----------------------------------------------------------

@pytest.mark.parametrize('raw,expected', [
    ('sw', 'sw'), ('EN', 'en'), ('en-US', 'en'), ('sw_TZ', 'sw'),
    ('fr-FR', None), ('', None), (None, None), ('nonsense', None),
])
def test_language_codes_are_normalised_or_refused(raw, expected):
    assert i18n.normalize_lang(raw) == expected


def test_current_lang_survives_having_no_request():
    """The background worker sends reminders with no request to read."""
    assert i18n.current_lang() == i18n.DEFAULT_LANGUAGE


# --- The catalogue cache -----------------------------------------------------

def test_a_catalogue_is_read_once_and_reused():
    translator._CATALOGS.clear()
    first = translator._catalog('sw')
    second = translator._catalog('sw')
    assert first is second, "the parsed catalogue should be reused, not re-read"


def test_a_missing_catalogue_does_not_thrash_the_disk():
    translator._CATALOGS.clear()
    assert translator._catalog('zz') is None
    # Remembered as missing, so it is not re-opened just to fail again.
    assert translator._CATALOGS['zz'] is translator._MISSING


def test_a_missing_language_falls_back_to_the_default_catalogue():
    translator._CATALOGS.clear()
    assert translator.translate_in('zz', 'my_library') == translator.translate_in(
        i18n.DEFAULT_LANGUAGE, 'my_library')


def test_an_unknown_key_returns_itself_so_it_can_be_spotted():
    assert translator.translate_in('en', 'definitely_not_a_real_key') == 'definitely_not_a_real_key'


def test_placeholders_are_substituted():
    out = translator.translate_in('en', 'meta_price_from', price='TZS 5,000')
    assert 'TZS 5,000' in out


def test_both_catalogues_carry_the_same_keys():
    """A key added to one language and forgotten in the other renders as the
    raw key to half the audience."""
    en = json.load(open('locales/en.json', encoding='utf-8'))
    sw = json.load(open('locales/sw.json', encoding='utf-8'))
    assert set(en) == set(sw), f"drifted: {set(en) ^ set(sw)}"


# --- The manifest ------------------------------------------------------------

def test_the_manifest_describes_only_what_a_type_actually_has():
    from models.nyota import AssetType

    physical = [c['path'] for c in i18n.translatable_collections(AssetType.PHYSICAL)]
    assert 'details.variations' in physical
    assert 'details.subscription_tiers' not in physical
    # Every type has a questionnaire.
    assert 'custom_fields' in physical


def test_the_wizard_manifest_covers_every_type():
    """The create wizard has no type yet — it must still describe every field."""
    paths = [c['path'] for c in i18n.translatable_collections(None)]
    assert 'details.recurrence.slots' in paths
    assert 'details.variations' in paths
    assert len(paths) == len(set(paths)), "the union must not repeat a collection"


def test_a_question_key_is_derived_from_its_text():
    """Derived, not minted at random, so a question written before translations
    existed lands on the same key the first time it is saved."""
    assert i18n.custom_field_key({'question': 'Your name'}) == 'your-name'
    assert i18n.custom_field_key({'key': 'kept', 'question': 'Your name'}) == 'kept'
    assert i18n.custom_field_key({}, 3) == 'q3'
