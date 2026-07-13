"""
timezones.py

Bridges the creator's wall-clock world (what the admin types into a
datetime-local input) and the database's world (naive datetimes that are
always UTC — see created_at/sent_at defaults using datetime.utcnow).

Anything the admin schedules must be converted local -> UTC on the way in and
UTC -> local on the way back out, or the background worker (which compares
against datetime.utcnow()) fires it at the wrong hour.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

# Matches the fallback used by DigitalAsset event handling.
DEFAULT_TZ = 'Africa/Nairobi'


def creator_tz_name(creator):
    """IANA timezone name configured by the creator, with a regional default."""
    name = None
    try:
        if creator:
            name = creator.get_setting('creator_timezone')
    except Exception:
        name = None
    if not name:
        return DEFAULT_TZ
    try:
        ZoneInfo(name)
    except Exception:
        return DEFAULT_TZ
    return name


def creator_tz(creator):
    return ZoneInfo(creator_tz_name(creator))


def local_to_utc(naive_local, creator):
    """Creator wall-clock -> naive UTC, for storage/comparison."""
    if naive_local is None:
        return None
    aware = naive_local.replace(tzinfo=creator_tz(creator))
    return aware.astimezone(ZoneInfo('UTC')).replace(tzinfo=None)


def utc_to_local(naive_utc, creator):
    """Naive UTC from the DB -> creator wall-clock, for display/editing."""
    if naive_utc is None:
        return None
    aware = naive_utc.replace(tzinfo=ZoneInfo('UTC'))
    return aware.astimezone(creator_tz(creator)).replace(tzinfo=None)


def add_days_local(naive_utc, days, creator):
    """
    Advance a stored UTC instant by N days *in the creator's timezone*, so a
    campaign set for 09:00 local keeps firing at 09:00 local across DST shifts.
    """
    from datetime import timedelta
    local = utc_to_local(naive_utc, creator)
    return local_to_utc(local + timedelta(days=days), creator)


def local_now(creator):
    return utc_to_local(datetime.utcnow(), creator)
