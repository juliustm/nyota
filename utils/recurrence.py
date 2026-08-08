"""
Recurring event schedules ("every Thursday at 7pm").

A TICKET asset can either be a one-off (the legacy `event_date` column) or a
repeating series. The series lives in `asset.details['recurrence']` — JSON, so
no migration — and is the single source of truth for every date the public sees:
`DigitalAsset.to_dict()` resolves the NEXT occurrence and publishes it through
the same `eventDetails` contract the one-off path uses, so the asset page,
countdown, ICS/Google calendar, QR and structured data all shift forward on
their own.

Stored shape (see `normalize_recurrence` for the validation rules):

    {
      "enabled": true,
      "frequency": "weekly",
      "interval": 1,                       # every N weeks
      "slots": [                           # one per repeating day
        {"id": "s1", "day": 4, "time": "19:00", "duration": 90,
         "label": "Digital Masterclass", "link": "https://...", "note": "..."}
      ],
      "starts_on": "2026-08-01",           # optional first eligible date
      "until": "2026-12-31",               # optional last eligible date
      "skip_dates": ["2026-08-13"]         # occurrences to cancel
    }

`day` is 0=Sunday .. 6=Saturday so it matches JavaScript's `Date.getDay()` and
the ICS BYDAY table below without any conversion on the frontend.

All wall-clock values are the creator's local time (same convention as
`event_date`); absolute instants are only produced by resolving them against the
creator's IANA timezone, which keeps the series correct across DST shifts.
"""

from datetime import datetime, timedelta, timezone, date as date_cls

# Index 0 = Sunday, matching JS getDay() and the ICS BYDAY codes.
ICS_DAY_CODES = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA']
DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

MAX_SLOTS = 14           # a fortnight's worth of distinct sessions is plenty
DEFAULT_DURATION = 60    # minutes
MAX_DURATION = 60 * 24   # a slot cannot run longer than a day


def _clean_str(value, limit):
    if value is None:
        return ''
    return str(value).strip()[:limit]


