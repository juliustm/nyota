"""
translator.py

This module provides a simple, robust function for handling internationalization (i18n)
on the Python/backend side of the Nyota ✨ application. It allows us to translate
strings used in flash messages, API responses, and other server-generated content.

The catalogues are read once and kept in memory. They used to be opened and
JSON-parsed on every single call, which meant rendering one asset page -- 175
`translate()` calls in `asset_detail.html` alone -- did 175 file opens. They are
also located relative to this file rather than the process working directory, so
the app no longer has to be started from the repository root to find its own words.
"""

import json
import os

from utils.i18n import DEFAULT_LANGUAGE, current_lang

# locales/ sits beside this package, at the project root.
_LOCALES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'locales'
)

_CATALOGS = {}   # lang code -> {key: string}
_MTIMES = {}     # lang code -> mtime the cached copy was read at (debug only)

# Sentinel for "we tried this language and there is nothing usable there", so a
# missing locale file is not re-opened on every call just to fail again.
_MISSING = {}


def _debug():
    """True only while running under Flask's debug reloader."""
    try:
        from flask import current_app
        return bool(current_app and current_app.debug)
    except Exception:
        return False


def _catalog(lang_code):
    """The parsed catalogue for `lang_code`, or None when there isn't one.

    In debug the file's mtime is checked so editing a locale file shows up on
    the next reload; in production it is read exactly once per process.
    """
    path = os.path.join(_LOCALES_DIR, f'{lang_code}.json')

    cached = _CATALOGS.get(lang_code)
    if cached is not None and not _debug():
        return None if cached is _MISSING else cached

    if cached is not None and _debug():
        try:
            if os.path.getmtime(path) == _MTIMES.get(lang_code):
                return None if cached is _MISSING else cached
        except OSError:
            pass

    try:
        with open(path, 'r', encoding='utf-8') as f:
            catalog = json.load(f)
        try:
            _MTIMES[lang_code] = os.path.getmtime(path)
        except OSError:
            pass
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        _CATALOGS[lang_code] = _MISSING
        return None

    _CATALOGS[lang_code] = catalog
    return catalog


def translate_in(lang_code: str, key: str, **kwargs) -> str:
    """`translate`, but in a language you name rather than the request's.

    Needed wherever one response has to carry BOTH languages at once — seeding a
    bilingual questionnaire, say — which a request-scoped lookup can't express.
    """
    translations = _catalog(lang_code) or _catalog(DEFAULT_LANGUAGE)
    if translations is None:
        return key
    translated_string = translations.get(key, key)
    if kwargs:
        for var_name, var_value in kwargs.items():
            translated_string = translated_string.replace(f"{{{{ {var_name} }}}}", str(var_value))
    return translated_string


def translate(key: str, **kwargs) -> str:
    """
    Translates a key into the currently selected language, with variable replacement.
    This is the Python-side equivalent of the _() function used in templates.

    It reads the language code from Flask's global `g` object, which is set
    on each request by our application factory.

    Args:
        key (str): The translation key to look up (e.g., 'login_successful').
        **kwargs: A dictionary of variables to substitute into the translated string.
                  For example, `translate('welcome_user', name='Amina')`.

    Returns:
        str: The translated and formatted string.
    """
    lang_code = current_lang()

    translations = _catalog(lang_code)
    if translations is None:
        # Fall back to the default catalogue when the selected language is
        # missing or corrupt.
        translations = _catalog(DEFAULT_LANGUAGE)
    if translations is None:
        # Absolute fallback: if even the default file is gone, return the raw key.
        # This prevents a crash and helps developers spot the missing file.
        return key

    # Get the base translated string, or return the key itself if not found.
    # This helps developers identify which translation keys are missing.
    translated_string = translations.get(key, key)

    # Perform variable replacement for placeholders like {{ name }}
    if kwargs:
        for var_name, var_value in kwargs.items():
            placeholder = f"{{{{ {var_name} }}}}" # Jinja2-style placeholder e.g. {{ name }}
            translated_string = translated_string.replace(placeholder, str(var_value))

    return translated_string
