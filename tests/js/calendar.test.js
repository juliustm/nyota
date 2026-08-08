// What lands in a buyer's calendar when they hit "Save to Calendar" or scan the
// QR code — for a one-off event and for a repeating series.
//
// The rules that matter: the entry is anchored on the absolute UTC instant the
// server resolved (never a floating local time), a repeating event carries an
// RRULE so the whole series is saved rather than one date, and each repeating
// day keeps its own time, length, title and link.

const assert = require('assert');
const { loadMain } = require('./load_main');

const { registry } = loadMain();

let failures = 0;
function test(name, fn) {
    try {
        fn();
    } catch (err) {
        failures++;
        console.error(`  FAIL ${name}\n       ${err.message}`);
    }
}

// A component instance holding the asset the server would have shipped.
function detail(eventDetails, extra = {}) {
    const component = registry.assetDetail('TZS');
    component.asset = Object.assign({
        id: 7,
        title: 'Digital Masterclass',
        slug: 'digital-masterclass',
        description: 'Build something live.',
        asset_type: 'TICKET',
        details: {},
        files: [],
        eventDetails
    }, extra);
    return component;
}

const ONE_OFF = {
    link: 'https://zoom.us/j/12345',
    isOnline: true,
    date: '2027-06-27',
    time: '18:30',
    utc: '2027-06-27T15:30:00Z',
    endUtc: '2027-06-27T16:30:00Z',
    durationMinutes: 60,
    tzLabel: 'EAT',
    tzOffsetMinutes: 180,
    isRecurring: false,
    recurrence: null,
    occurrences: []
};

// Every Thursday 19:00 (90 min) and every Saturday 10:00 (60 min), EAT.
function series(overrides = {}) {
    return Object.assign({
        link: 'https://zoom.us/j/12345',
        isOnline: true,
        date: '2026-08-13',
        time: '19:00',
        utc: '2026-08-13T16:00:00Z',
        endUtc: '2026-08-13T17:30:00Z',
        durationMinutes: 90,
        tzLabel: 'EAT',
        tzOffsetMinutes: 180,
        isRecurring: true,
        sessionLabel: 'Masterclass',
        recurrence: {
            enabled: true,
            frequency: 'weekly',
            interval: 1,
            starts_on: null,
            until: null,
            skip_dates: [],
            slots: [
                { id: 'thu', day: 4, time: '19:00', duration: 90, label: 'Masterclass', link: '', note: '' },
                { id: 'sat', day: 6, time: '10:00', duration: 60, label: 'Clinic', link: 'https://meet.example/clinic', note: '' }
            ]
        },
        occurrences: [
            { date: '2026-08-13', time: '19:00', utc: '2026-08-13T16:00:00Z', endUtc: '2026-08-13T17:30:00Z', durationMinutes: 90, label: 'Masterclass', link: '', note: '', slotId: 'thu', inProgress: false },
            { date: '2026-08-15', time: '10:00', utc: '2026-08-15T07:00:00Z', endUtc: '2026-08-15T08:00:00Z', durationMinutes: 60, label: 'Clinic', link: 'https://meet.example/clinic', note: '', slotId: 'sat', inProgress: false }
        ]
    }, overrides);
}

function vevents(ics) {
    return ics.split('BEGIN:VEVENT').slice(1).map(block => block.split('END:VEVENT')[0]);
}

// --- One-off events ---------------------------------------------------------

test('a one-off event is saved at the exact instant the server resolved', () => {
    const ics = detail(ONE_OFF).generateICSString();
    assert.strictEqual(vevents(ics).length, 1);
    assert.ok(ics.includes('DTSTART:20270627T153000Z'), ics);
    assert.ok(ics.includes('DTEND:20270627T163000Z'), ics);
    assert.ok(!ics.includes('RRULE'), 'a one-off must not repeat');
});

test('a one-off event honours the length the server published', () => {
    const ics = detail(Object.assign({}, ONE_OFF, { endUtc: null, durationMinutes: 120 })).generateICSString();
    assert.ok(ics.includes('DTEND:20270627T173000Z'), ics);
});

// --- Repeating events -------------------------------------------------------

test('a repeating event saves one rule per repeating day', () => {
    const ics = detail(series()).generateICSString();
    const blocks = vevents(ics);

    assert.strictEqual(blocks.length, 2);
    assert.ok(blocks[0].includes('RRULE:FREQ=WEEKLY;BYDAY=TH'), blocks[0]);
    assert.ok(blocks[1].includes('RRULE:FREQ=WEEKLY;BYDAY=SA'), blocks[1]);
});

