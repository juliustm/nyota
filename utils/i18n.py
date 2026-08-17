"""
i18n.py

Where the app decides *which language* it is speaking.

Two different questions live here, and they are not the same question:

1. "What language is this visitor reading?" -> `current_lang()`. One answer per
   request, taken from the session (see `main.get_locale`).

2. "This creator wrote the same thing twice -- which copy do I show?" ->
   `pick_localized()`. A creator who filled in only one side meant it to be
   read, not to disappear for half their visitors, so a missing side falls
   through to whichever side exists rather than rendering blank.

Both used to be written out longhand wherever they were needed: the language
pair `('en', 'sw')` appeared in a dozen places, and the fallback ladder was
copy-pasted into `utils/pricing.py`, `templates/user/index.html` and
`templates/user/asset_detail.html` -- three copies that could disagree about
what a half-translated asset should show. They agree now because there is one
of each.
"""

# The languages the storefront speaks. Everything that validates a language code
# -- the /set-language route, the checkout payload, the translation editor --
# checks against this, so adding a third language is a change here plus a new
# locales/<code>.json rather than a hunt through the codebase.
SUPPORTED_LANGUAGES = ('sw', 'en')

# Swahili, not English: the store serves Tanzania, and an unknown visitor is far
# likelier to read Swahili. `main.get_locale()` makes the same choice.
DEFAULT_LANGUAGE = 'sw'

# The order `pick_localized` searches after the visitor's own language. This is
# deliberately NOT SUPPORTED_LANGUAGES: a creator writing one side of a label
# pair overwhelmingly writes the English one first (it is the shorter word and
# the one the admin UI puts first), so English is the more useful second guess.
PEER_FALLBACK_ORDER = ('en', 'sw')

# A creator's own word for what an asset is ("Masterclass", "Darasa Kuu"). It
# renders as a badge over a cover on a phone, so it has to stay short.
LABEL_MAX_LEN = 40


def current_lang():
    """The language this request is being read in.

    Safe to call with no request at all -- the background worker sends renewal
    reminders outside any request context and must not blow up reaching for
    `g`. It gets the default, and callers who know better (a customer's own
    stored language, say) pass `lang` explicitly instead.
    """
    try:
        from flask import g, has_request_context
        if not has_request_context():
            return DEFAULT_LANGUAGE
        return getattr(g, 'language', None) or DEFAULT_LANGUAGE
    except Exception:
        return DEFAULT_LANGUAGE


def normalize_lang(code):
    """A supported language code, or None.

    Browsers and payment payloads send things like 'en-US', 'sw-TZ' or junk;
    this reduces them to something the app actually has words for.
    """
    if not code:
        return None
    code = str(code).strip().lower().replace('_', '-')
    if code in SUPPORTED_LANGUAGES:
        return code
    base = code.split('-')[0]
    return base if base in SUPPORTED_LANGUAGES else None


def resolve(translations, lang, path, base):
    """One creator-written field, in `lang`, falling back to what they wrote first.

    This is the ASSET ladder, and it is only two rungs deep -- unlike
    `pick_localized`, which searches every language. Here the base column *is*
    the creator's own text and is always populated, so there is never a reason
    to look at a third place: either this language has a translation or the
    original stands in for it.

    `path` is dotted and addresses the translation slot, e.g. 'title',
    'details.welcomeContent'. `base` is the canonical value the caller already
    has in hand.
    """
    slot = (translations or {}).get(lang)
    if not isinstance(slot, dict):
        return base
    for part in path.split('.'):
        if not isinstance(slot, dict):
            return base
        slot = slot.get(part)
    if slot is None:
        return base
    text = str(slot)
    return text if text.strip() else base


# --- What can be translated ----------------------------------------------------
#
# One manifest, read by two very different consumers: the sanitizer in
# `save_asset_from_form` (which rejects anything not listed here) and the admin
# translation editor (which renders a box per entry). They cannot drift apart
# because there is only one list. It is plain dicts rather than objects so it can
# be handed to the browser with |tojson, the way the CTA presets already are.
#
# `widget` tells the editor what to draw: a one-line box, a markdown editor, an
# image slot, or a list of choices. `max` is enforced server-side regardless.