def _parse_date(value):
    """'YYYY-MM-DD' -> date, or None."""
    if not value:
        return None
    if isinstance(value, date_cls) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.strptime(str(value).strip()[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def _parse_time(value):
    """'HH:MM' (or 'HH:MM:SS') -> (hour, minute), or None."""
    if not value:
        return None
    parts = str(value).strip().split(':')
    try:
        hour, minute = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def normalize_recurrence(raw):
    """
    Coerce an untrusted payload (admin form / stored JSON) into the canonical
    shape, or return None when there is nothing usable. A recurrence with no
    valid slot is not a recurrence — callers can treat None as "one-off".
    """
    if not isinstance(raw, dict):
        return None
    if not raw.get('enabled'):
        return None

    slots = []
    seen_ids = set()
    for i, item in enumerate(raw.get('slots') or []):
        if not isinstance(item, dict):
            continue
        try:
            day = int(item.get('day'))
        except (TypeError, ValueError):
            continue
        if not 0 <= day <= 6:
            continue
        parsed_time = _parse_time(item.get('time'))
        if not parsed_time:
            continue
        try:
            duration = int(item.get('duration') or DEFAULT_DURATION)
        except (TypeError, ValueError):
            duration = DEFAULT_DURATION
        duration = max(5, min(duration, MAX_DURATION))

        slot_id = _clean_str(item.get('id'), 40) or f's{i + 1}'
        while slot_id in seen_ids:            # ids drive ICS UIDs — keep unique
            slot_id = f'{slot_id}x'
        seen_ids.add(slot_id)

        slots.append({
            'id': slot_id,
            'day': day,
            'time': '%02d:%02d' % parsed_time,
            'duration': duration,
            'label': _clean_str(item.get('label'), 120),
            'link': _clean_str(item.get('link'), 512),
            'note': _clean_str(item.get('note'), 500),
        })
        if len(slots) >= MAX_SLOTS:
            break

    if not slots:
        return None

    slots.sort(key=lambda s: (s['day'], s['time']))

    try:
        interval = int(raw.get('interval') or 1)
    except (TypeError, ValueError):
        interval = 1
    interval = max(1, min(interval, 12))

    starts_on = _parse_date(raw.get('starts_on'))
    until = _parse_date(raw.get('until'))
    if starts_on and until and until < starts_on:
        until = None

    skip_dates = []
    for value in (raw.get('skip_dates') or []):
        parsed = _parse_date(value)
        if parsed and parsed.isoformat() not in skip_dates:
            skip_dates.append(parsed.isoformat())

    return {
        'enabled': True,
        'frequency': 'weekly',   # the only cadence today; kept explicit for later
        'interval': interval,
        'slots': slots,
        'starts_on': starts_on.isoformat() if starts_on else None,
        'until': until.isoformat() if until else None,
        'skip_dates': skip_dates[:60],
    }


def _anchor_date(recurrence):
    """
    The week the series counts intervals from. With `interval > 1` ("every other
    Thursday") the parity has to be stable, so it is measured from `starts_on`
    when set and from the Unix epoch's Sunday otherwise.
    """
    starts_on = _parse_date(recurrence.get('starts_on'))
    base = starts_on or date_cls(1970, 1, 4)  # 1970-01-04 was a Sunday
    return base - timedelta(days=(base.weekday() + 1) % 7)  # back to that Sunday


def occurrences(recurrence, tz, now=None, limit=6, horizon_days=400):
    """
    Upcoming occurrences of the series, soonest first.

    An occurrence stays "upcoming" until its END time so a session already in
    progress remains the one advertised instead of jumping to next week.
    Returns dicts carrying both the creator wall-clock and the absolute instant:

        {'date', 'time', 'start_local', 'end_local', 'utc', 'end_utc',
         'duration', 'slot', 'in_progress'}
    """
    recurrence = normalize_recurrence(recurrence)
    if not recurrence:
        return []

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    starts_on = _parse_date(recurrence.get('starts_on'))
    until = _parse_date(recurrence.get('until'))
    skip = set(recurrence.get('skip_dates') or [])
    interval = recurrence.get('interval') or 1
    anchor_sunday = _anchor_date(recurrence)

    # Start scanning a day early: an occurrence that began yesterday can still be
    # running, and timezone offsets can push a local date either side of "today".
    local_today = now.astimezone(tz).date()
    cursor = local_today - timedelta(days=1)
    if starts_on and starts_on > cursor:
        cursor = starts_on

    found = []
    end_scan = cursor + timedelta(days=horizon_days)
    while cursor <= end_scan and len(found) < limit:
        if until and cursor > until:
            break
        if cursor.isoformat() in skip:
            cursor += timedelta(days=1)
            continue

        if interval > 1:
            week_index = ((cursor - anchor_sunday).days // 7)
            if week_index % interval != 0:
                cursor += timedelta(days=1)
                continue

        js_day = (cursor.weekday() + 1) % 7  # Monday=0 -> Sunday=0 convention
        for slot in recurrence['slots']:
            if slot['day'] != js_day:
                continue
            hour, minute = _parse_time(slot['time'])
            start_local = datetime(cursor.year, cursor.month, cursor.day, hour, minute)
            end_local = start_local + timedelta(minutes=slot['duration'])
            start_utc = start_local.replace(tzinfo=tz).astimezone(timezone.utc)
            end_utc = end_local.replace(tzinfo=tz).astimezone(timezone.utc)
            if end_utc <= now:
                continue
            found.append({
                'date': start_local.strftime('%Y-%m-%d'),
                'time': start_local.strftime('%H:%M'),
                'start_local': start_local,
                'end_local': end_local,
                'utc': start_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'end_utc': end_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'duration': slot['duration'],
                'slot': slot,
                'in_progress': start_utc <= now < end_utc,
            })
            if len(found) >= limit:
                break
        cursor += timedelta(days=1)

    found.sort(key=lambda o: o['utc'])
    return found[:limit]


def next_occurrence(recurrence, tz, now=None):
    """The occurrence to advertise right now, or None once the series has ended."""
    upcoming = occurrences(recurrence, tz, now=now, limit=1)
    return upcoming[0] if upcoming else None


def first_occurrence_of_slot(recurrence, slot, tz, now=None):
    """
    The next date a single slot runs — the DTSTART an ICS RRULE needs so each
    repeating day gets its own correctly anchored VEVENT.
    """
    single = dict(normalize_recurrence(recurrence) or {})
    if not single:
        return None
    single['slots'] = [s for s in single['slots'] if s['id'] == slot.get('id')]
    if not single['slots']:
        return None
    return next_occurrence(single, tz, now=now)


def summary(recurrence):
    """
    Plain-English cadence, e.g. "Every Thursday at 19:00". Used for structured
    data and admin previews; the public page builds its own localized version
    from the structured slots.
    """
    recurrence = normalize_recurrence(recurrence)
    if not recurrence:
        return ''
    interval = recurrence.get('interval') or 1
    prefix = 'Every' if interval == 1 else f'Every {interval} weeks on'
    parts = []
    for slot in recurrence['slots']:
        piece = f"{DAY_NAMES[slot['day']]} at {slot['time']}"
        if slot['label']:
            piece += f" ({slot['label']})"
        parts.append(piece)
    return f"{prefix} {', '.join(parts)}"


def schedule_schema(recurrence, tz_name=None):
    """
    schema.org `Schedule` entries for an Event's `eventSchedule` — one per slot,
    so search engines understand the series rather than a single date.
    """
    recurrence = normalize_recurrence(recurrence)
    if not recurrence:
        return []
    schedules = []
    for slot in recurrence['slots']:
        entry = {
            '@type': 'Schedule',
            'repeatFrequency': 'P1W' if (recurrence.get('interval') or 1) == 1
                               else f"P{recurrence['interval']}W",
            'byDay': f"https://schema.org/{DAY_NAMES[slot['day']]}",
            'startTime': slot['time'],
            'duration': f"PT{slot['duration']}M",
        }
        if tz_name:
            entry['scheduleTimezone'] = tz_name
        if recurrence.get('starts_on'):
            entry['startDate'] = recurrence['starts_on']
        if recurrence.get('until'):
            entry['endDate'] = recurrence['until']
        if recurrence.get('skip_dates'):
            entry['exceptDate'] = recurrence['skip_dates']
        schedules.append(entry)
    return schedules
