"""Events that happen again and again — "every Thursday at 7pm".

A repeating TICKET has no fixed date: the schedule lives in
details['recurrence'] and the date every surface quotes is resolved on each
render. These tests pin the three things that must never drift — the schedule
the admin saves, the occurrence the page advertises, and the absolute instant
the calendar files are anchored on.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from models.nyota import AssetStatus, AssetType, DigitalAsset, db

from utils.recurrence import (
    next_occurrence,
    normalize_recurrence,
    occurrences,
    schedule_schema,
    summary,
)

from .conftest import make_asset

EAT = ZoneInfo('Africa/Nairobi')  # UTC+3, the store's default zone

THURSDAY = 4
SATURDAY = 6


def weekly(**overrides):
    """Every Thursday, 19:00, 90 minutes."""
    rec = {
        'enabled': True,
        'slots': [{'id': 's1', 'day': THURSDAY, 'time': '19:00', 'duration': 90,
                   'label': 'Digital Masterclass'}],
    }
    rec.update(overrides)
    return rec


def make_recurring_asset(creator, recurrence=None, **overrides):
    details = dict(overrides.pop('details', {}) or {})
    details['recurrence'] = recurrence if recurrence is not None else weekly()
    return make_asset(
        creator,
        title='Thursday Masterclass',
        asset_type=AssetType.TICKET,
        status=AssetStatus.PUBLISHED,
        event_location='https://zoom.us/j/12345',
        details=details,
        **overrides,
    )


# --- The stored schedule ----------------------------------------------------

def test_a_schedule_without_a_usable_day_is_not_a_recurrence():
    assert normalize_recurrence(None) is None
    assert normalize_recurrence({'enabled': True, 'slots': []}) is None
    # Junk days and times are dropped rather than saved half-broken.
    assert normalize_recurrence({'enabled': True, 'slots': [{'day': 9, 'time': '19:00'}]}) is None
    assert normalize_recurrence({'enabled': True, 'slots': [{'day': 4, 'time': 'lunchtime'}]}) is None
    # Switched off means one-off, whatever else is in the payload.
    assert normalize_recurrence({'enabled': False, 'slots': [{'day': 4, 'time': '19:00'}]}) is None


def test_a_schedule_is_normalized_and_sorted():
    rec = normalize_recurrence({
        'enabled': True,
        'interval': '2',
        'slots': [
            {'day': SATURDAY, 'time': '9:5', 'duration': '45', 'label': ' Clinic '},
            {'day': THURSDAY, 'time': '19:00'},
        ],
        'until': '2026-12-31',
    })

    assert [s['day'] for s in rec['slots']] == [THURSDAY, SATURDAY]
    assert rec['slots'][0]['duration'] == 60          # default length
    assert rec['slots'][1]['time'] == '09:05'         # zero-padded
    assert rec['slots'][1]['label'] == 'Clinic'       # trimmed
    assert rec['interval'] == 2
    assert rec['until'] == '2026-12-31'


# --- Which session is "next" ------------------------------------------------

def test_next_occurrence_is_the_coming_thursday():
    now = datetime(2026, 8, 10, 6, 0, tzinfo=timezone.utc)  # Monday
    nxt = next_occurrence(weekly(), EAT, now=now)

    assert nxt['date'] == '2026-08-13'                 # that Thursday
    assert nxt['time'] == '19:00'                      # creator wall-clock
    assert nxt['utc'] == '2026-08-13T16:00:00Z'        # 19:00 EAT == 16:00 UTC
    assert nxt['end_utc'] == '2026-08-13T17:30:00Z'    # 90 minutes later


def test_a_session_in_progress_is_still_the_one_advertised():
    """Ten minutes in, the page must not jump to next week."""
    now = datetime(2026, 8, 13, 16, 10, tzinfo=timezone.utc)
    nxt = next_occurrence(weekly(), EAT, now=now)

    assert nxt['date'] == '2026-08-13'
    assert nxt['in_progress'] is True


def test_the_date_rolls_over_once_the_session_has_finished():
    now = datetime(2026, 8, 13, 17, 31, tzinfo=timezone.utc)  # one minute after the end
    nxt = next_occurrence(weekly(), EAT, now=now)

    assert nxt['date'] == '2026-08-20'
    assert nxt['in_progress'] is False


def test_each_repeating_day_keeps_its_own_time_and_details():
    rec = weekly(slots=[
        {'id': 'thu', 'day': THURSDAY, 'time': '19:00', 'duration': 90, 'label': 'Masterclass',
         'link': 'https://zoom.us/j/thursday'},
        {'id': 'sat', 'day': SATURDAY, 'time': '10:00', 'duration': 60, 'label': 'Clinic'},
    ])
    now = datetime(2026, 8, 10, 6, 0, tzinfo=timezone.utc)
    upcoming = occurrences(rec, EAT, now=now, limit=3)

    assert [(o['date'], o['time'], o['slot']['label']) for o in upcoming] == [
        ('2026-08-13', '19:00', 'Masterclass'),
        ('2026-08-15', '10:00', 'Clinic'),
        ('2026-08-20', '19:00', 'Masterclass'),
    ]


def test_cancelled_dates_are_skipped_and_the_end_date_stops_the_series():
    now = datetime(2026, 8, 10, 6, 0, tzinfo=timezone.utc)

    skipped = occurrences(weekly(skip_dates=['2026-08-13']), EAT, now=now, limit=2)
    assert [o['date'] for o in skipped] == ['2026-08-20', '2026-08-27']

    ended = occurrences(weekly(until='2026-08-20'), EAT, now=now, limit=5)
    assert [o['date'] for o in ended] == ['2026-08-13', '2026-08-20']

    assert next_occurrence(weekly(until='2026-08-01'), EAT, now=now) is None


def test_every_other_week_keeps_its_parity_from_the_start_date():
    rec = weekly(interval=2, starts_on='2026-08-13')
    now = datetime(2026, 8, 10, 6, 0, tzinfo=timezone.utc)

    assert [o['date'] for o in occurrences(rec, EAT, now=now, limit=3)] == [
        '2026-08-13', '2026-08-27', '2026-09-10']


def test_the_wall_clock_survives_a_dst_shift():
    """A zone that changes offset must keep the session at the same local time."""
    berlin = ZoneInfo('Europe/Berlin')
    rec = weekly(slots=[{'id': 's1', 'day': THURSDAY, 'time': '19:00', 'duration': 60}])
    now = datetime(2026, 10, 20, 6, 0, tzinfo=timezone.utc)  # before the Oct 25 switch
    upcoming = occurrences(rec, berlin, now=now, limit=3)

    assert [o['time'] for o in upcoming] == ['19:00', '19:00', '19:00']
    assert upcoming[0]['utc'] == '2026-10-22T17:00:00Z'   # CEST, UTC+2
    assert upcoming[1]['utc'] == '2026-10-29T18:00:00Z'   # CET, UTC+1


# --- What the page is handed ------------------------------------------------

def test_the_asset_advertises_the_next_session_through_the_usual_keys(creator):
    """Everything downstream (display, ICS, QR, countdown) reads eventDetails."""
    asset = make_recurring_asset(creator)
    ev = asset.to_dict()['eventDetails']

    expected = next_occurrence(weekly(), EAT)
    assert ev['isRecurring'] is True
    assert ev['date'] == expected['date']
    assert ev['time'] == '19:00'
    assert ev['utc'] == expected['utc']
    assert ev['endUtc'] == expected['end_utc']
    assert ev['durationMinutes'] == 90
    assert ev['tzLabel'] == 'EAT'
    assert ev['tzOffsetMinutes'] == 180
    assert ev['sessionLabel'] == 'Digital Masterclass'
    assert ev['seriesEnded'] is False


def test_every_repeating_day_appears_in_the_published_occurrences(creator):
    """The frontend anchors one calendar rule per day, so each needs a session."""
    asset = make_recurring_asset(creator, weekly(slots=[
        {'id': 'thu', 'day': THURSDAY, 'time': '19:00'},
        {'id': 'sat', 'day': SATURDAY, 'time': '10:00'},
    ]))
    ev = asset.to_dict()['eventDetails']

    assert {o['slotId'] for o in ev['occurrences']} == {'thu', 'sat'}
    assert ev['occurrences'] == sorted(ev['occurrences'], key=lambda o: o['utc'])


def test_a_days_own_link_overrides_the_events_location(creator):
    """A Thursday Zoom room and a Saturday venue are different places."""
    thursday_only = weekly(slots=[
        {'id': 'thu', 'day': THURSDAY, 'time': '19:00', 'link': 'https://meet.example/thursday'},
    ])
    asset = make_recurring_asset(creator, thursday_only)
    ev = asset.to_dict()['eventDetails']

    assert ev['link'] == 'https://meet.example/thursday'
    assert ev['isOnline'] is True


def test_a_finished_series_says_so_instead_of_showing_a_stale_date(creator):
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    asset = make_recurring_asset(creator, weekly(until=yesterday))
    ev = asset.to_dict()['eventDetails']

    assert ev['seriesEnded'] is True
    assert ev['date'] is None
    assert ev['occurrences'] == []


def test_a_one_off_event_is_untouched_by_any_of_this(creator):
    asset = make_asset(
        creator,
        title='One night only',
        asset_type=AssetType.TICKET,
        event_date=datetime(2027, 6, 27, 18, 30),
        event_location='Nyota Hall',
    )
    ev = asset.to_dict()['eventDetails']

    assert ev['isRecurring'] is False
    assert ev['recurrence'] is None
    assert ev['date'] == '2027-06-27'
    assert ev['time'] == '18:30'
    assert ev['utc'] == '2027-06-27T15:30:00Z'
    assert ev['endUtc'] == '2027-06-27T16:30:00Z'   # default hour, for the calendar
    assert ev['link'] == 'Nyota Hall'


# --- Saving from the admin --------------------------------------------------

def test_saving_a_schedule_stores_it_and_mirrors_the_next_date(app, creator):
    """event_date stays populated so anything reading the column still works."""
    from routes import _apply_event_details

    asset = make_asset(creator, title='Masterclass', asset_type=AssetType.TICKET)
    _apply_event_details(asset, {
        'link': 'https://zoom.us/j/12345',
        'maxAttendees': '40',
        'recurrence': weekly(),
    })
    db.session.commit()

    stored = asset.details['recurrence']
    assert stored['slots'][0]['day'] == THURSDAY
    assert asset.max_attendees == 40
    assert asset.event_date.strftime('%Y-%m-%d') == next_occurrence(weekly(), EAT)['date']


def test_the_create_wizard_can_publish_a_repeating_event(client, creator):
    """End to end through the real endpoint: a brand-new asset with a schedule."""
    import json

    with client.session_transaction() as session:
        session['creator_id'] = creator.id

    payload = {
        'action': 'publish',
        'asset': {'title': 'Thursday Masterclass', 'description': 'Build live'},
        'assetTypeEnum': 'TICKET',
        'pricing': {'type': 'one-time', 'amount': 20000},
        'contentItems': [],
        'customFields': [],
        'eventDetails': {
            'link': 'https://zoom.us/j/12345',
            'maxAttendees': 40,
            'postPurchaseInstructions': 'Join 5 minutes early',
            'recurrence': weekly(),
        },
    }
    response = client.post('/admin/assets/save', data={'asset_data': json.dumps(payload)},
                           headers={'Accept': 'application/json'})

    assert response.status_code == 200, response.get_data(as_text=True)
    saved = DigitalAsset.query.filter_by(title='Thursday Masterclass').one()
    assert saved.details['recurrence']['slots'][0]['day'] == THURSDAY
    assert saved.details['postPurchaseInstructions'] == 'Join 5 minutes early'
    assert saved.to_dict()['eventDetails']['isRecurring'] is True


def test_turning_the_repeat_off_restores_a_plain_date(app, creator):
    from routes import _apply_event_details

    asset = make_recurring_asset(creator)
    _apply_event_details(asset, {
        'link': 'Nyota Hall',
        'date': '2027-01-14',
        'time': '18:00',
        'recurrence': {'enabled': False, 'slots': []},
    })
    db.session.commit()

    assert 'recurrence' not in asset.details
    assert asset.event_date == datetime(2027, 1, 14, 18, 0)
    assert asset.to_dict()['eventDetails']['isRecurring'] is False


# --- What crawlers and buyers see ------------------------------------------

def test_the_public_page_ships_the_schedule_and_marks_it_up(client, creator):
    asset = make_recurring_asset(creator)
    page = client.get(f'/{asset.slug}', follow_redirects=True).get_data(as_text=True)

    assert '"isRecurring": true' in page
    assert '"EventSeries"' in page
    assert 'https://schema.org/Thursday' in page


def test_a_private_join_link_is_still_hidden_from_non_buyers(client, creator):
    """Per-day links are as private as the main one until a ticket is bought."""
    asset = make_recurring_asset(creator, weekly(slots=[
        {'id': 'thu', 'day': THURSDAY, 'time': '19:00', 'link': 'https://meet.example/secret'},
    ]))
    page = client.get(f'/{asset.slug}', follow_redirects=True).get_data(as_text=True)

    assert 'meet.example/secret' not in page
    assert '"isOnline": true' in page


def test_the_cadence_reads_as_a_sentence_for_crawlers():
    assert summary(weekly()) == 'Every Thursday at 19:00 (Digital Masterclass)'

    schedules = schedule_schema(weekly(until='2026-12-31'), 'Africa/Nairobi')
    assert schedules[0]['repeatFrequency'] == 'P1W'
    assert schedules[0]['byDay'] == 'https://schema.org/Thursday'
    assert schedules[0]['duration'] == 'PT90M'
    assert schedules[0]['scheduleTimezone'] == 'Africa/Nairobi'
    assert schedules[0]['endDate'] == '2026-12-31'
