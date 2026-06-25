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
    #    Missing leading zero: 7XXXXXXXX (9 digits) -> 07XXXXXXXX
    elif len(digits) == 9 and digits[0] in ('6', '7'):
        digits = '0' + digits

    # 4. Ensure the result starts with '0' for local format
    #    If it doesn't match any known pattern, return as-is (digits only)
    return digits