_COMMON_FIELDS = (
    {'path': 'title',           'label': 'Title',             'widget': 'text',     'max': 200},
    {'path': 'description',     'label': 'Short description', 'widget': 'markdown', 'max': 2000},
    {'path': 'story',           'label': 'Full story',        'widget': 'markdown', 'max': 20000},
    {'path': 'cover_image_url', 'label': 'Cover image',       'widget': 'image',    'max': 512},
)

_TYPE_FIELDS = {
    'TICKET': (
        {'path': 'event_location', 'label': 'Venue', 'widget': 'text', 'max': 512},
        {'path': 'details.postPurchaseInstructions',
         'label': 'After-purchase instructions', 'widget': 'markdown', 'max': 5000},
    ),
    'SUBSCRIPTION': (
        {'path': 'details.welcomeContent', 'label': 'Welcome message', 'widget': 'markdown', 'max': 20000},
        {'path': 'details.benefits', 'label': "What's included", 'widget': 'markdown', 'max': 20000},
    ),
    'NEWSLETTER': (
        {'path': 'details.welcomeContent', 'label': 'Welcome message', 'widget': 'markdown', 'max': 20000},
        {'path': 'details.benefits', 'label': "What's included", 'widget': 'markdown', 'max': 20000},
        {'path': 'details.welcomeDescription', 'label': 'Welcome description', 'widget': 'text', 'max': 2000},
    ),
}

# Repeating rows. Translations are keyed by the row's own stable id, never by its
# position, so reordering or deleting an option can't hand its Swahili name to
# the row that took its place.
_TYPE_COLLECTIONS = {
    'PHYSICAL': (
        {'path': 'details.variations', 'label': 'Options', 'id_key': 'id', 'fields': (
            {'key': 'name', 'label': 'Option name', 'widget': 'text', 'max': 120},
        )},
    ),
    'SUBSCRIPTION': (
        {'path': 'details.subscription_tiers', 'label': 'Plans', 'id_key': 'id', 'fields': (
            {'key': 'name', 'label': 'Plan name', 'widget': 'text', 'max': 120},
            {'key': 'description', 'label': 'Plan description', 'widget': 'text', 'max': 500},
        )},
    ),
    'TICKET': (
        {'path': 'details.recurrence.slots', 'label': 'Sessions', 'id_key': 'id', 'fields': (
            {'key': 'label', 'label': 'Session name', 'widget': 'text', 'max': 120},
            {'key': 'note', 'label': 'Session note', 'widget': 'text', 'max': 500},
        )},
    ),
}

# The questionnaire exists on every asset type. Its `question` string is the KEY
# that answers are stored under (Purchase.ticket_data), so it can never change --
# the translation is display-only and lives beside it.
_UNIVERSAL_COLLECTIONS = (
    {'path': 'custom_fields', 'label': 'Questions', 'id_key': 'key', 'fields': (
        {'key': 'question', 'label': 'Question', 'widget': 'text', 'max': 200},
        {'key': 'options', 'label': 'Choices', 'widget': 'list', 'max': 120},
    )},
)

# The delivery questionnaire a new physical product starts with.
#
# These used to be resolved through translate() in the ADMIN's session language,
# which froze one language into visitor-facing data — and, because a question's
# text is the key its answers are stored under, froze it permanently. Seeding both
# languages at once means a physical product ships bilingual on day one and the
# answer key stops depending on which language the creator happened to be
# browsing in. The keys are the same ones translate() reads, so the wording stays
# in one place: locales/<lang>.json.
DELIVERY_QUESTION_DEFAULTS = (
    {'type': 'text',     'key': 'delivery_q_name',     'required': True},
    {'type': 'phone',    'key': 'delivery_q_phone',    'required': True},
    {'type': 'textarea', 'key': 'delivery_q_where',    'required': True},
    {'type': 'location', 'key': 'delivery_q_location', 'required': False},
)


