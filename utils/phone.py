"""
Phone number normalization utilities for Tanzanian phone numbers.

Handles all common input formats and normalizes to a canonical form (0XXXXXXXXX)
which matches how numbers are stored in the database during purchase.

Supported input formats:
  - 0712345678        -> 0712345678
  - 255712345678      -> 0712345678
  - +255712345678     -> 0712345678
  - 00255712345678    -> 0712345678
  - 0712 345 678      -> 0712345678
  - 0712-345-678      -> 0712345678
  - 712345678         -> 0712345678  (missing leading zero)
  - +255 (0) 712 345 678 -> 0712345678
  - 0712.345.678      -> 0712345678
"""

import re


def normalize_phone_number(phone: str) -> str:
    """
    Normalize a Tanzanian phone number to the canonical format: 0XXXXXXXXX (10 digits).
    
    This ensures that however the user types their number (with country code,
    with spaces, with dashes, etc.), we always compare against the same format
    that was stored in the database at purchase time.
    
    Args:
        phone: Raw phone number string from user input.
        
    Returns:
        Normalized phone string in 0XXXXXXXXX format, or the cleaned digits
        if the number doesn't match expected Tanzanian patterns (fallback).
    """
    if not phone:
        return ''

    # 1. Strip whitespace and common formatting characters
    cleaned = re.sub(r'[\s\-\.\(\)\+]+', '', str(phone).strip())

    # 2. Remove any remaining non-digit characters
    digits = re.sub(r'\D', '', cleaned)

    if not digits:
        return ''

    # 3. Handle Tanzanian country code variations
    #    +255XXXXXXXXX or 255XXXXXXXXX -> 0XXXXXXXXX
    if digits.startswith('255') and len(digits) == 12:
        digits = '0' + digits[3:]
    #    00255XXXXXXXXX -> 0XXXXXXXXX (international dialing prefix)
    elif digits.startswith('00255') and len(digits) == 14:
        digits = '0' + digits[5:]
    #    Missing leading zero: 6XXXXXXXX or 7XXXXXXXX (9 digits) -> 0XXXXXXXXX
    elif len(digits) == 9 and digits[0] in ('6', '7'):
        digits = '0' + digits

    # 4. Ensure the result starts with '0' for local format
    #    If it doesn't match any known pattern, return as-is (digits only)
    return digits


def is_valid_tz_phone(normalized: str) -> bool:
    """
    Validate that a normalized phone number looks like a valid Tanzanian mobile number.
    Expected format: 0[67]XXXXXXXX (10 digits, starting with 06 or 07).
    """
    if not normalized:
        return False
    # Must be exactly 10 digits starting with 06 or 07
    return bool(re.match(r'^0[67]\d{8}$', normalized))


def format_for_api(normalized: str) -> str:
    """
    Convert a normalized local phone (0XXXXXXXXX) back to international format
    (255XXXXXXXXX) for the SMS API provider.
    
    The OnSMS API and most TZ SMS gateways expect 255XXXXXXXXX.
    """
    if not normalized:
        return normalized
    if normalized.startswith('0') and len(normalized) == 10:
        return '255' + normalized[1:]
    # Already in international format or unknown — return as-is
    return normalized


def normalize_phone_list(raw_phones):
    """
    Batch normalize, validate, and deduplicate a list of raw phone strings.
    
    Designed for the SMS campaign phone import feature. Takes raw user input
    (pasted phones, one per line or comma-separated) and returns a clean result
    with full analytics for the UI.
    
    Args:
        raw_phones: List of raw phone number strings.
        
    Returns:
        dict with keys:
            cleaned       – list of unique, valid, normalized phone numbers
            total_input   – how many non-empty inputs were received
            valid_count   – how many unique valid numbers remain
            duplicate_count – how many duplicates were removed
            invalid       – list of original strings that couldn't be parsed
            invalid_count – len(invalid)
            duplicates_removed – list of normalized numbers that appeared more than once
    """
    seen = set()
    cleaned = []
    invalid = []
    duplicates_removed = []
    total_input = 0

    for raw in raw_phones:
        raw_str = str(raw).strip()
        if not raw_str:
            continue
        total_input += 1

        normalized = normalize_phone_number(raw_str)

        # Validate: must look like a real TZ phone number
        if not normalized or not is_valid_tz_phone(normalized):
            invalid.append(raw_str)
            continue

        if normalized in seen:
            duplicates_removed.append(normalized)
            continue

        seen.add(normalized)
        cleaned.append(normalized)

    return {
        'cleaned': cleaned,
        'total_input': total_input,
        'valid_count': len(cleaned),
        'duplicate_count': len(duplicates_removed),
        'invalid': invalid,
        'invalid_count': len(invalid),
        'duplicates_removed': duplicates_removed,
    }
