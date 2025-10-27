"""
translator.py

This module provides a simple, robust function for handling internationalization (i18n)
on the Python/backend side of the Nyota Digital application. It allows us to translate
strings used in flash messages, API responses, and other server-generated content.

It works in tandem with Flask-Babel, which handles translations within Jinja2 templates.
"""

import json
from flask import g

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
    # Use g.language, which is set on every request. Default to 'sw'.
    lang_code = getattr(g, 'language', 'sw')

    # Define file paths relative to the application root
    default_lang_path = 'locales/sw.json'
    selected_lang_path = f'locales/{lang_code}.json'

    try:
        with open(selected_lang_path, 'r', encoding='utf-8') as f:
            translations = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Fallback to English if the selected language file is missing or corrupt
        try:
            with open(default_lang_path, 'r', encoding='utf-8') as f:
                translations = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # Absolute fallback: if even the English file is gone, return the raw key.
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