def delivery_defaults(primary=None):
    """Starter delivery questions, canonical text plus the other language.

    Shaped exactly like the payload the save route expects, so the wizard can
    hand it straight back:
        [{type, question, key, required, translations: {<lang>: {question}}}]
    """
    from utils.translator import translate_in

    primary = normalize_lang(primary) or DEFAULT_LANGUAGE
    out = []
    for spec in DELIVERY_QUESTION_DEFAULTS:
        question = translate_in(primary, spec['key'])
        row = {
            'type': spec['type'],
            'question': question,
            'key': custom_field_key({'question': question}),
            'required': spec['required'],
            'translations': {},
        }
        for code in SUPPORTED_LANGUAGES:
            if code == primary:
                continue
            other = translate_in(code, spec['key'])
            if other and other != spec['key']:
                row['translations'][code] = {'question': other}
        out.append(row)
    return out


# Content items live in their own table with their own translations column.
FILE_FIELDS = (
    {'key': 'title', 'label': 'Title', 'widget': 'text', 'max': 255},
    {'key': 'description', 'label': 'Description', 'widget': 'text', 'max': 2000},
)


def _type_name(asset_type):
    """'TICKET' from an AssetType, a name, or None."""
    return getattr(asset_type, 'name', None) or str(asset_type or '').upper()


def _dedupe(specs, key):
    seen, out = set(), []
    for spec in specs:
        if spec[key] in seen:
            continue
        seen.add(spec[key])
        out.append(spec)
    return out


def translatable_fields(asset_type):
    """The single-value translatable fields for this asset type.

    `asset_type=None` means "type not decided yet" — the create wizard, which
    picks a type at step 1 — and returns the union across every type.
    """
    if asset_type is None:
        extra = [spec for specs in _TYPE_FIELDS.values() for spec in specs]
        return _dedupe(list(_COMMON_FIELDS) + extra, 'path')
    return list(_COMMON_FIELDS) + list(_TYPE_FIELDS.get(_type_name(asset_type), ()))


def translatable_collections(asset_type):
    """The repeating translatable rows for this asset type (see above for None)."""
    if asset_type is None:
        extra = [spec for specs in _TYPE_COLLECTIONS.values() for spec in specs]
        return _dedupe(extra + list(_UNIVERSAL_COLLECTIONS), 'path')
    return list(_TYPE_COLLECTIONS.get(_type_name(asset_type), ())) + list(_UNIVERSAL_COLLECTIONS)


LANGUAGE_LABELS = {'sw': 'Kiswahili', 'en': 'English'}


def manifest(asset_type, primary=None):
    """Everything the admin translation editor needs, ready for |tojson."""
    return {
        'languages': [{'code': code, 'label': LANGUAGE_LABELS.get(code, code.upper())}
                      for code in SUPPORTED_LANGUAGES],
        'fields': translatable_fields(asset_type),
        'collections': translatable_collections(asset_type),
        'primary': normalize_lang(primary) or DEFAULT_LANGUAGE,
    }


def custom_field_key(field, index=0):
    """The stable id a questionnaire question's translation is filed under.

    Derived from the question text rather than minted at random, so a question
    that predates this feature lands on the same key the moment it is saved --
    translations written before that save are not orphaned by it.
    """
    if not isinstance(field, dict):
        return f'q{index}'
    existing = str(field.get('key') or '').strip()
    if existing:
        return existing[:60]
    question = str(field.get('question') or '').strip()
    if question:
        from slugify import slugify
        slug = slugify(question)[:60]
        if slug:
            return slug
    return f'q{index}'


def pick_localized(mapping, lang=None):
    """Read one side of a `{'en': ..., 'sw': ...}` pair written by a creator.

    Used for the two label pairs that are genuine PEERS -- neither side is the
    original: `details['labels']` (the card's type badge) and
    `details['donation']['cta_custom']` (the pay-what-you-want verb). Returns
    '' when nothing was written at all.

    Whitespace-only counts as unwritten, so a stray space in one box can't
    render an empty badge where the other language's word belongs.
    """
    if not isinstance(mapping, dict):
        return ''
    for code in (lang or current_lang(),) + PEER_FALLBACK_ORDER:
        value = mapping.get(code)
        if value and str(value).strip():
            return str(value).strip()
    return ''
