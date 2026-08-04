"""However a buyer types their number, it has to land on one canonical form.

Checkout now shows a fixed +255 prefix, so the browser sends 0XXXXXXXXX — but the
endpoint still has to survive every other shape, because saved numbers, retries and
older clients arrive in all of them.
"""

import pytest

from utils.phone import (
    format_for_api,
    is_valid_tz_phone,
    normalize_phone_list,
    normalize_phone_number,
)

CANONICAL = '0712345678'


@pytest.mark.parametrize('raw', [
    '0712345678',            # what checkout now sends
    '712345678',             # national part alone (no trunk zero)
    '255712345678',          # country code, no plus
    '+255712345678',         # full international
    '00255712345678',        # international dialling prefix
    '+255 712 345 678',      # spaced, as pasted from a contact card
    '0712 345 678',          # spaced local — the format we used to store
    '0712-345-678',
    '0712.345.678',
    '+255 (0) 712 345 678',  # the "(0)" convention
    '  0712345678  ',
])
def test_every_input_shape_normalizes_to_one_number(raw):
    assert normalize_phone_number(raw) == CANONICAL


def test_empty_input_is_empty():
    assert normalize_phone_number('') == ''
    assert normalize_phone_number(None) == ''
    assert normalize_phone_number('   ') == ''


def test_letters_are_stripped_not_trusted():
    assert normalize_phone_number('abc0712345678xyz') == CANONICAL


@pytest.mark.parametrize('raw,expected', [
    ('812345678', '812345678'),        # unfamiliar 9-digit string is left alone
    ('0812345678', '0812345678'),      # already local-looking, kept as typed
    ('255812345678', '0812345678'),    # a country code still means "make it local"
    ('254712345678', '254712345678'),  # a foreign number is not rewritten
    ('12345', '12345'),                # too short to interpret
])
def test_numbers_we_cannot_interpret_keep_their_shape(raw, expected):
    """Only recognizable Tanzanian mobile numbers get rewritten — anything else is
    handed back as digits so the caller's own validation decides."""
    assert normalize_phone_number(raw) == expected


@pytest.mark.parametrize('number,valid', [
    ('0712345678', True),
    ('0612345678', True),   # 06 mobile ranges
    ('0812345678', False),  # not a TZ mobile prefix
    ('071234567', False),   # too short
    ('07123456789', False),  # too long
    ('', False),
])
def test_validity_matches_tz_mobile_shape(number, valid):
    assert is_valid_tz_phone(number) is valid


def test_sms_api_wants_the_international_form():
    assert format_for_api(CANONICAL) == '255712345678'
    assert format_for_api('255712345678') == '255712345678'
    assert format_for_api('') == ''


def test_bulk_import_dedupes_across_formats():
    result = normalize_phone_list([
        '0712345678',
        '+255 712 345 678',   # same person, different shape
        '0754000111',
        'not-a-phone',
        '',
    ])
    assert result['cleaned'] == ['0712345678', '0754000111']
    assert result['valid_count'] == 2
    assert result['duplicate_count'] == 1
    assert result['invalid'] == ['not-a-phone']