test('each repeating day is anchored on its own next session', () => {
    const blocks = vevents(detail(series()).generateICSString());

    assert.ok(blocks[0].includes('DTSTART:20260813T160000Z'), blocks[0]);
    assert.ok(blocks[0].includes('DTEND:20260813T173000Z'), blocks[0]);   // 90 minutes
    assert.ok(blocks[1].includes('DTSTART:20260815T070000Z'), blocks[1]);
    assert.ok(blocks[1].includes('DTEND:20260815T080000Z'), blocks[1]);   // 60 minutes
});

test('each day keeps its own title and location', () => {
    const blocks = vevents(detail(series()).generateICSString());

    assert.ok(blocks[0].includes('SUMMARY:Digital Masterclass — Masterclass'), blocks[0]);
    assert.ok(blocks[0].includes('LOCATION:https://zoom.us/j/12345'), blocks[0]);
    // The Saturday clinic overrides the event's main link.
    assert.ok(blocks[1].includes('LOCATION:https://meet.example/clinic'), blocks[1]);
});

test('a fortnightly series says so, and an end date closes it', () => {
    const rec = series();
    rec.recurrence.interval = 2;
    rec.recurrence.until = '2026-12-31';
    const block = vevents(detail(rec).generateICSString())[0];

    assert.ok(block.includes('INTERVAL=2'), block);
    // End of the final day in the creator's zone (23:59 EAT = 20:59 UTC).
    assert.ok(block.includes('UNTIL=20261231T205900Z'), block);
});

test('a cancelled date is excluded from the day it falls on', () => {
    const rec = series();
    rec.recurrence.skip_dates = ['2026-08-20'];   // a Thursday
    const blocks = vevents(detail(rec).generateICSString());

    assert.ok(blocks[0].includes('EXDATE:20260820T160000Z'), blocks[0]);
    assert.ok(!blocks[1].includes('EXDATE'), 'the Saturday rule is unaffected');
});

test('a day with no session left is not scheduled', () => {
    const rec = series();
    rec.occurrences = rec.occurrences.filter(o => o.slotId === 'thu');
    const blocks = vevents(detail(rec).generateICSString());

    assert.strictEqual(blocks.length, 1);
    assert.ok(blocks[0].includes('BYDAY=TH'), blocks[0]);
});

test('a series with nothing ahead still produces a valid single entry', () => {
    const rec = series({ occurrences: [] });
    const ics = detail(rec).generateICSString();

    assert.strictEqual(vevents(ics).length, 1);
    assert.ok(ics.includes('DTSTART:20260813T160000Z'), ics);
});

// --- The QR code ("Scan to Save") -------------------------------------------

test('the QR payload carries the same rules, trimmed for scannability', () => {
    const component = detail(series());
    component.asset.description = 'x'.repeat(2000);
    const ics = component.generateICSString(true);

    assert.ok(ics.includes('RRULE:FREQ=WEEKLY;BYDAY=TH'), 'QR keeps the series');
    assert.ok(!ics.includes('BEGIN:VALARM'), 'no alarms in a QR payload');
    ics.split('DESCRIPTION:').slice(1).forEach(part => {
        assert.ok(part.split('\n')[0].length <= 160, 'description trimmed for the QR');
    });
});

// --- Google Calendar (the Android path) -------------------------------------

test('the Google link repeats on the day the next session falls', () => {
    const url = detail(series()).getGoogleCalendarUrl();

    assert.ok(url.includes('dates=20260813T160000Z/20260813T173000Z'), url);
    assert.ok(url.includes('recur=' + encodeURIComponent('RRULE:FREQ=WEEKLY;BYDAY=TH')), url);
});

test('a one-off Google link carries no recurrence', () => {
    const url = detail(ONE_OFF).getGoogleCalendarUrl();

    assert.ok(url.includes('dates=20270627T153000Z/20270627T163000Z'), url);
    assert.ok(!url.includes('recur='), url);
});

// --- What the page says ------------------------------------------------------

test('the cadence names every repeating day', () => {
    const info = detail(series()).eventInfo;

    assert.strictEqual(info.isRecurring, true);
    assert.ok(/Thursday/.test(info.cadence), info.cadence);
    assert.ok(/Saturday/.test(info.cadence), info.cadence);
    assert.ok(/EAT$/.test(info.cadence), info.cadence);
    assert.strictEqual(info.sessionLabel, 'Masterclass');
});

test('a finished series is reported, not silently hidden', () => {
    const component = detail(series({ date: null, time: null, utc: null, occurrences: [], seriesEnded: true }));
    const info = component.eventInfo;

    assert.ok(info, 'the card must still render');
    assert.strictEqual(info.ended, true);
    assert.strictEqual(info.adminDisplay, component.eventI18n.seriesEnded);
});

test('a one-off event reports no recurrence at all', () => {
    const info = detail(ONE_OFF).eventInfo;

    assert.strictEqual(info.isRecurring, false);
    assert.strictEqual(info.cadence, '');
});

// --- The admin schedule editor ----------------------------------------------
// Both admin components mix in the same editor, so both are checked: building
// them must not blow up (the getters have to stay lazy), and the payload they
// submit has to be the shape the server normalizes.

function creatorForm() {
    const c = registry.assetForm();
    c.assetType = 'ticket';
    return c;
}

function editorPage(recurrence = null) {
    const c = registry.assetView({
        id: 3, title: 'Masterclass', asset_type: 'TICKET', status: 'Published',
        details: {}, files: [], custom_fields: [],
        eventDetails: { link: 'https://zoom.us/j/12345', date: '', time: '', maxAttendees: null, recurrence }
    }, ['Published', 'Draft']);
    c.editableAsset.eventDetails = JSON.parse(JSON.stringify(c.asset.eventDetails));
    c.editableAsset.eventDetails.recurrence = c._hydrateRecurrence(recurrence);
    return c;
}

[['create wizard', creatorForm], ['edit page', () => editorPage()]].forEach(([label, build]) => {
    test(`${label}: a fresh event has no schedule until it is switched on`, () => {
        const c = build();
        assert.strictEqual(c.recurrence.enabled, false);
        assert.deepStrictEqual(c.recurrence.slots, []);
        assert.deepStrictEqual(c.buildRecurrencePayload(), { enabled: false, slots: [] });
    });

    test(`${label}: switching the repeat on starts a first day`, () => {
        const c = build();
        c.toggleRecurrence();
        assert.strictEqual(c.recurrence.enabled, true);
        assert.strictEqual(c.recurrence.slots.length, 1);
        assert.strictEqual(c.recurrence.slots[0].duration, 60);
    });

    test(`${label}: extra days can be added and removed`, () => {
        const c = build();
        c.toggleRecurrence();
        c.recurrence.slots[0].day = 4;              // Thursday
        c.addRecurrenceSlot();
        assert.strictEqual(c.recurrence.slots.length, 2);

        c.removeRecurrenceSlot(c.recurrence.slots[1].id);
        assert.strictEqual(c.recurrence.slots.length, 1);
        // Removing the last day means the event is no longer repeating.
        c.removeRecurrenceSlot(c.recurrence.slots[0].id);
        assert.strictEqual(c.recurrence.enabled, false);
    });

    test(`${label}: the payload matches what the server stores`, () => {
        const c = build();
        c.toggleRecurrence();
        Object.assign(c.recurrence.slots[0], { day: 4, time: '19:00', duration: 90, label: ' Masterclass ' });
        c.recurrence.interval = 2;
        c.recurrence.until = '';
        const payload = c.buildRecurrencePayload();

        assert.strictEqual(payload.enabled, true);
        assert.strictEqual(payload.interval, 2);
        assert.strictEqual(payload.until, null);    // an empty date is "no end"
        assert.deepStrictEqual(
            { day: payload.slots[0].day, time: payload.slots[0].time, duration: payload.slots[0].duration, label: payload.slots[0].label },
            { day: 4, time: '19:00', duration: 90, label: 'Masterclass' }
        );
    });

    test(`${label}: the preview shows the dates the schedule will produce`, () => {
        const c = build();
        c.toggleRecurrence();
        Object.assign(c.recurrence.slots[0], { day: 4, time: '19:00', label: 'Masterclass' });
        const preview = c.recurrencePreview;

        assert.ok(preview.length > 0, 'a live schedule must preview something');
        assert.ok(preview.every(p => /Thu/.test(p.text)), JSON.stringify(preview));
        assert.strictEqual(preview[0].label, 'Masterclass');
    });

    test(`${label}: an end date in the past previews nothing`, () => {
        const c = build();
        c.toggleRecurrence();
        c.recurrence.until = '2020-01-01';
        assert.deepStrictEqual(c.recurrencePreview, []);
    });
});

test('edit page: an existing schedule is loaded back into the form', () => {
    const c = editorPage({
        enabled: true, interval: 1, starts_on: null, until: '2026-12-31', skip_dates: ['2026-08-13'],
        slots: [{ id: 'thu', day: 4, time: '19:00', duration: 90, label: 'Masterclass', link: '', note: '' }]
    });

    assert.strictEqual(c.recurrence.enabled, true);
    assert.strictEqual(c.recurrence.slots[0].label, 'Masterclass');
    assert.deepStrictEqual(c.recurrence.skip_dates, ['2026-08-13']);
    // Round-trips unchanged, so re-saving an untouched event changes nothing.
    const payload = c.buildRecurrencePayload();
    assert.strictEqual(payload.until, '2026-12-31');
    assert.strictEqual(payload.slots[0].id, 'thu');
});

if (failures) {
    console.error(`\n${failures} calendar assertion(s) failed`);
    process.exit(1);
}
console.log('calendar + recurrence: all assertions passed');
