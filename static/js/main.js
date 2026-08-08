// static/js/main.js

// Every admin field whose value is rendered as Markdown to buyers gets the same
// editor: same toolbar, same preview styling (.editor-preview reuses the public
// .prose rules), same single-line-break behaviour as the public renderer, which
// parses with marked({ breaks: true }).
function mountMarkdownEditor(element, { minHeight = '160px', placeholder = '' } = {}) {
    if (typeof EasyMDE === 'undefined' || !element || element._mde) return null;
    const mde = new EasyMDE({
        element,
        placeholder: placeholder || element.getAttribute('placeholder') || '',
        minHeight,
        spellChecker: false,
        status: false,
        autosave: { enabled: false },
        renderingConfig: { singleLineBreaks: true },
        toolbar: [
            'bold', 'italic', 'heading', '|',
            'quote', 'unordered-list', 'ordered-list', '|',
            'link', 'image', '|',
            'preview', 'side-by-side', 'guide'
        ]
    });
    element._mde = mde;
    return mde;
}

// Wire a mounted editor to Alpine state in both directions on mount, then keep
// state in sync as the creator types.
// Client-side id for a product variation. Server keeps it (sanitized to
// [A-Za-z0-9_-]) and pairs it with the matching variation_photo_<id> upload.
function newVariationId() {
    return 'v' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}

// Shared by the admin activity feeds: render questionnaire answers in their most
// useful form — location objects as Google Maps links, phone numbers as tel/WhatsApp
// links, URLs as links. Mixed into activityFeed and supporterActivity.
const answerValueHelpers = {
    isLocationAnswer(v) { return !!(v && typeof v === 'object' && v.__location__); },
    locationHref(v) {
        if (!this.isLocationAnswer(v)) return '';
        if ((v.maps_url || '').trim()) return v.maps_url.trim();
        if (v.lat !== null && v.lat !== undefined && v.lng !== null && v.lng !== undefined) {
            return `https://www.google.com/maps?q=${v.lat},${v.lng}`;
        }
        return '';
    },
    isPhoneAnswer(v) {
        if (typeof v !== 'string') return false;
        const t = v.trim();
        return /^\+?[0-9][0-9 ()\-]{7,15}$/.test(t) && t.replace(/\D/g, '').length >= 9;
    },
    telHref(v) { return 'tel:' + String(v).replace(/[^\d+]/g, ''); },
    waHref(v) {
        let d = String(v).replace(/\D/g, '');
        if (d.startsWith('0')) d = '255' + d.slice(1); // Tanzanian local format
        return 'https://wa.me/' + d;
    },
    isUrlAnswer(v) { return typeof v === 'string' && /^https?:\/\//i.test(v.trim()); },
};

// --- Tanzanian phone entry -------------------------------------------------
// Checkout shows a fixed 🇹🇿 +255 prefix, so a buyer only ever types the 9-digit
// national part. Whatever they actually type or paste — 0712 345 678,
// +255 712 345 678, 255712345678, 00255712345678, +255 (0) 712-345-678 — collapses
// to those same 9 digits, and we always submit the canonical 0XXXXXXXXX that the
// database and the UZA gateway expect. Kept as a plain object (no Alpine, no DOM)
// so both checkout components and the tests can share exactly one implementation.
const NyotaPhone = {
    // The 9 national digits, stripped of every prefix. Safe on every keystroke.
    national(raw) {
        let d = String(raw === null || raw === undefined ? '' : raw).replace(/\D/g, '');
        if (d.startsWith('00255')) d = d.slice(5);
        // Only treat a leading 255 as the country code once it can't be the start
        // of a real number — so someone typing "255…" mid-entry isn't fought with.
        else if (d.startsWith('255') && (d.length > 9 || /^255[67]/.test(d))) d = d.slice(3);
        d = d.replace(/^0+/, ''); // national trunk prefix (and any stray zeros)
        return d.slice(0, 9);
    },

    // What the input shows while typing: 712 345 678
    display(raw) {
        const d = this.national(raw);
        if (d.length > 6) return d.slice(0, 3) + ' ' + d.slice(3, 6) + ' ' + d.slice(6);
        if (d.length > 3) return d.slice(0, 3) + ' ' + d.slice(3);
        return d;
    },

    // Canonical local form (0XXXXXXXXX) — what we store and send to the server.
    canonical(raw) {
        const d = this.national(raw);
        return d ? '0' + d : '';
    },

    // Full international form, for read-back ("Request sent to +255 712 345 678").
    international(raw) {
        const d = this.display(raw);
        return d ? '+255 ' + d : '';
    },

    // TZ mobile numbers are 9 national digits starting with 6 or 7.
    isValid(raw) {
        return /^[67]\d{8}$/.test(this.national(raw));
    },
};

if (typeof window !== 'undefined') window.NyotaPhone = NyotaPhone;
if (typeof module !== 'undefined' && module.exports) module.exports = { NyotaPhone };

// --- Repeating events (admin) ----------------------------------------------
// Shared by the create wizard (assetForm) and the edit page (assetView) so both
// build the exact same details['recurrence'] payload the server normalizes:
//   { enabled, interval, slots: [{id, day, time, duration, label, link, note}],
//     starts_on, until, skip_dates }
// `day` is 0=Sunday..6=Saturday, matching Date.getDay() and the ICS BYDAY table.
const recurrenceEditor = {
    recurrenceDays: [
        { value: 1, name: 'Monday' }, { value: 2, name: 'Tuesday' }, { value: 3, name: 'Wednesday' },
        { value: 4, name: 'Thursday' }, { value: 5, name: 'Friday' }, { value: 6, name: 'Saturday' },
        { value: 0, name: 'Sunday' }
    ],

    // Fill in anything a stored (or missing) recurrence lacks, so the form can
    // bind to it directly without null checks in every x-model.
    _hydrateRecurrence(stored) {
        const rec = stored && typeof stored === 'object' ? stored : {};
        return {
            enabled: !!rec.enabled,
            interval: rec.interval || 1,
            starts_on: rec.starts_on || '',
            until: rec.until || '',
            skip_dates: Array.isArray(rec.skip_dates) ? [...rec.skip_dates] : [],
            slots: (rec.slots || []).map(s => ({
                id: s.id || newRecurrenceSlotId(),
                day: Number(s.day) || 0,
                time: s.time || '18:00',
                duration: s.duration || 60,
                label: s.label || '',
                link: s.link || '',
                note: s.note || ''
            }))
        };
    },

    // The recurrence object the form is bound to. Each host component keeps its
    // event state somewhere different, so it supplies `_recurrence()`.
    get recurrence() { return this._recurrence(); },

    toggleRecurrence() {
        const rec = this.recurrence;
        rec.enabled = !rec.enabled;
        // Turning it on with nothing configured yet: start from the day/time the
        // creator already picked for the one-off, so nothing has to be retyped.
        if (rec.enabled && !rec.slots.length) this.addRecurrenceSlot();
    },

    addRecurrenceSlot() {
        const rec = this.recurrence;
        const seed = this._eventSeed();
        const last = rec.slots[rec.slots.length - 1];
        rec.slots.push({
            id: newRecurrenceSlotId(),
            day: last ? (last.day + 1) % 7 : (seed.date ? new Date(seed.date + 'T00:00').getDay() : 4),
            time: last ? last.time : (seed.time || '18:00'),
            duration: last ? last.duration : 60,
            label: '', link: '', note: ''
        });
    },

    removeRecurrenceSlot(id) {
        const rec = this.recurrence;
        rec.slots = rec.slots.filter(s => s.id !== id);
        if (!rec.slots.length) rec.enabled = false;
    },

    recurrenceDayName(day) {
        return (this.recurrenceDays.find(d => d.value === Number(day)) || {}).name || '';
    },

    // The next few dates this schedule produces — the admin's proof that "every
    // Thursday" lands where they expect. Times are echoed back exactly as typed
    // (they are store wall-clock); only "which day is today" comes from the
    // browser, so the server stays the authority on what buyers are shown.
    get recurrencePreview() {
        const rec = this.recurrence;
        if (!rec.enabled || !rec.slots.length) return [];
        const skip = new Set(rec.skip_dates || []);
        const startsOn = rec.starts_on ? new Date(rec.starts_on + 'T00:00') : null;
        const until = rec.until ? new Date(rec.until + 'T23:59') : null;
        const interval = Math.max(1, Number(rec.interval) || 1);
        const anchor = startsOn ? new Date(startsOn) : new Date(1970, 0, 4);
        anchor.setDate(anchor.getDate() - anchor.getDay()); // back to that Sunday

        const out = [];
        const cursor = new Date();
        cursor.setHours(0, 0, 0, 0);
        if (startsOn && startsOn > cursor) cursor.setTime(startsOn.getTime());
        for (let i = 0; i < 120 && out.length < 4; i++) {
            const iso = `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, '0')}-${String(cursor.getDate()).padStart(2, '0')}`;
            const weekIndex = Math.floor((cursor - anchor) / (7 * 86400000));
            if ((!until || cursor <= until) && !skip.has(iso) && (interval === 1 || weekIndex % interval === 0)) {
                rec.slots.filter(s => Number(s.day) === cursor.getDay()).forEach(slot => {
                    if (out.length >= 4) return;
                    const when = new Date(cursor);
                    const [h, m] = String(slot.time || '00:00').split(':').map(Number);
                    when.setHours(h || 0, m || 0);
                    if (when < new Date()) return; // already gone today
                    out.push({
                        key: iso + slot.id,
                        text: when.toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }),
                        label: slot.label || ''
                    });
                });
            }
            cursor.setDate(cursor.getDate() + 1);
        }
        return out;
    },

    // The payload shape the server expects; '' dates become null.
    buildRecurrencePayload() {
        const rec = this.recurrence;
        if (!rec || !rec.enabled || !rec.slots.length) return { enabled: false, slots: [] };
        return {
            enabled: true,
            interval: Math.max(1, Number(rec.interval) || 1),
            starts_on: rec.starts_on || null,
            until: rec.until || null,
            skip_dates: rec.skip_dates || [],
            slots: rec.slots.map(s => ({
                id: s.id, day: Number(s.day), time: s.time,
                duration: Number(s.duration) || 60,
                label: (s.label || '').trim(), link: (s.link || '').trim(), note: (s.note || '').trim()
            }))
        };
    }
};

function newRecurrenceSlotId() {
    return 'r' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

// Mix the editor into a component. Copying descriptors (rather than spreading)
// keeps `recurrence` and `recurrencePreview` as accessors — a spread would *call*
// them against a half-built component. Alpine reads getters as accessors too, so
// they stay reactive.
function withRecurrenceEditor(component) {
    return Object.defineProperties(component, Object.getOwnPropertyDescriptors(recurrenceEditor));
}

// --- Contribution call to action ---------------------------------------------
// The verb on a pay-what-you-want button: "Donate", "Buy me a coffee", "Unlock".
// Not every flexible-amount asset is charity — most hand something back — and a
// visitor decides which one they are looking at from this one word, so the
// creator gets to choose it.
//
// The creator works in an English admin while their visitors read Swahili, so
// the picker shows both languages at once. The pool comes from the server
// (utils/pricing.CTA_PRESETS) through a #cta-presets island, so the words
// previewed here are the exact words that will render.
const CTA_FALLBACK = { id: 'donate', en: 'Donate', sw: 'Changia' };

let _ctaPresetPool = null;
function ctaPresetPool() {
    // Memoised outside Alpine: a getter that wrote to component state would be
    // a reactive write during render.
    if (_ctaPresetPool) return _ctaPresetPool;
    try {
        const el = document.getElementById('cta-presets');
        _ctaPresetPool = el ? (JSON.parse(el.textContent || '[]') || []) : [];
    } catch (e) { _ctaPresetPool = []; }
    return _ctaPresetPool;
}

// Mixed into any component that has a `ctaTarget()` returning its donation
// config object. Reads never mutate that object; only the two actions do.
const ctaEditor = {
    get ctaPresets() { return ctaPresetPool(); },

    ctaConfig() {
        const d = this.ctaTarget() || {};
        return {
            cta: d.cta || CTA_FALLBACK.id,
            custom: (d.cta_custom && typeof d.cta_custom === 'object') ? d.cta_custom : { en: '', sw: '' },
        };
    },

    // Once the creator has written their own words, "Write your own" is the
    // selected option and no preset chip is.
    get ctaIsCustom() {
        const c = this.ctaConfig().custom;
        return !!((c.en || '').trim() || (c.sw || '').trim());
    },

    ctaPresetSelected(id) {
        return !this.ctaIsCustom && this.ctaConfig().cta === id;
    },

    // A required contribution puts this label on the main button; an optional one
    // leaves the button offering the item free and moves the label under the price.
    get ctaIsMandatory() { return !!(this.ctaTarget() || {}).mandatory; },

    pickCtaPreset(id) {
        const d = this.ctaTarget();
        d.cta = id;
        d.cta_custom = { en: '', sw: '' };
    },

    // Seed the custom boxes from the current preset. Editing real words beats
    // facing two empty fields, and it means both languages start out filled.
    startCustomCta() {
        if (this.ctaIsCustom) return;
        const d = this.ctaTarget();
        const p = this.ctaPresets.find(x => x.id === (d.cta || CTA_FALLBACK.id)) || CTA_FALLBACK;
        d.cta_custom = { en: p.en, sw: p.sw };
    },

    // x-model targets, so the partial can be dropped into any host component
    // without knowing where that component keeps its donation config.
    _ctaCustomWrite(lang, value) {
        const d = this.ctaTarget();
        if (!d.cta_custom || typeof d.cta_custom !== 'object') d.cta_custom = { en: '', sw: '' };
        d.cta_custom[lang] = value;
    },
    get ctaCustomEn() { return this.ctaConfig().custom.en || ''; },
    set ctaCustomEn(v) { this._ctaCustomWrite('en', v); },
    get ctaCustomSw() { return this.ctaConfig().custom.sw || ''; },
    set ctaCustomSw(v) { this._ctaCustomWrite('sw', v); },

    // The amount half of the button, so the preview reads like the real thing
    // instead of a bare verb. The first suggestion is what most people tap.
    get ctaPreviewAmount() {
        const d = this.ctaTarget() || {};
        const suggested = String(d._suggestedRaw || '')
            .split(',').map(s => parseFloat(s.trim())).filter(n => !isNaN(n) && n > 0);
        const amount = suggested[0] || parseFloat(d.min_amount) || 0;
        return amount > 0 ? amount.toLocaleString('en-US') : '';
    },

    // The same fallback ladder the server uses (utils/pricing.contribution_voice):
    // a creator who filled in one language meant it to be read, not to vanish
    // for half their visitors.
    get ctaPreview() {
        const { cta, custom } = this.ctaConfig();
        const en = (custom.en || '').trim();
        const sw = (custom.sw || '').trim();
        if (en || sw) return { en: en || sw, sw: sw || en };
        const p = this.ctaPresets.find(x => x.id === cta) || CTA_FALLBACK;
        return { en: p.en, sw: p.sw };
    },
};

function withCtaEditor(component) {
    return Object.defineProperties(component, Object.getOwnPropertyDescriptors(ctaEditor));
}

function bindMarkdownEditor(element, opts, getValue, setValue) {
    const mde = mountMarkdownEditor(element, opts);
    if (!mde) return null;
    const initial = getValue();
    if (initial) mde.value(initial);
    mde.codemirror.on('change', () => setValue(mde.value()));
    return mde;
}

document.addEventListener('alpine:init', () => {

    // ========================================================================
    // == GLOBAL & USER-FACING COMPONENTS
    // ========================================================================

    Alpine.data('themeManager', () => ({
        theme: localStorage.getItem('theme') || 'system',
        isDarkMode: false,
        init() { this.applyTheme(); window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (this.theme === 'system') this.applyTheme(); }); window.addEventListener('set-theme', (event) => { this.setTheme(event.detail); }); },
        applyTheme() { if (this.theme === 'dark' || (this.theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)) { document.documentElement.classList.add('dark'); this.isDarkMode = true; } else { document.documentElement.classList.remove('dark'); this.isDarkMode = false; } },
        setTheme(newTheme) { this.theme = newTheme; localStorage.setItem('theme', newTheme); this.applyTheme(); }
    }));

    Alpine.data('storefront', (currencySymbol) => ({
        assets: [], activeFilter: 'all', currency: currencySymbol,
        init() { try { const dataElement = document.getElementById('storefront-data'); if (dataElement) this.assets = JSON.parse(dataElement.textContent); } catch (e) { console.error('Error parsing storefront data:', e); } },
        get filteredAssets() { if (this.activeFilter === 'all') return this.assets; return this.assets.filter(asset => asset.asset_type === this.activeFilter); },
        setFilter(type) { this.activeFilter = type; },
        formatCurrency(amount) { return new Intl.NumberFormat('en-US', { style: 'decimal', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount || 0); }
    }));

    // --- Physical goods: the buyer's in-progress order --------------------------
    // The choice (variation + quantity) is made ON the product page, next to the
    // photos, and is then read by the price card, the sticky footer and the
    // checkout modal. A store rather than component state, because those four live
    // in different Alpine scopes and must never disagree about what is being bought.
    Alpine.store('order', {
        isPhysical: false,
        variations: [],
        selected: null,
        quantity: 1,
        basePrice: 0,

        init() {
            let asset = null;
            try {
                const el = document.getElementById('asset-data');
                if (el) asset = JSON.parse(el.textContent);
            } catch (e) { /* not an asset page — the store stays inert */ }
            if (!asset || asset.asset_type !== 'PHYSICAL') return;
            this.isPhysical = true;
            this.basePrice = parseFloat(asset.price || 0);
            this.variations = (asset.details?.variations || []).filter(v => v && v.id);
            // Pre-select the first available option so a buyer who wants the obvious
            // thing pays without a single extra tap. The choice is never silent: the
            // hero photo, the footer and the modal all name it before money moves.
            this.selected = this.variations.find(v => !v.sold_out) || null;
        },

        get hasOptions() { return this.variations.length > 0; },
        // Every option gone — the page shows "sold out" instead of a buy button.
        get soldOut() { return this.hasOptions && !this.selected; },
        // A variation with no price of its own is sold at the asset's base price.
        priceOf(v) {
            const p = v ? v.price : null;
            return (p === null || p === undefined || p === '') ? this.basePrice : (parseFloat(p) || 0);
        },
        get unitPrice() { return this.selected ? this.priceOf(this.selected) : this.basePrice; },
        get total() { return this.unitPrice * this.quantity; },
        // True when the options a buyer can actually pick differ in price — if they
        // don't, repeating the same number on every row is noise to read past. A
        // sold-out option's price is irrelevant: it can never be bought.
        get pricesVary() {
            const buyable = this.variations.filter(v => !v.sold_out);
            if (buyable.length < 2) return false;
            const first = this.priceOf(buyable[0]);
            return buyable.some(v => this.priceOf(v) !== first);
        },
        get photo() { return (this.selected && this.selected.photo_url) || null; },
        pick(v) { if (v && !v.sold_out) this.selected = v; },
        inc() { if (this.quantity < 100) this.quantity++; },
        dec() { if (this.quantity > 1) this.quantity--; },
        money(amount) {
            return new Intl.NumberFormat('en-US', { style: 'decimal', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount || 0);
        }
    });

    Alpine.data('assetDetail', (currencySymbol) => ({
        asset: {}, countdown: 'Loading...', currency: currencySymbol, visibleReviews: 3,
        toast: { show: false, message: '', type: 'success' },
        qrCodeUrl: '', showQRCode: false,
        // Translatable fragments for the timezone hints; overridden from #event-i18n.
        eventI18n: {
            same: 'This is your local time', ahead: "You're {d} ahead", behind: "You're {d} behind",
            yourTime: 'your time', hourShort: 'h', minShort: 'm',
            every: 'Every {days}', nextSession: 'Next session', happeningNow: 'Happening now',
            upcomingSessions: 'Upcoming sessions', seriesEnded: 'This series has ended'
        },

        init() {
            try { const dataElement = document.getElementById('asset-data'); if (dataElement) this.asset = JSON.parse(dataElement.textContent); } catch (e) { console.error('Error parsing asset detail data:', e); }
            try { const i18nEl = document.getElementById('event-i18n'); if (i18nEl) this.eventI18n = Object.assign(this.eventI18n, JSON.parse(i18nEl.textContent)); } catch (e) { /* keep defaults */ }
            // Anchor the countdown on the resolved UTC instant — for a repeating
            // event that is the next occurrence, so it rolls over on its own.
            if (this.asset.asset_type === 'TICKET' && this.asset.eventDetails?.utc) {
                this.countdownInterval = setInterval(() => this.updateCountdown(), 1000);
                this.updateCountdown();
            }
        },

        showToast(message, type = 'success') {
            this.toast.message = message;
            this.toast.type = type;
            this.toast.show = true;
            setTimeout(() => { this.toast.show = false; }, 3000);
        },

        updateCountdown() { const eventDate = new Date(this.asset.eventDetails?.utc || this.asset.event_date).getTime(); const now = new Date().getTime(); const distance = eventDate - now; if (distance < 0) { this.countdown = "EVENT HAS PASSED"; if (this.countdownInterval) clearInterval(this.countdownInterval); return; } const d = Math.floor(distance / (1000 * 60 * 60 * 24)); const h = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60)); const m = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60)); const s = Math.floor((distance % (1000 * 60)) / 1000); this.countdown = `${d}d ${h}h ${m}m ${s}s`; },
        get averageRating() { if (!this.asset.reviews || this.asset.reviews.length === 0) return 'N/A'; const total = this.asset.reviews.reduce((sum, review) => sum + review.rating, 0); return (total / this.asset.reviews.length).toFixed(1); },
        showMoreReviews() { this.visibleReviews += 5; },
        renderMarkdown(text) {
            if (!text) return '';
            const mdPattern = /(?:^#{1,6}\s|^\s*[-*+]\s|^\s*\d+\.\s|\*\*.+\*\*|__.+__|`.+`|\[.+\]\(.+\)|^>\s|^```|!\[)/m;
            const hasMarkdown = mdPattern.test(text);
            if (hasMarkdown && window.marked) {
                try { return window.marked.parse(text); } catch (e) { /* fall through */ }
            }
            const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
            return escaped.replace(/\n/g, '<br>');
        },
        formatCurrency(amount) { return new Intl.NumberFormat('en-US', { style: 'decimal', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount || 0); },

        toggleQRCode() {
            try {
                if (!this.qrCodeUrl) {
                    const icsString = this.generateICSString(true);
                    this.qrCodeUrl = `https://api.qrserver.com/v1/create-qr-code/?size=400x400&ecc=L&margin=1&format=svg&data=${encodeURIComponent(icsString)}`;
                }
                this.showQRCode = !this.showQRCode;
            } catch (err) {
                console.error("Error generating QR code:", err);
                this.showToast("Could not generate calendar code. Invalid event details.", "error");
            }
        },

        // --- Timezone-aware event display -------------------------------------
        // The creator's wall-clock time is the single source of truth. We show it
        // verbatim (labelled with the creator's zone) and, when we have a real UTC
        // anchor, also tell the buyer how their own zone relates to it.
        get eventInfo() {
            const ev = this.asset.eventDetails || {};
            // A repeating series that has run past its end date has no date left to
            // show, but the card must still explain why rather than vanish.
            if (!ev.date) {
                if (ev.seriesEnded) {
                    return { hasTime: false, tzLabel: ev.tzLabel || '', adminDisplay: this.eventI18n.seriesEnded,
                             userDisplay: null, relation: null, sameZone: null,
                             isRecurring: true, ended: true, cadence: this.recurrenceCadence,
                             sessionLabel: '', inProgress: false };
                }
                return null;
            }
            const info = {
                hasTime: !!ev.time,
                tzLabel: ev.tzLabel || '',
                adminDisplay: this._formatWallClock(ev.date, ev.time, ev.tzLabel),
                userDisplay: null,
                relation: null,
                sameZone: null,
                // Repeating-event context: the cadence ("Every Thursday, 7:00 PM"),
                // the label the creator gave this particular day, and whether the
                // session advertised is running right now.
                isRecurring: !!ev.isRecurring,
                ended: false,
                cadence: this.recurrenceCadence,
                sessionLabel: ev.sessionLabel || '',
                sessionNote: ev.sessionNote || '',
                inProgress: !!ev.inProgress
            };
            // Buyer-relative info needs the UTC anchor + the creator's offset.
            if (ev.utc && ev.tzOffsetMinutes !== undefined && ev.tzOffsetMinutes !== null) {
                const instant = new Date(ev.utc);
                if (!isNaN(instant.getTime())) {
                    const userOffset = -instant.getTimezoneOffset(); // minutes east of UTC
                    const diff = userOffset - ev.tzOffsetMinutes;    // + => buyer ahead
                    info.sameZone = (diff === 0);
                    info.userDisplay = instant.toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
                    info.relation = this._describeOffset(diff);
                }
            }
            return info;
        },

        // Format creator wall-clock numbers without any timezone shift. We build a
        // local Date from the literal parts purely so Intl can render names; the
        // displayed numbers are exactly what the admin entered.
        _formatWallClock(dateStr, timeStr, tzLabel) {
            const [y, m, d] = (dateStr || '').split('-').map(Number);
            if (!y || !m || !d) return (dateStr || '') + (timeStr ? ' ' + timeStr : '');
            let hh = 0, mm = 0;
            if (timeStr) { const p = timeStr.split(':'); hh = parseInt(p[0], 10) || 0; mm = parseInt(p[1], 10) || 0; }
            const dt = new Date(y, m - 1, d, hh, mm);
            const opts = timeStr
                ? { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' }
                : { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' };
            let out = dt.toLocaleString(undefined, opts);
            if (tzLabel) out += ' ' + tzLabel;
            return out;
        },

        // "Every Thursday, 7:00 PM EAT" — built from the structured slots so day
        // and time names follow the visitor's locale, while the numbers stay the
        // creator's wall-clock (the canonical time everyone is quoted).
        get recurrenceCadence() {
            const rec = this.asset.eventDetails?.recurrence;
            if (!rec || !(rec.slots || []).length) return '';
            const tzLabel = this.asset.eventDetails?.tzLabel || '';
            const parts = rec.slots.map(slot => {
                const dayName = this._weekdayName(slot.day);
                const time = this._formatClockTime(slot.time);
                return time ? `${dayName} ${time}` : dayName;
            });
            const joined = parts.length > 1
                ? parts.slice(0, -1).join(', ') + ' & ' + parts[parts.length - 1]
                : parts[0];
            let out = (this.eventI18n.every || 'Every {days}').replace('{days}', joined);
            if (tzLabel) out += ' ' + tzLabel;
            if (rec.interval > 1) out += ` (every ${rec.interval} weeks)`;
            return out;
        },

        // The next few sessions, ready for a list. Each keeps the creator's
        // wall-clock plus that day's own label, so a Thursday masterclass and a
        // Saturday clinic read as the different things they are.
        get upcomingSessions() {
            const list = this.asset.eventDetails?.occurrences || [];
            return list.map(o => ({
                key: o.utc,
                display: this._formatWallClock(o.date, o.time, ''),
                label: o.label || '',
                inProgress: !!o.inProgress
            }));
        },

        // 0 = Sunday, matching the stored slot day and JS getDay().
        _weekdayName(day) {
            const ref = new Date(Date.UTC(2024, 0, 7 + (Number(day) || 0))); // 2024-01-07 was a Sunday
            return ref.toLocaleDateString(undefined, { weekday: 'long', timeZone: 'UTC' });
        },

        // 'HH:MM' wall-clock -> locale time string, with no timezone shift applied.
        _formatClockTime(timeStr) {
            if (!timeStr) return '';
            const [h, m] = String(timeStr).split(':').map(Number);
            if (isNaN(h)) return timeStr;
            const dt = new Date(2024, 0, 1, h, m || 0);
            return dt.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
        },

        _describeOffset(diffMinutes) {
            if (diffMinutes === 0) return this.eventI18n.same;
            const ahead = diffMinutes > 0;
            const abs = Math.abs(diffMinutes);
            const h = Math.floor(abs / 60), m = abs % 60;
            let dur = '';
            if (h) dur += h + this.eventI18n.hourShort;
            if (m) dur += (h ? ' ' : '') + m + this.eventI18n.minShort;
            return (ahead ? this.eventI18n.ahead : this.eventI18n.behind).replace('{d}', dur);
        },

        getEventDates() {
            const toUtcStamp = (d) => d.toISOString().replace(/[-:]|\.\d{3}/g, ''); // -> 20260627T183200Z

            // Preferred path: anchor to the server-computed UTC instant so the saved
            // calendar entry lands at the correct absolute moment in every timezone.
            // For a repeating event that instant is the next occurrence, and the
            // RRULE added by generateICSString carries the rest of the series.
            const evUtc = this.asset.eventDetails?.utc;
            if (evUtc) {
                const start = new Date(evUtc);
                if (!isNaN(start.getTime())) {
                    const evEndUtc = this.asset.eventDetails?.endUtc;
                    let end = evEndUtc ? new Date(evEndUtc) : null;
                    if (!end || isNaN(end.getTime())) {
                        const mins = this.asset.eventDetails?.durationMinutes || 60;
                        end = new Date(start.getTime() + mins * 60 * 1000);
                    }
                    const stamp = toUtcStamp(start), endStamp = toUtcStamp(end);
                    return { icsStart: stamp, icsEnd: endStamp, googleStart: stamp, googleEnd: endStamp };
                }
            }

            // Fallback (no UTC anchor): legacy floating local time.
            let startDt = new Date();
            let endDt = new Date(startDt.getTime() + 60 * 60 * 1000); // default +1 hour

            const evtDate = this.asset.eventDetails?.date;
            const evtTime = this.asset.eventDetails?.time;

            if (evtDate) {
                // Try parsing as-is first
                let parsed = new Date(evtDate);

                // If we also have a time, try to compose them safely
                if (evtTime) {
                    // Make sure date is in YYYY-MM-DD format before appending T
                    const isIsoRegex = /^\d{4}-\d{2}-\d{2}$/;
                    if (isIsoRegex.test(evtDate)) {
                        const composed = new Date(`${evtDate}T${evtTime}`);
                        if (!isNaN(composed.getTime())) parsed = composed;
                    } else {
                        // Fallback: use the date parsed, set hours/mins from time
                        const [hours, minutes] = evtTime.split(':');
                        if (!isNaN(parsed.getTime()) && hours !== undefined && minutes !== undefined) {
                            parsed.setHours(parseInt(hours, 10), parseInt(minutes, 10), 0);
                        }
                    }
                }

                if (!isNaN(parsed.getTime())) {
                    startDt = parsed;
                    endDt = new Date(startDt.getTime() + 60 * 60 * 1000);
                }
            }

            // Local time formatting for ICS (Floating Time)
            const formatICS = (d) => {
                const pad = (n) => n < 10 ? '0' + n : n;
                return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}T${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
            };

            // UTC format for Google Calendar
            const formatGoogle = (d) => {
                return d.toISOString().replace(/-|:|\.\d\d\d/g, "");
            };

            return {
                icsStart: formatICS(startDt),
                icsEnd: formatICS(endDt),
                googleStart: formatGoogle(startDt),
                googleEnd: formatGoogle(endDt)
            };
        },

        getEventDescription() {
            const asset = this.asset;
            let fullDescription = asset.description || '';

            if (asset.details && asset.details.postPurchaseInstructions) {
                fullDescription += `\n\nNotes / Instructions:\n${asset.details.postPurchaseInstructions}`;
            }

            const link = asset.eventDetails?.link;
            if (link) {
                fullDescription += `\n\nWebinar Link: ${link}`;
            }

            if (asset.files && asset.files.length > 0) {
                fullDescription += `\n\nIncluded Files/Links:\n`;
                asset.files.forEach(f => {
                    const linkUrl = f.link.startsWith('http') ? f.link : (window.location.origin + f.link);
                    fullDescription += `- ${f.title}: ${linkUrl}\n`;
                });
            }
            return fullDescription;
        },

        // --- Calendar rules for a repeating event ------------------------------
        // ICS BYDAY codes, indexed the same way as the stored slot day (0 = Sunday).
        _icsDayCodes: ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'],

        // 'YYYY-MM-DD' + 'HH:MM' in the CREATOR's zone -> a UTC ICS stamp. Uses the
        // offset the server resolved for the next occurrence, which is the right
        // one for every rule anchored near it.
        _creatorStampToUtc(dateStr, timeStr) {
            const offset = this.asset.eventDetails?.tzOffsetMinutes || 0;
            const [y, m, d] = String(dateStr || '').split('-').map(Number);
            if (!y || !m || !d) return null;
            const [hh, mm] = String(timeStr || '00:00').split(':').map(Number);
            const utcMs = Date.UTC(y, m - 1, d, hh || 0, mm || 0) - offset * 60 * 1000;
            return new Date(utcMs).toISOString().replace(/[-:]|\.\d{3}/g, '');
        },

        // The RRULE (plus any EXDATEs) for one repeating day.
        _slotRecurrenceRule(slot) {
            const rec = this.asset.eventDetails?.recurrence;
            if (!rec) return '';
            let rule = `RRULE:FREQ=WEEKLY;BYDAY=${this._icsDayCodes[slot.day] || 'MO'}`;
            if (rec.interval > 1) rule += `;INTERVAL=${rec.interval}`;
            if (rec.until) {
                // End of the final day in the creator's zone, expressed as UTC.
                const untilStamp = this._creatorStampToUtc(rec.until, '23:59');
                if (untilStamp) rule += `;UNTIL=${untilStamp}`;
            }
            let out = rule + '\n';
            // Cancelled dates only exclude the sessions that actually fall on them.
            const skipped = (rec.skip_dates || []).filter(dateStr => {
                const [y, m, d] = String(dateStr).split('-').map(Number);
                if (!y) return false;
                return new Date(Date.UTC(y, m - 1, d)).getUTCDay() === slot.day;
            }).map(dateStr => this._creatorStampToUtc(dateStr, slot.time)).filter(Boolean);
            if (skipped.length) out += `EXDATE:${skipped.join(',')}\n`;
            return out;
        },

        generateICSString(isForQR = false) {
            const asset = this.asset;
            const title = asset.title || 'Event';
            const ev = asset.eventDetails || {};
            const rec = ev.recurrence;
            const uidBase = asset.id || Date.now();
            const now = new Date().toISOString().replace(/-|:|\.\d\d\d/g, "");

            const baseDescription = this.getEventDescription();
            // Keep QR payloads scannable — harder when a series adds a rule per day.
            const descLimit = isForQR ? (rec && rec.slots.length > 1 ? 150 : 300) : Infinity;
            const describe = (extra) => {
                let text = extra ? `${extra}\n\n${baseDescription}` : baseDescription;
                if (text.length > descLimit) text = text.substring(0, descLimit - 3) + '...';
                return text.replace(/\n/g, '\\n');
            };

            let alarms = '';
            // Omit alarms for QR to reduce string length
            if (!isForQR) {
                const reminders = [
                    { trigger: '-P1D', desc: '1 day' },
                    { trigger: '-PT1H', desc: '1 hour' },
                    { trigger: '-PT5M', desc: '5 mins' }
                ];

                reminders.forEach(r => {
                    alarms += `BEGIN:VALARM\nTRIGGER:${r.trigger}\nACTION:DISPLAY\nDESCRIPTION:Reminder: ${title} in ${r.desc}\nEND:VALARM\n`;
                });
            }

            let events = '';
            if (rec && (rec.slots || []).length) {
                // One VEVENT per repeating day, each anchored on that day's next
                // session and carrying its own RRULE — so the buyer's calendar gets
                // the whole series, not just the next date, and each day keeps its
                // own time, length, title and link.
                (rec.slots || []).forEach(slot => {
                    const first = (ev.occurrences || []).find(o => o.slotId === slot.id);
                    if (!first) return; // this day has no session left to schedule
                    const start = new Date(first.utc);
                    const end = new Date(first.endUtc || (start.getTime() + (slot.duration || 60) * 60000));
                    if (isNaN(start.getTime())) return;
                    const stamp = (d) => d.toISOString().replace(/[-:]|\.\d{3}/g, '');
                    const summary = slot.label ? `${title} — ${slot.label}` : title;
                    const location = slot.link || ev.link || '';
                    events += `BEGIN:VEVENT\nUID:${uidBase}-${slot.id}@nyota.app\nDTSTAMP:${now}\n`
                        + `DTSTART:${stamp(start)}\nDTEND:${stamp(end)}\n`
                        + this._slotRecurrenceRule(slot)
                        + `SUMMARY:${summary}\nDESCRIPTION:${describe(slot.note)}\nLOCATION:${location}\n`
                        + `${alarms}END:VEVENT\n`;
                });
            }

            if (!events) {
                // One-off event (or a series with nothing scheduled ahead).
                const dates = this.getEventDates();
                events = `BEGIN:VEVENT\nUID:${uidBase}@nyota.app\nDTSTAMP:${now}\n`
                    + `DTSTART:${dates.icsStart}\nDTEND:${dates.icsEnd}\n`
                    + `SUMMARY:${title}\nDESCRIPTION:${describe('')}\nLOCATION:${ev.link || ''}\n`
                    + `${alarms}END:VEVENT\n`;
            }

            return `BEGIN:VCALENDAR\nVERSION:2.0\nPROID:-//Nyota//Asset Calendar//EN\n${events}END:VCALENDAR`;
        },

        smartCalendarSave() {
            try {
                const userAgent = navigator.userAgent || navigator.vendor || window.opera;
                const isAndroid = /android/i.test(userAgent);
                // Google's template URL can only express ONE event, so a series
                // that repeats on several days takes the ICS path everywhere —
                // dropping the other days would be worse than the extra download.
                const multiDaySeries = ((this.asset.eventDetails?.recurrence?.slots || []).length > 1);

                if (isAndroid && !multiDaySeries) {
                    window.open(this.getGoogleCalendarUrl(), '_blank');
                } else {
                    const icsString = this.generateICSString();
                    const blob = new Blob([icsString], { type: 'text/calendar;charset=utf-8' });
                    const link = document.createElement('a');
                    link.href = window.URL.createObjectURL(blob);
                    link.setAttribute('download', `${this.asset.slug || 'event'}.ics`);
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                }
            } catch (err) {
                console.error("Error saving to calendar:", err);
                this.showToast("Could not save to calendar. Invalid event details.", "error");
            }
        },

        getGoogleCalendarUrl() {
            const asset = this.asset;
            const ev = asset.eventDetails || {};
            const dates = this.getEventDates();
            // Google's template URL holds a single event, so it carries the next
            // session and — for a series — the rule for the day that session falls
            // on. Days beyond that come through the ICS path (the multi-day
            // "Save to calendar" fallback below).
            const nextSlot = ev.recurrence
                ? (ev.recurrence.slots || []).find(s => s.id === (ev.occurrences || [])[0]?.slotId)
                : null;
            const summary = nextSlot && nextSlot.label ? `${asset.title || 'Event'} — ${nextSlot.label}` : (asset.title || 'Event');
            const title = encodeURIComponent(summary);
            const description = encodeURIComponent(this.getEventDescription());
            const location = encodeURIComponent((nextSlot && nextSlot.link) || ev.link || '');

            let url = `https://www.google.com/calendar/render?action=TEMPLATE&text=${title}&details=${description}&location=${location}&dates=${dates.googleStart}/${dates.googleEnd}`;
            if (nextSlot) {
                const rule = this._slotRecurrenceRule(nextSlot).split('\n')[0]; // RRULE line only
                if (rule) url += `&recur=${encodeURIComponent(rule)}`;
            }
            return url;
        }
    }));

    Alpine.data('userLibrary', (currencySymbol) => ({
        purchasedAssets: [], activeTab: 'all', currency: currencySymbol,
        init() { try { const dataElement = document.getElementById('library-data'); if (dataElement) this.purchasedAssets = JSON.parse(dataElement.textContent); } catch (e) { console.error('Error parsing library data:', e); } },
        get filteredAssets() { if (this.activeTab === 'all') return this.purchasedAssets; return this.purchasedAssets.filter(asset => asset.asset_type === this.activeTab); },
        setTab(tab) { this.activeTab = tab; },
        formatCurrency(amount) { return new Intl.NumberFormat('en-US', { style: 'decimal', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount || 0); }
    }));

    Alpine.data('postPurchaseForm', (assetId, purchaseId, alreadyAnswered = false) => ({
        fields: [],
        formData: {},
        fileData: {},
        isSubmitting: false,
        submitted: false,
        alreadyAnswered: alreadyAnswered,
        // 'view' shows a read-only summary of submitted answers; 'edit' shows the form.
        mode: alreadyAnswered ? 'view' : 'edit',
        // In view mode the summary is a collapsed disclosure so it never competes with the
        // bought content above it. Expanded by default while filling/unlocking the form.
        open: !alreadyAnswered,
        // Saved delivery details from the buyer's last physical order (one-tap prefill).
        savedAnswers: {},
        prefillApplied: false,
        // Per-question geolocation state: '' | 'locating' | 'set' | 'error'
        locState: {},
        i18n: { locating: 'Getting your location...', location_set: 'Location received', location_denied: "We couldn't get your location. You can type it or paste a link instead." },
        init() {
            // Field definitions and any existing answers are read from JSON <script> tags rather
            // than inline attribute arguments — embedding the JSON directly in x-data breaks the
            // HTML attribute (its double quotes close the attribute early) and the form never renders.
            try {
                const el = document.getElementById('post-purchase-fields-' + assetId);
                const parsed = el ? JSON.parse(el.textContent || '[]') : [];
                this.fields = Array.isArray(parsed) ? parsed : [];
            } catch (e) {
                this.fields = [];
                console.error('Failed to parse post-purchase fields:', e);
            }

            let answers = {};
            try {
                const el = document.getElementById('post-purchase-answers-' + assetId);
                answers = el ? (JSON.parse(el.textContent || '{}') || {}) : {};
            } catch (e) {
                answers = {};
            }
            // Internal order keys (tier/variation/quantity) — never shown or edited
            ['tier', 'variation', 'quantity'].forEach(k => delete answers[k]);

            // Saved delivery details (physical orders only; emitted server-side only
            // for a session already authorized to edit this purchase).
            try {
                const sd = document.getElementById('saved-delivery-' + assetId);
                this.savedAnswers = sd ? (JSON.parse(sd.textContent || '{}') || {}) : {};
            } catch (e) { this.savedAnswers = {}; }

            // Localized strings for the location widget.
            try {
                const di = document.getElementById('delivery-i18n');
                if (di) this.i18n = Object.assign({}, this.i18n, JSON.parse(di.textContent || '{}'));
            } catch (e) { }

            // Seed formData: reuse an existing answer when present, else a sensible empty default.
            this.fields.forEach(field => {
                const existing = answers[field.question];
                if (field.type === 'file') {
                    this.fileData[field.question] = null;
                    // Show original filename if already uploaded
                    this.formData[field.question] = (existing && existing.__file__)
                        ? existing.original_name : '';
                } else if (field.type === 'location') {
                    this.formData[field.question] = this._locationValue(existing);
                    this.locState[field.question] = this._hasPin(existing) ? 'set' : '';
                } else if (existing !== undefined && existing !== null) {
                    this.formData[field.question] = existing;
                } else {
                    this.formData[field.question] = field.type === 'checkbox' ? false : '';
                }
            });
        },
        // --- Location-answer helpers ---
        _locationValue(v) {
            v = (v && typeof v === 'object' && v.__location__) ? v : {};
            return { __location__: true, lat: v.lat ?? null, lng: v.lng ?? null, maps_url: v.maps_url || '', text: v.text || '' };
        },
        _hasPin(v) {
            return !!(v && typeof v === 'object' && v.lat !== null && v.lat !== undefined && v.lat !== '');
        },
        hasLocationValue(v) {
            return !!(v && typeof v === 'object'
                && (this._hasPin(v) || (v.maps_url || '').trim() || (v.text || '').trim()));
        },
        shareLocation(question) {
            if (!navigator.geolocation) { this.locState[question] = 'error'; return; }
            this.locState[question] = 'locating';
            navigator.geolocation.getCurrentPosition(
                pos => {
                    const v = this.formData[question];
                    v.lat = +pos.coords.latitude.toFixed(6);
                    v.lng = +pos.coords.longitude.toFixed(6);
                    this.locState[question] = 'set';
                },
                () => { this.locState[question] = 'error'; },
                { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
            );
        },
        clearLocation(question) {
            const v = this.formData[question];
            v.lat = null; v.lng = null;
            this.locState[question] = '';
        },
        locationLink(v) {
            if (!v || typeof v !== 'object') return '';
            if ((v.maps_url || '').trim()) return v.maps_url.trim();
            if (this._hasPin(v)) return `https://www.google.com/maps?q=${v.lat},${v.lng}`;
            return '';
        },
        // --- "Use my last details" prefill ---
        get hasSavedAnswers() {
            if (this.alreadyAnswered || this.prefillApplied) return false;
            const saved = this.savedAnswers || {};
            return this.fields.some(f => f.type !== 'file' && saved[f.question] !== undefined && saved[f.question] !== null);
        },
        applySavedAnswers() {
            this.fields.forEach(field => {
                const saved = (this.savedAnswers || {})[field.question];
                if (saved === undefined || saved === null || field.type === 'file') return;
                if (field.type === 'location') {
                    this.formData[field.question] = this._locationValue(saved);
                    this.locState[field.question] = this._hasPin(saved) ? 'set' : '';
                } else {
                    this.formData[field.question] = saved;
                }
            });
            this.prefillApplied = true;
        },
        // Human-readable value for the read-only summary.
        displayValue(field) {
            const v = this.formData[field.question];
            if (field.type === 'checkbox') return v ? 'Yes' : 'No';
            if (field.type === 'file') return v ? v : '—';
            if (field.type === 'location') {
                if (!this.hasLocationValue(v)) return '—';
                return this.locationLink(v) || (v.text || '').trim() || '—';
            }
            return (v === '' || v === null || v === undefined) ? '—' : v;
        },
        handleFileSelect(question, event) {
            const file = event.target.files[0] || null;
            this.fileData[question] = file;
            this.formData[question] = file ? file.name : '';
        },
        get currentStep() {
            const total = this.fields.length;
            const answered = this.fields.filter(f => {
                if (f.type === 'file') return !!this.fileData[f.question];
                if (f.type === 'location') return this.hasLocationValue(this.formData[f.question]);
                const v = this.formData[f.question];
                return v !== '' && v !== false && v !== null && v !== undefined;
            }).length;
            return { answered, total };
        },
        async submit() {
            this.isSubmitting = true;
            try {
                // Step 1: collect non-file answers
                const textAnswers = {};
                this.fields.forEach(f => {
                    if (f.type === 'file') return;
                    if (f.type === 'location') {
                        // Only send a location when it actually carries something.
                        const v = this.formData[f.question];
                        if (this.hasLocationValue(v)) textAnswers[f.question] = v;
                        return;
                    }
                    textAnswers[f.question] = this.formData[f.question];
                });

                // Step 2: submit text answers to existing endpoint
                if (Object.keys(textAnswers).length > 0) {
                    const r = await fetch(`/api/purchases/${purchaseId}/ticket-data`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ ticket_data: textAnswers })
                    });
                    const result = await r.json();
                    if (!r.ok || !result.success) {
                        alert(result.message || 'Error submitting answers.');
                        return;
                    }
                }

                // Step 3: upload each file answer
                for (const field of this.fields) {
                    if (field.type !== 'file') continue;
                    const file = this.fileData[field.question];
                    if (!file && field.required) {
                        alert(`Please select a file for "${field.question}".`);
                        return;
                    }
                    if (!file) continue;

                    const maxBytes = (field.maxSizeMb || 5) * 1024 * 1024;
                    if (file.size > maxBytes) {
                        alert(`"${field.question}": file exceeds the ${field.maxSizeMb || 5} MB limit.`);
                        return;
                    }

                    const fd = new FormData();
                    fd.append('question_name', field.question);
                    fd.append('file', file);
                    const fr = await fetch(`/api/purchases/${purchaseId}/ticket-file`, {
                        method: 'POST',
                        body: fd
                    });
                    const fres = await fr.json();
                    if (!fr.ok || !fres.success) {
                        alert(fres.message || `Error uploading file for "${field.question}".`);
                        return;
                    }
                }

                this.submitted = true;
                setTimeout(() => window.location.reload(), 1500);
            } catch (e) {
                alert('A network error occurred.');
            } finally {
                this.isSubmitting = false;
            }
        }
    }));

    // ========================================================================
    // == ADMIN COMPONENTS
    // ========================================================================

    Alpine.data('adminAssets', () => ({
        assets: [], filteredAssets: [], viewMode: 'list', searchTerm: '', statusFilter: 'all', typeFilter: 'all',
        sortBy: 'updated_at', sortAsc: false, selectedAssets: [], bulkAction: '', currentPage: 1, itemsPerPage: 10,

        init() {
            try {
                const dataElement = document.getElementById('assets-data');
                if (dataElement && dataElement.textContent) {
                    this.assets = Array.isArray(JSON.parse(dataElement.textContent)) ? JSON.parse(dataElement.textContent) : [];
                }
            } catch (e) { this.assets = []; console.error('Error parsing assets data:', e); }

            // Load UI preferences from localStorage
            const savedPreferences = JSON.parse(localStorage.getItem('adminAssetsPreferences')) || {};
            this.viewMode = savedPreferences.viewMode || 'list';
            this.searchTerm = savedPreferences.searchTerm || '';
            this.statusFilter = savedPreferences.statusFilter || 'all';
            this.typeFilter = savedPreferences.typeFilter || 'all';
            this.sortBy = savedPreferences.sortBy || 'updated_at';
            this.sortAsc = savedPreferences.sortAsc !== undefined ? savedPreferences.sortAsc : false;
            this.itemsPerPage = savedPreferences.itemsPerPage || 10;
            this.currentPage = savedPreferences.currentPage || 1; // Load currentPage

            this.$watch(() => [this.searchTerm, this.statusFilter, this.typeFilter, this.sortBy, this.sortAsc], () => {
                this.applyFiltersAndSort();
                this.currentPage = 1; // Reset to first page on filter/sort change
                this.savePreferences();
            });

            this.$watch(() => [this.viewMode, this.itemsPerPage, this.currentPage], () => this.savePreferences());

            this.applyFiltersAndSort(); // Initial application of filters and sort
        },

        savePreferences() {
            localStorage.setItem('adminAssetsPreferences', JSON.stringify({
                viewMode: this.viewMode,
                searchTerm: this.searchTerm,
                statusFilter: this.statusFilter,
                typeFilter: this.typeFilter,
                sortBy: this.sortBy,
                sortAsc: this.sortAsc,
                itemsPerPage: this.itemsPerPage,
                currentPage: this.currentPage,
            }));
        },

        applyFiltersAndSort() {
            let temp = [...this.assets];
            if (this.searchTerm.trim()) { const s = this.searchTerm.toLowerCase(); temp = temp.filter(a => (a.title && a.title.toLowerCase().includes(s)) || (a.description && a.description.toLowerCase().includes(s))); }
            if (this.statusFilter !== 'all') { temp = temp.filter(a => a.status === this.statusFilter); }
            if (this.typeFilter !== 'all') { temp = temp.filter(a => a.type.toLowerCase().replace(/_/g, '-') === this.typeFilter); }
            temp.sort((a, b) => { let vA, vB; switch (this.sortBy) { case 'title': vA = a.title.toLowerCase(); vB = b.title.toLowerCase(); break; case 'sales': vA = a.sales || 0; vB = b.sales || 0; break; case 'revenue': vA = a.revenue || 0; vB = b.revenue || 0; break; default: vA = new Date(a.updated_at); vB = new Date(b.updated_at); break; } if (vA < vB) return this.sortAsc ? -1 : 1; if (vA > vB) return this.sortAsc ? 1 : -1; return 0; });
            this.filteredAssets = temp;
        },

        // --- Pagination ---
        get paginatedAssets() {
            const start = (this.currentPage - 1) * this.itemsPerPage;
            const end = start + this.itemsPerPage;
            return this.filteredAssets.slice(start, end);
        },
        get totalPages() {
            return Math.ceil(this.filteredAssets.length / this.itemsPerPage);
        },
        goToPage(page) {
            if (page >= 1 && page <= this.totalPages) {
                this.currentPage = page;
            }
        },
        nextPage() {
            if (this.currentPage < this.totalPages) {
                this.currentPage++;
            }
        },
        prevPage() {
            if (this.currentPage > 1) {
                this.currentPage--;
            }
        },

        // --- Action Methods ---
        async applyBulkAction() {
            if (!this.bulkAction || this.selectedAssets.length === 0) return alert('Please select an action and at least one asset.');
            if (this.bulkAction === 'delete' && !confirm(`Permanently delete ${this.selectedAssets.length} asset(s)? This cannot be undone.`)) return;

            try {
                const response = await fetch('/admin/api/assets/bulk-action', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: this.bulkAction, ids: this.selectedAssets })
                });
                const result = await response.json();
                if (response.ok && result.success) {
                    alert(result.message);
                    window.location.reload();
                } else {
                    alert('Error: ' + (result.message || 'An unknown error occurred.'));
                }
            } catch (e) {
                alert('A server connection error occurred.');
            }
        },
        confirmDelete(assetId) {
            if (confirm('Are you sure you want to permanently delete this asset?')) {
                this.selectedAssets = [assetId];
                this.bulkAction = 'delete';
                this.applyBulkAction();
            }
        },
        async duplicateAsset(assetId) {
            if (confirm('Create a duplicate of this asset? It will be saved as a draft.')) {
                try {
                    const response = await fetch(`/admin/api/assets/${assetId}/duplicate`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                    });
                    const result = await response.json();
                    if (response.ok && result.success) {
                        alert(result.message);
                        window.location.reload();
                    } else {
                        alert('Error: ' + (result.message || 'An unknown error occurred.'));
                    }
                } catch (e) {
                    alert('A server connection error occurred.');
                }
            }
        },

        // --- UI & Helper Methods ---
        getStatusCount(status) { return this.assets.filter(a => a.status === status).length; },
        getTotalRevenue() { return this.assets.reduce((sum, asset) => sum + (parseFloat(asset.revenue) || 0), 0); },
        getTotalSales() { return this.assets.reduce((sum, asset) => sum + (parseInt(asset.sales) || 0), 0); },
        formatDate(iso) { if (!iso) return 'N/A'; return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }); },
        getStatusClasses(status) { return { 'Published': 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300', 'Draft': 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300', 'Archived': 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300' }[status] || 'bg-gray-100 text-gray-800'; },
        getAssetTypeLabel(type) { if (!type) return 'Product'; return type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()); },
        toggleSelectAll(event) { if (event.target.checked) { this.selectedAssets = this.filteredAssets.map(a => a.id); } else { this.selectedAssets = []; } },
        hasActiveFilters() { return this.searchTerm || this.statusFilter !== 'all' || this.typeFilter !== 'all' },
        getActiveFilters() { let f = []; if (this.searchTerm) f.push({ key: 'searchTerm', label: `Search: "${this.searchTerm}"` }); if (this.statusFilter !== 'all') f.push({ key: 'statusFilter', label: `Status: ${this.statusFilter}` }); if (this.typeFilter !== 'all') f.push({ key: 'typeFilter', label: `Type: ${this.typeFilter.replace('-', ' ')}` }); return f; },
        removeFilter(key) { this[key] = key === 'searchTerm' ? '' : 'all'; },
        clearAllFilters() { this.searchTerm = ''; this.statusFilter = 'all'; this.typeFilter = 'all'; },
    }));

    Alpine.data('assetForm', () => withRecurrenceEditor(withCtaEditor({
        ctaTarget() { return this.donation; },
        _recurrence() {
            if (!this.eventDetails.recurrence) {
                this.eventDetails.recurrence = recurrenceEditor._hydrateRecurrence(null);
            }
            return this.eventDetails.recurrence;
        },
        _eventSeed() { return { date: this.eventDetails.date, time: this.eventDetails.time }; },
        step: 1,
        asset: { id: null, title: '', description: '', cover_image_url: null, story_snippet: '' },
        assetType: '',
        assetTypeEnum: '',
        contentItems: [],
        customFields: [],
        eventDetails: {
            link: '', maxAttendees: null, date: '', time: '', postPurchaseInstructions: '',
            recurrence: recurrenceEditor._hydrateRecurrence(null)
        },
        subscriptionDetails: { welcomeContent: '', benefits: '' },
        newsletterDetails: { welcomeFile: null, welcomeDescription: '', frequency: 'monthly' },
        pricing: { type: 'one-time', amount: null, billingCycle: 'monthly', tiers: [] },
        donation: { enabled: false, min_amount: 0, mandatory: false, _suggestedRaw: '', cta: CTA_FALLBACK.id, cta_custom: { en: '', sw: '' } },
        variations: [],
        // Default delivery questions (creator's language) seeded onto new physical
        // products; parsed from the #delivery-defaults JSON island.
        _deliveryDefaults: [],
        positionPreference: 'bottom',
        collectInfoMode: 'optional',
        steps: [{ number: 1, title: 'Type', subtitle: 'Choose content format' }, { number: 2, title: 'Details', subtitle: 'Describe your asset' }, { number: 3, title: 'Content', subtitle: 'Add files/links' }, { number: 4, title: 'Pricing', subtitle: 'Set your price' }],

        init() {
            try {
                const dd = document.getElementById('delivery-defaults');
                this._deliveryDefaults = dd ? (JSON.parse(dd.textContent || '[]') || []) : [];
            } catch (e) { this._deliveryDefaults = []; }

            const dataElement = document.getElementById('asset-form-data');
            if (dataElement && dataElement.textContent.trim() !== '{}') {
                const existing = JSON.parse(dataElement.textContent);
                this.asset = { id: existing.id, title: existing.title, description: existing.description, cover_image_url: existing.cover_image_url, story_snippet: existing.story };
                this.assetType = this.mapEnumTypeToFormType(existing.asset_type);
                this.assetTypeEnum = existing.asset_type;

                // Initialize content items with type detection
                this.contentItems = (existing.files || []).map(f => ({
                    ...f,
                    type: f.link && !f.link.startsWith('/content/') ? 'link' : 'upload'
                }));

                this.customFields = existing.custom_fields || [];
                this.variations = (existing.details?.variations || []).map(v => ({ ...v }));

                // Initialize event details
                this.eventDetails = {
                    link: existing.eventDetails?.link || existing.event_location,
                    maxAttendees: existing.eventDetails?.maxAttendees || existing.max_attendees,
                    date: existing.eventDetails?.date || existing.event_date,
                    time: existing.eventDetails?.time || existing.event_time,
                    postPurchaseInstructions: existing.details?.postPurchaseInstructions || '',
                    recurrence: recurrenceEditor._hydrateRecurrence(existing.eventDetails?.recurrence)
                };

                // Initialize pricing and tiers
                const isSubscription = existing.is_subscription;
                this.pricing = {
                    type: isSubscription ? 'recurring' : 'one-time',
                    amount: existing.price,
                    billingCycle: existing.subscription_interval || 'monthly',
                    tiers: existing.details?.subscription_tiers || []
                };

                if (existing.details) {
                    this.subscriptionDetails = existing.details.welcomeContent ? existing.details : this.subscriptionDetails;
                    this.newsletterDetails = existing.details.frequency ? existing.details : this.newsletterDetails;
                }

                // Initialize donation / flexible-amount config
                const dExisting = existing.details?.donation || {};
                this.donation = {
                    enabled: !!dExisting.enabled,
                    min_amount: dExisting.min_amount || 0,
                    mandatory: !!dExisting.mandatory,
                    _suggestedRaw: Array.isArray(dExisting.suggested_amounts) ? dExisting.suggested_amounts.join(', ') : '',
                    cta: dExisting.cta || CTA_FALLBACK.id,
                    cta_custom: {
                        en: (dExisting.cta_custom || {}).en || '',
                        sw: (dExisting.cta_custom || {}).sw || ''
                    }
                };

                // FIX: Only jump to step 2 if we are EDITING an existing asset (has ID)
                this.step = existing.id ? 2 : 1;
            }
            this.$nextTick(() => { this._initMDEditors(); });
        },

        _initMDEditors() {
            bindMarkdownEditor(
                document.getElementById('description'), { minHeight: '110px' },
                () => this.asset.description,
                v => { this.asset.description = v; }
            );
            bindMarkdownEditor(
                document.getElementById('story'), { minHeight: '260px' },
                () => this.asset.story_snippet,
                v => { this.asset.story_snippet = v; }
            );
        },
        setAssetType(type) {
            this.assetType = type;
            this.assetTypeEnum = this.mapFormTypeToEnumType(type);
            if (type === 'physical') {
                // Physical goods are plain one-time sales, and they arrive with the
                // delivery questionnaire pre-seeded (still fully editable/removable).
                this.pricing.type = 'one-time';
                this.donation.enabled = false;
                if (!this.customFields.length && this._deliveryDefaults.length) {
                    this.customFields = this._deliveryDefaults.map(f => ({
                        type: f.type || 'text', question: f.question || '', required: !!f.required,
                        options: [], _optionsRaw: '', accept: '', maxSizeMb: 5
                    }));
                    this.collectInfoMode = 'reminder';
                }
            }
        },
        addContentItem(defaultType = 'upload') { this.contentItems.push({ type: defaultType, title: '', link: '', description: '' }); },
        removeContentItem(index) { this.contentItems.splice(index, 1); },
        addCustomField() { this.customFields.push({ type: 'text', question: '', required: false, options: [], _optionsRaw: '', accept: '', maxSizeMb: 5 }); },
        removeCustomField(index) { this.customFields.splice(index, 1); },
        addPricingTier() { this.pricing.tiers.push({ name: '', price: null, interval: 'monthly', description: '' }); },
        removePricingTier(index) { this.pricing.tiers.splice(index, 1); },
        addVariation() { this.variations.push({ id: newVariationId(), name: '', price: null, photo_url: null, sold_out: false }); },
        removeVariation(index) { this.variations.splice(index, 1); },
        previewVariationPhoto(variation, event) {
            const file = event.target.files[0];
            if (file) { variation.photo_url = URL.createObjectURL(file); }
        },
        previewCoverImage(event) { const file = event.target.files[0]; if (file) { this.asset.cover_image_url = URL.createObjectURL(file); } },
        submitForm(action) {
            // Clean custom fields: derive dropdown options + drop editor-only helpers.
            const cleanedCustomFields = (this.customFields || []).map(f => {
                const out = { type: f.type || 'text', question: f.question || '', required: !!f.required };
                if (f.type === 'select') {
                    out.options = (f._optionsRaw || (Array.isArray(f.options) ? f.options.join(', ') : ''))
                        .split(',').map(s => s.trim()).filter(Boolean);
                }
                if (f.type === 'file') {
                    out.accept = f.accept || '';
                    out.maxSizeMb = f.maxSizeMb || 5;
                }
                return out;
            }).filter(f => f.question.trim());

            // Sanitize donation config (only for one-time / non-subscription assets).
            const donationEnabled = !!this.donation.enabled && this.pricing.type !== 'recurring';
            const donation = {
                enabled: donationEnabled,
                min_amount: parseFloat(this.donation.min_amount) || 0,
                mandatory: !!this.donation.mandatory,
                suggested_amounts: (this.donation._suggestedRaw || '')
                    .split(',').map(s => parseFloat(s.trim())).filter(n => !isNaN(n) && n > 0),
                cta: this.donation.cta || CTA_FALLBACK.id,
                cta_custom: {
                    en: (this.donation.cta_custom?.en || '').trim(),
                    sw: (this.donation.cta_custom?.sw || '').trim()
                }
            };
            // A donation asset is always free at base — the contribution is the charge.
            const pricing = donationEnabled ? { ...this.pricing, amount: 0 } : this.pricing;

            // Prepare data for submission
            const allData = {
                action: action,
                asset: this.asset,
                assetTypeEnum: this.assetTypeEnum,
                contentItems: this.contentItems,
                customFields: cleanedCustomFields,
                collect_info_mode: this.collectInfoMode || 'optional',
                eventDetails: { ...this.eventDetails, recurrence: this.buildRecurrencePayload() },
                subscriptionDetails: this.subscriptionDetails,
                newsletterDetails: { ...this.newsletterDetails, welcomeFile: null },
                donation: donation,
                variations: (this.variations || [])
                    .map(v => ({
                        id: v.id, name: (v.name || '').trim(),
                        price: (v.price === null || v.price === '') ? null : parseFloat(v.price),
                        // Blob previews are editor-only; the real URL comes back from the upload.
                        photo_url: (v.photo_url && !v.photo_url.startsWith('blob:')) ? v.photo_url : null,
                        sold_out: !!v.sold_out
                    }))
                    .filter(v => v.name),
                pricing: pricing,
                position_preference: this.positionPreference || 'bottom'
            };

            const hidden = document.createElement('input');
            hidden.type = 'hidden';
            hidden.name = 'asset_data';
            hidden.value = JSON.stringify(allData);
            this.$refs.assetForm.appendChild(hidden);
            this.$refs.assetForm.submit();
        },

        // Asset Type Details — descriptions, examples, and guide tips
        assetTypeDetails: {
            'video-series': {
                title: 'Video Course',
                description: 'A structured series of video lessons your audience can purchase and watch at their own pace. Ideal for teaching skills, sharing knowledge, or building a curriculum.',
                contentDescription: 'Add your course videos — upload files or paste links from YouTube, Vimeo, etc.',
                examples: ['Online cooking class', 'Photography masterclass', 'Fitness workout series'],
                guide: ['Give each lesson a clear, numbered title (e.g. "Lesson 1: Getting Started")', 'Add a short description so students know what each video covers', 'You can mix uploaded videos and external links']
            },
            'ticket': {
                title: 'Event & Webinar',
                description: 'Sell access to a live or virtual event. Attendees register and purchase a ticket, then receive instructions on how to join.',
                contentDescription: 'Configure your event — set the date, time, location/link, and any custom registration questions.',
                examples: ['Zoom workshop', 'In-person seminar', 'Live Q&A session'],
                guide: ['Set a clear date & time so attendees can plan ahead', 'Add a Zoom/Meet link or physical address', 'Use custom questions to collect info like T-shirt size or dietary needs']
            },
            'digital-file': {
                title: 'Digital Product',
                description: 'Sell downloadable files — e-books, templates, presets, design assets, music, or any digital file your audience can download after purchase.',
                contentDescription: 'Upload your files. You can add multiple files, each with optional release and expiration dates.',
                examples: ['E-book (PDF)', 'Lightroom presets pack', 'Canva templates bundle'],
                guide: ['Bundle related files into a single zip for a cleaner experience', 'Use descriptive file names so buyers know what they\'re getting', 'Test your downloads before publishing']
            },
            'subscription': {
                title: 'Subscription',
                description: 'Offer recurring paid access to exclusive content, community, or services. Subscribers are billed on a regular cycle and retain access as long as they\'re subscribed.',
                contentDescription: 'Describe what subscribers will receive — welcome content and ongoing benefits.',
                examples: ['Monthly exclusive articles', 'Private community membership', 'Weekly coaching calls'],
                guide: ['Clearly list what subscribers get so they understand the value', 'Create pricing tiers (e.g. Monthly, Quarterly, Annual) with different prices', 'Write a warm welcome message for new subscribers']
            },
            'newsletter': {
                title: 'Newsletter',
                description: 'Build a paid newsletter — subscribers pay for regular, exclusive written content delivered on a schedule you define.',
                contentDescription: 'Set up your welcome content and choose how often you\'ll send new editions.',
                examples: ['Weekly industry insights', 'Monthly market analysis', 'Bi-weekly creative writing'],
                guide: ['Include a high-value welcome PDF or message so new subscribers feel it\'s worth it', 'Pick a frequency you can consistently maintain', 'Set clear expectations about what each edition will cover']
            },
            'physical': {
                title: 'Physical Product',
                description: 'Sell real, deliverable goods — clothing, crafts, books, food, electronics. Buyers pick a variation and quantity, pay with mobile money, then share their delivery details.',
                contentDescription: 'Add the variations buyers can choose from (e.g. size or colour), each with its own optional photo and price.',
                examples: ['Branded T-shirts (S/M/L)', 'Handmade bags', 'Packaged spices'],
                guide: ['Add a photo per variation so buyers see exactly what they\'re choosing', 'Leave a variation\'s price empty to use the base price', 'A delivery questionnaire is attached automatically — edit it in the Questionnaire tab', 'Mark a variation "sold out" instead of deleting it when stock runs dry']
            }
        },

        getAssetTypeDetails() { return this.assetTypeDetails[this.assetType] || { title: 'Asset', contentDescription: '', description: '', examples: [], guide: [] }; },
        mapEnumTypeToFormType(enumType) { const map = { 'VIDEO_SERIES': 'video-series', 'TICKET': 'ticket', 'DIGITAL_PRODUCT': 'digital-file', 'SUBSCRIPTION': 'subscription', 'NEWSLETTER': 'newsletter', 'PHYSICAL': 'physical' }; return map[enumType]; },
        mapFormTypeToEnumType(formType) { const map = { 'video-series': 'VIDEO_SERIES', 'ticket': 'TICKET', 'digital-file': 'DIGITAL_PRODUCT', 'subscription': 'SUBSCRIPTION', 'newsletter': 'NEWSLETTER', 'physical': 'PHYSICAL' }; return map[formType]; },
    })));

    Alpine.data('settingsPage', (initialSettings) => ({
        // --- State ---
        settings: initialSettings || {}, // Guard against null/undefined data
        mainTab: 'storeProfile',
        integrationTab: 'notifications',
        storeLogo: null, // Initialize as null, set in init()

        // Form states
        telegramEnabled: false,
        whatsappEnabled: false,
        smtpEnabled: false,
        aiEnabled: false,

        // Testing states
        telegramTesting: false,
        telegramTested: false,
        telegramTestSuccess: false,
        emailTesting: false,
        emailTested: false,
        emailTestSuccess: false,
        testEmailAddress: '',
        testSMSNumber: '',
        smsEnabled: false,
        smsTesting: false,
        smsTested: false,
        smsTestSuccess: false,
        smsTestMessage: '',
        metaPixelEnabled: false,
        gaEnabled: false,

        // Footer: links and opening hours are edited as structures and posted as
        // JSON in a single hidden field each (see the footer section of settings.html).
        footerLinks: [],
        businessHours: {},
        weekdays: [
            { key: 'mon', label: 'Monday' },
            { key: 'tue', label: 'Tuesday' },
            { key: 'wed', label: 'Wednesday' },
            { key: 'thu', label: 'Thursday' },
            { key: 'fri', label: 'Friday' },
            { key: 'sat', label: 'Saturday' },
            { key: 'sun', label: 'Sunday' },
        ],
        maxFooterLinks: 3,

        init() {
            // Populate state from the initial settings object
            this.storeLogo = this.settings.store_logo_url || '';
            this.telegramEnabled = this.settings.telegram_enabled || false;
            this.whatsappEnabled = this.settings.whatsapp_enabled || false;
            this.smtpEnabled = this.settings.email_smtp_enabled || false;
            this.smsEnabled = this.settings.sms_enabled || false;
            this.aiEnabled = this.settings.ai_enabled || false;
            this.metaPixelEnabled = this.settings.marketing_meta_pixel_enabled || false;
            this.gaEnabled = this.settings.marketing_ga_enabled || false;

            // Footer defaults. A store that has never opened this tab has no rows at
            // all, so seed the selects (an unmatched x-model would render blank) and
            // switch on the two things every store wants.
            ['footer_about_visibility', 'footer_contact_visibility', 'footer_address_visibility', 'footer_hours_visibility']
                .forEach(key => {
                    if (!this.settings[key]) this.settings[key] = 'public';
                });
            if (this.settings.footer_enabled === undefined) this.settings.footer_enabled = true;
            if (this.settings.footer_credit_enabled === undefined) this.settings.footer_credit_enabled = true;

            // Footer structures. Both are stored as JSON in CreatorSetting.value, but
            // tolerate a string in case an older row was written as text.
            this.footerLinks = this.parseStructure(this.settings.footer_links, []);
            if (!Array.isArray(this.footerLinks)) this.footerLinks = [];
            this.footerLinks = this.footerLinks.slice(0, this.maxFooterLinks).map(link => ({
                title: link.title || '',
                description: link.description || '',
                url: link.url || '',
            }));

            const savedHours = this.parseStructure(this.settings.business_hours, {}) || {};
            this.businessHours = {};
            this.weekdays.forEach(day => {
                const entry = savedHours[day.key] || {};
                this.businessHours[day.key] = {
                    closed: !!entry.closed,
                    open: entry.open || '',
                    close: entry.close || '',
                };
            });

            // Restore the last-open tabs so a refresh returns to the same view.
            const validMainTabs = ['storeProfile', 'appearance', 'footer', 'integrations'];
            const validIntegrationTabs = ['notifications', 'payments', 'marketing'];
            const savedMainTab = localStorage.getItem('adminSettingsMainTab');
            const savedIntegrationTab = localStorage.getItem('adminSettingsIntegrationTab');
            if (validMainTabs.includes(savedMainTab)) this.mainTab = savedMainTab;
            if (validIntegrationTabs.includes(savedIntegrationTab)) this.integrationTab = savedIntegrationTab;
            this.$watch('mainTab', val => localStorage.setItem('adminSettingsMainTab', val));
            this.$watch('integrationTab', val => localStorage.setItem('adminSettingsIntegrationTab', val));

            // This is just for the local theme picker, separate from saved settings
            const theme = localStorage.getItem('theme') || 'system';
            this.$dispatch('set-theme', theme);
        },

        setTheme(newTheme) {
            // This method updates the LIVE theme, not the saved setting
            this.$dispatch('set-theme', newTheme);
        },

        // --- Footer helpers ---

        parseStructure(value, fallback) {
            if (value === null || value === undefined || value === '') return fallback;
            if (typeof value === 'object') return value;
            try {
                return JSON.parse(value);
            } catch (e) {
                console.warn('[Nyota] Ignoring unreadable footer setting:', e);
                return fallback;
            }
        },

        addFooterLink() {
            if (this.footerLinks.length >= this.maxFooterLinks) return;
            this.footerLinks.push({ title: '', description: '', url: '' });
        },

        removeFooterLink(index) {
            this.footerLinks.splice(index, 1);
        },

        // Copy one day's hours down to every other open day — the common case is
        // the same window Mon–Fri.
        applyHoursToAll(sourceKey) {
            const source = this.businessHours[sourceKey];
            if (!source) return;
            this.weekdays.forEach(day => {
                if (day.key === sourceKey) return;
                if (this.businessHours[day.key].closed) return;
                this.businessHours[day.key].open = source.open;
                this.businessHours[day.key].close = source.close;
            });
        },

        previewStoreLogo(event) {
            const file = event.target.files[0];
            if (file) {
                this.storeLogo = URL.createObjectURL(file);
            }
        },

        // Test methods (placeholders)
        testTelegram() {
            this.telegramTesting = true;
            setTimeout(() => {
                this.telegramTesting = false;
                this.telegramTested = true;
                this.telegramTestSuccess = Math.random() > 0.3;
            }, 2000);
        },
        testEmail() {
            if (!this.testEmailAddress.trim()) {
                alert('Please enter an email address to send a test to.');
                return;
            }
            this.emailTesting = true;
            setTimeout(() => {
                this.emailTesting = false;
                this.emailTested = true;
                this.emailTestSuccess = Math.random() > 0.2;
            }, 2500);
        },
        testWhatsApp() { alert('Testing WhatsApp...'); },
        testWhatsApp() { alert('Testing WhatsApp...'); },
        testSMS() {
            if (!this.testSMSNumber || !this.testSMSNumber.trim()) {
                alert('Please enter a phone number to send a test SMS to.');
                return;
            }
            this.smsTesting = true;
            this.smsTested = false;

            const formData = new FormData();
            formData.append('phone', this.testSMSNumber);

            fetch('/admin/settings/sms/test', {
                method: 'POST',
                body: formData
            })
                .then(response => response.json())
                .then(data => {
                    this.smsTesting = false;
                    this.smsTested = true;
                    this.smsTestSuccess = data.success;
                    this.smsTestMessage = data.message;
                })
                .catch(error => {
                    this.smsTesting = false;
                    this.smsTested = true;
                    this.smsTestSuccess = false;
                    this.smsTestMessage = 'Network error occurred.';
                    console.error('Error:', error);
                });
        },
        testAI() { alert('Testing AI...'); },
        testInstagram() { alert('Testing Instagram...'); },
        connectInstagram() { alert('Connecting to Instagram...'); },
        connectGoogle() { alert('Connecting to Google...'); },
    }));

    Alpine.data('assetView', (initialAsset, allStatuses) => withRecurrenceEditor(withCtaEditor({
        ctaTarget() { return this.editableAsset.donation; },
        _recurrence() {
            if (!this.editableAsset.eventDetails) this.editableAsset.eventDetails = {};
            if (!this.editableAsset.eventDetails.recurrence) {
                this.editableAsset.eventDetails.recurrence = recurrenceEditor._hydrateRecurrence(null);
            }
            return this.editableAsset.eventDetails.recurrence;
        },
        _eventSeed() { return { date: this.editableAsset.eventDetails?.date, time: this.editableAsset.eventDetails?.time }; },
        // Original data from the server. Guard against null.
        // Original data from the server. Guard against null.
        asset: initialAsset || {},
        // A mutable copy for the form. Initialize immediately to prevent template errors.
        editableAsset: JSON.parse(JSON.stringify(initialAsset || {})),

        statuses: allStatuses || [],
        activeTab: 'general',
        isSaving: false,
        notification: { show: false, message: '', type: 'success' },
        previewImage: null,

        init() {
            // Initialize preview image
            this.previewImage = this.asset.cover_image_url;

            // Restore the last-open tab so a refresh returns to the same view.
            // Fall back to General if the saved tab isn't valid for this asset type.
            const validTabs = ['general', 'configuration', 'content', 'questionnaire', 'responses', 'activity'];
            let savedTab = localStorage.getItem('adminAssetViewTab');
            if (savedTab && validTabs.includes(savedTab)) {
                const configurableTypes = ['TICKET', 'SUBSCRIPTION', 'NEWSLETTER', 'PHYSICAL'];
                if (savedTab === 'configuration' && !configurableTypes.includes(this.asset.asset_type)) {
                    savedTab = 'general';
                }
                this.activeTab = savedTab;
            }
            this.$watch('activeTab', val => localStorage.setItem('adminAssetViewTab', val));

            // Safely add the nested properties if they don't exist.
            if (!this.editableAsset.eventDetails) {
                this.editableAsset.eventDetails = {
                    link: this.asset.eventDetails?.link || '',
                    date: this.asset.eventDetails?.date || '',
                    time: this.asset.eventDetails?.time || '',
                    maxAttendees: this.asset.eventDetails?.maxAttendees || null,
                    postPurchaseInstructions: this.asset.details?.postPurchaseInstructions || ''
                };
            } else {
                // Ensure postPurchaseInstructions is populated if eventDetails exists but field is missing
                this.editableAsset.eventDetails.postPurchaseInstructions = this.asset.details?.postPurchaseInstructions || '';
            }
            // eventDetails.date/time carry the NEXT occurrence for a repeating event —
            // useful to display, but they must not be re-saved as a fixed date. The
            // schedule itself is edited through this hydrated recurrence object.
            this.editableAsset.eventDetails.recurrence =
                this._hydrateRecurrence(this.asset.eventDetails?.recurrence);
            if (this.editableAsset.eventDetails.recurrence.enabled) {
                this.editableAsset.eventDetails.date = '';
                this.editableAsset.eventDetails.time = '';
            }

            if (!this.editableAsset.details) {
                this.editableAsset.details = { welcomeContent: '', benefits: '', subscription_tiers: [], labels: { en: '', sw: '' } };
            }
            if (!this.editableAsset.details.labels) {
                this.editableAsset.details.labels = this.asset.details?.labels || { en: '', sw: '' };
            }

            // Initialize UZA Product ID
            if (!this.editableAsset.uza_product_id) {
                this.editableAsset.uza_product_id = this.asset.details?.uza_product_id || '';
            }

            // Initialize donation / flexible-amount ("pay-what-you-want") config.
            if (!this.editableAsset.donation) {
                const d = this.asset.details?.donation || {};
                this.editableAsset.donation = {
                    enabled: !!d.enabled,
                    min_amount: d.min_amount || 0,
                    mandatory: !!d.mandatory,
                    suggested_amounts: Array.isArray(d.suggested_amounts) ? d.suggested_amounts.slice() : [],
                    // Editor-only helper: comma-separated string for the presets input.
                    _suggestedRaw: Array.isArray(d.suggested_amounts) ? d.suggested_amounts.join(', ') : '',
                    cta: d.cta || CTA_FALLBACK.id,
                    cta_custom: { en: (d.cta_custom || {}).en || '', sw: (d.cta_custom || {}).sw || '' }
                };
            }

            // Initialize pricing tiers
            if (!this.editableAsset.details.subscription_tiers) {
                this.editableAsset.details.subscription_tiers = this.asset.details?.subscription_tiers || [];
            }

            // Initialize physical-product variations (each may carry a pending photo upload)
            if (!this.editableAsset.details.variations) {
                this.editableAsset.details.variations = (this.asset.details?.variations || []).map(v => ({ ...v }));
            }
            this.editableAsset.details.variations.forEach(v => { if (v._newPhoto === undefined) v._newPhoto = null; });

            // Initialize subscription content fields
            if (!this.editableAsset.details.welcomeContent) {
                this.editableAsset.details.welcomeContent = this.asset.details?.welcomeContent || '';
            }
            if (!this.editableAsset.details.benefits) {
                this.editableAsset.details.benefits = this.asset.details?.benefits || '';
            }

            // Initialize allow_download (default to true if not set)
            if (this.editableAsset.allow_download === undefined || this.editableAsset.allow_download === null) {
                this.editableAsset.allow_download = this.asset.allow_download !== false;
            }

            // Initialize custom fields (available for all asset types)
            if (!this.editableAsset.customFields) {
                this.editableAsset.customFields = this.asset.custom_fields || [];
            }
            // Ensure each field has an editable raw-options string for the dropdown builder
            this.editableAsset.customFields.forEach(f => {
                if (f._optionsRaw === undefined) {
                    f._optionsRaw = Array.isArray(f.options) ? f.options.join(', ') : '';
                }
                if (f.required === undefined) f.required = false;
                if (f.accept === undefined) f.accept = '';
                if (f.maxSizeMb === undefined) f.maxSizeMb = 5;
            });

            // Initialize questionnaire enforcement mode: 'optional' | 'reminder' | 'gate'
            if (!this.editableAsset.collect_info_mode) {
                this.editableAsset.collect_info_mode = this.asset.details?.collect_info_mode || 'optional';
            }

            // Initialize content items date/expiry from description
            if (this.editableAsset.files) {
                this.editableAsset.files.forEach((f, i) => {
                    f.newFile = null; // Initialize for UI binding
                    f._uid = f.id ? ('db-' + f.id) : ('uid-' + Date.now() + '-' + i);
                    // Parse [Date:YYYY-MM-DD] from description
                    const dateMatch = f.description ? f.description.match(/\[Date:(\d{4}-\d{2}-\d{2})\]\s*/) : null;
                    if (dateMatch) {
                        f.date = dateMatch[1];
                        f.description = f.description.replace(dateMatch[0], '');
                    }
                    // Parse [Expiry:YYYY-MM-DD] from description
                    const expiryMatch = f.description ? f.description.match(/\[Expiry:(\d{4}-\d{2}-\d{2})\]\s*/) : null;
                    if (expiryMatch) {
                        f.expiry = expiryMatch[1];
                        f.description = f.description.replace(expiryMatch[0], '');
                    }
                    if (!f.expiry) f.expiry = '';
                    if (!f.date) f.date = '';
                    // Initialize type if missing
                    if (!f.type) {
                        f.type = f.link && !f.link.startsWith('/content/') ? 'link' : 'upload';
                    }
                });
            }

            this.$nextTick(() => this._initMDEditors());
        },

        _initMDEditors() {
            this._mdEditors = [
                bindMarkdownEditor(
                    document.getElementById('description'), { minHeight: '110px' },
                    () => this.editableAsset.description,
                    v => { this.editableAsset.description = v; }
                ),
                bindMarkdownEditor(
                    document.getElementById('story'), { minHeight: '340px' },
                    () => this.editableAsset.story,
                    v => { this.editableAsset.story = v; }
                )
            ].filter(Boolean);

            // CodeMirror measures 0px while its tab is display:none, so an editor
            // mounted under a restored non-General tab renders blank until refreshed.
            this.$watch('activeTab', tab => {
                if (tab !== 'general') return;
                this.$nextTick(() => this._mdEditors.forEach(mde => mde.codemirror.refresh()));
            });
        },

        handleCoverSelect(event) {
            const file = event.target.files[0];
            if (file) {
                this.previewImage = URL.createObjectURL(file);
                this.editableAsset.newCoverImage = file;
            }
        },

        get publicUrl() {
            // Guard against a null asset object here as well.
            return `${window.location.origin}/${this.editableAsset.slug || this.asset.slug || ''}`;
        },

        linkCopied: false,
        async copyPublicUrl() {
            try {
                await navigator.clipboard.writeText(this.publicUrl);
            } catch (e) {
                // Clipboard API needs a secure context; fall back to a temp input.
                const tmp = document.createElement('input');
                tmp.value = this.publicUrl;
                document.body.appendChild(tmp);
                tmp.select();
                document.execCommand('copy');
                document.body.removeChild(tmp);
            }
            this.linkCopied = true;
            setTimeout(() => { this.linkCopied = false; }, 2000);
        },

        addContentItem(position = 'bottom') {
            if (!this.editableAsset.files) this.editableAsset.files = [];
            const blank = { _uid: 'new-' + Date.now() + '-' + Math.random(), title: '', link: '', description: '', newFile: null, type: 'upload', date: '', expiry: '' };
            if (position === 'top') {
                this.editableAsset.files.unshift(blank);
            } else {
                this.editableAsset.files.push(blank);
            }
            // Bring the newly added card into view on the next render tick.
            this.$nextTick(() => {
                const list = this.$refs.contentList;
                if (!list) return;
                const target = position === 'top' ? list.firstElementChild : list.lastElementChild;
                if (target && target.scrollIntoView) target.scrollIntoView({ behavior: 'smooth', block: 'center' });
            });
        },

        removeContentItem(index) {
            this.editableAsset.files.splice(index, 1);
        },

        // Initialize SortableJS for drag-and-drop reordering
        initSortable() {
            if (typeof Sortable === 'undefined') {
                console.warn('SortableJS not loaded, drag-and-drop disabled');
                return;
            }

            this.$nextTick(() => {
                const el = this.$refs.contentList;
                if (!el) return;

                new Sortable(el, {
                    animation: 150,
                    handle: '.drag-handle',
                    ghostClass: 'opacity-50',
                    chosenClass: 'ring-indigo-500',
                    dragClass: 'shadow-lg',
                    onEnd: (evt) => {
                        const oldIndex = evt.oldIndex;
                        const newIndex = evt.newIndex;
                        if (oldIndex !== newIndex && this.editableAsset.files) {
                            // Move item in array
                            const item = this.editableAsset.files.splice(oldIndex, 1)[0];
                            this.editableAsset.files.splice(newIndex, 0, item);
                        }
                    }
                });
            });
        },

        moveItemUp(index) {
            if (index <= 0 || !this.editableAsset.files) return;
            const files = this.editableAsset.files;
            [files[index - 1], files[index]] = [files[index], files[index - 1]];
        },

        moveItemDown(index) {
            if (!this.editableAsset.files || index >= this.editableAsset.files.length - 1) return;
            const files = this.editableAsset.files;
            [files[index], files[index + 1]] = [files[index + 1], files[index]];
        },

        addPricingTier() {
            this.editableAsset.details.subscription_tiers.push({ name: '', price: null, interval: 'monthly', description: '' });
        },

        removePricingTier(index) {
            this.editableAsset.details.subscription_tiers.splice(index, 1);
        },

        addVariation() {
            if (!this.editableAsset.details.variations) this.editableAsset.details.variations = [];
            this.editableAsset.details.variations.push({ id: newVariationId(), name: '', price: null, photo_url: null, sold_out: false, _newPhoto: null });
        },

        removeVariation(index) {
            this.editableAsset.details.variations.splice(index, 1);
        },

        handleVariationPhoto(variation, event) {
            const file = event.target.files[0];
            if (file) {
                variation._newPhoto = file;
                variation.photo_url = URL.createObjectURL(file);
            }
        },

        addCustomField() {
            if (!this.editableAsset.customFields) this.editableAsset.customFields = [];
            this.editableAsset.customFields.push({ type: 'text', question: '', required: false, options: [], _optionsRaw: '', accept: '', maxSizeMb: 5 });
        },

        removeCustomField(index) {
            this.editableAsset.customFields.splice(index, 1);
        },

        handleFileSelect(event, index) {
            const file = event.target.files[0];
            if (file) {
                // Ensure the object is reactive
                this.editableAsset.files[index].newFile = file;
                // Force Alpine to notice the change if needed (usually automatic)
            }
        },

        async saveChanges() {
            this.isSaving = true;
            this.hideNotification();

            if (!this.editableAsset || !this.asset.id) {
                this.showNotification('Error: Asset data is missing. Cannot save.', 'error');
                this.isSaving = false;
                return;
            }

            const formData = new FormData();

            // Construct the asset_data JSON structure expected by save_asset_from_form
            const contentItems = (this.editableAsset.files || []).map(f => {
                let desc = f.description || '';
                if (f.expiry) {
                    desc = `[Expiry:${f.expiry}] ${desc}`;
                }
                if (f.date) {
                    desc = `[Date:${f.date}] ${desc}`;
                }
                return {
                    title: f.title,
                    link: f.link,
                    description: desc,
                    type: f.type || 'upload'
                };
            });

            // Clean custom fields: derive dropdown options from the raw string and
            // drop the editor-only _optionsRaw helper before persisting.
            const cleanedCustomFields = (this.editableAsset.customFields || []).map(f => {
                const out = {
                    type: f.type || 'text',
                    question: f.question || '',
                    required: !!f.required
                };
                if (f.type === 'select') {
                    out.options = (f._optionsRaw || (Array.isArray(f.options) ? f.options.join(', ') : ''))
                        .split(',').map(s => s.trim()).filter(Boolean);
                }
                if (f.type === 'file') {
                    out.accept = f.accept || '';
                    out.maxSizeMb = f.maxSizeMb || 5;
                }
                return out;
            }).filter(f => f.question.trim());

            // Sanitize donation config (only meaningful for non-subscription assets).
            const donationSrc = this.editableAsset.donation || {};
            const donationEnabled = !!donationSrc.enabled && !this.asset.is_subscription;
            const donation = {
                enabled: donationEnabled,
                min_amount: parseFloat(donationSrc.min_amount) || 0,
                mandatory: !!donationSrc.mandatory,
                cta: donationSrc.cta || CTA_FALLBACK.id,
                cta_custom: {
                    en: (donationSrc.cta_custom?.en || '').trim(),
                    sw: (donationSrc.cta_custom?.sw || '').trim()
                },
                suggested_amounts: (donationSrc._suggestedRaw || '')
                    .split(',').map(s => parseFloat(s.trim())).filter(n => !isNaN(n) && n > 0)
            };
            // A donation asset is always free at base — the contribution is the charge.
            const effectivePrice = donationEnabled ? 0 : this.editableAsset.price;

            const assetData = {
                action: this.editableAsset.status === 'Draft' ? 'draft' : 'publish',
                // Send the exact status too — 'action' alone cannot express
                // Unlisted/Archived and the server would fall back to Published.
                status: this.editableAsset.status,
                asset: {
                    id: this.asset.id,
                    title: this.editableAsset.title,
                    description: this.editableAsset.description,
                    story_snippet: this.editableAsset.story,
                    uza_product_id: this.editableAsset.uza_product_id || '',
                    slug: this.editableAsset.slug || ''
                },
                allow_download: this.editableAsset.allow_download,
                assetTypeEnum: this.asset.asset_type,
                contentItems: contentItems,
                customFields: cleanedCustomFields,
                collect_info_mode: this.editableAsset.collect_info_mode || 'optional',
                eventDetails: { ...(this.editableAsset.eventDetails || {}), recurrence: this.buildRecurrencePayload() },
                subscriptionDetails: {
                    welcomeContent: this.editableAsset.details?.welcomeContent || '',
                    benefits: this.editableAsset.details?.benefits || '',
                    subscription_tiers: this.editableAsset.details?.subscription_tiers || []
                },
                newsletterDetails: {
                    welcomeContent: this.editableAsset.details?.welcomeContent || '',
                    benefits: this.editableAsset.details?.benefits || ''
                },
                labels: this.editableAsset.details?.labels || {},
                donation: donation,
                variations: (this.editableAsset.details?.variations || [])
                    .map(v => ({
                        id: v.id, name: (v.name || '').trim(),
                        price: (v.price === null || v.price === '') ? null : parseFloat(v.price),
                        photo_url: (v.photo_url && !v.photo_url.startsWith('blob:')) ? v.photo_url : null,
                        sold_out: !!v.sold_out
                    }))
                    .filter(v => v.name),
                pricing: {
                    // The billing model is fixed at creation; the server ignores this on
                    // updates. Sent only so the payload stays consistent with the asset.
                    amount: effectivePrice,
                    type: this.asset.is_subscription ? 'recurring' : 'one-time',
                    billingCycle: (this.asset.subscription_interval || 'monthly').toLowerCase(),
                    tiers: this.editableAsset.details?.subscription_tiers || []
                }
            };


            formData.append('asset_data', JSON.stringify(assetData));

            // Append Cover Image if changed
            if (this.editableAsset.newCoverImage) {
                formData.append('cover_image', this.editableAsset.newCoverImage);
            }

            // Append files
            (this.editableAsset.files || []).forEach((f, index) => {
                if (f.newFile) {
                    formData.append(`content_file_${index}`, f.newFile);
                }
            });

            // Append new/replacement variation photos
            (this.editableAsset.details?.variations || []).forEach(v => {
                if (v._newPhoto && v.id) {
                    formData.append(`variation_photo_${v.id}`, v._newPhoto);
                }
            });

            try {
                // Use the robust save_asset endpoint
                const response = await fetch('/admin/assets/save', {
                    method: 'POST',
                    headers: { 'Accept': 'application/json' },
                    body: formData
                });

                const result = await response.json();

                if (response.ok && result.success) {
                    this.showNotification(result.message, 'success');
                    // Reload to reflect changes (especially file links)
                    setTimeout(() => window.location.reload(), 1000);
                } else {
                    this.showNotification(result.message || 'An unknown error occurred.', 'error');
                }
            } catch (e) {
                console.error(e);
                this.showNotification('A server connection error occurred.', 'error');
            } finally {
                this.isSaving = false;
            }
        },

        showNotification(message, type = 'success') {
            this.notification.message = message;
            this.notification.type = type;
            this.notification.show = true;
            setTimeout(() => this.hideNotification(), 4000);
        },

        hideNotification() {
            this.notification.show = false;
        }
    })));

    Alpine.data('checkout', (asset, currencySymbol, paymentUrl) => ({
        isOpen: false,
        asset: asset,
        currency: currencySymbol,
        paymentUrl: paymentUrl,
        renewalTierName: null,
        autoOpenRenew: false,
        // Holds the national part only ("712 345 678") — the +255 lives in the UI.
        phoneNumber: NyotaPhone.display(localStorage.getItem('nyota_phone') || ''),
        status: 'ready',
        errorMessage: '',
        statusMessage: '',
        channelId: null,
        eventSource: null,
        selectedTier: null,
        tiers: [],
        contribution: '', // Donor-chosen amount for pay-what-you-want assets
        purchaseId: null,
        dealId: null,
        pollingInterval: null,
        pollCount: 0,
        maxPolls: 120, // 10 minutes at 5s interval
        modalTimeout: null, // Timeout for modal auto-refresh
        _trackPurchaseOnce: false, // Prevent duplicate purchase events from SSE+polling

        // --- Donation / flexible-amount ("pay-what-you-want") helpers ---
        get donationCfg() {
            const d = this.asset.details && this.asset.details.donation;
            return (d && d.enabled) ? d : null;
        },
        get isDonation() {
            // Donation never applies while a subscription tier is selected, nor to physical goods.
            return !!this.donationCfg && !this.selectedTier && !this.isPhysical;
        },
        get donationMin() {
            return this.donationCfg ? parseFloat(this.donationCfg.min_amount || 0) : 0;
        },
        get contributionAmount() {
            const n = parseFloat(this.contribution);
            return isNaN(n) || n < 0 ? 0 : n;
        },
        // Is this checkout a contribution rather than a purchase? True when the
        // asset requires one, or when the supporter has chosen to give on an
        // asset that only invites it. The wording of the whole modal hangs off
        // this: a required donation is priced 0 at the base, so `isFree` alone
        // would greet the supporter with "Get this, Free!" and then charge them.
        get isDonating() {
            return this.isDonation && (!!this.donationCfg?.mandatory || this.contributionAmount > 0);
        },
        // Quick-pick chips: unique, sorted, and never below the minimum — offering a
        // chip the server would reject is a dead end for the supporter.
        get suggestedAmounts() {
            const min = this.donationMin;
            const seen = new Set();
            return (this.donationCfg?.suggested_amounts || [])
                .map(a => parseFloat(a))
                .filter(n => !isNaN(n) && n > 0 && n >= min && !seen.has(n) && seen.add(n))
                .sort((a, b) => a - b)
                .slice(0, 6);
        },
        // Money as a supporter reads it: 12,000 — not 12,000.00. Cents only appear
        // when the amount actually has them.
        formatAmount(amount) {
            const n = parseFloat(amount) || 0;
            const decimals = Number.isInteger(n) ? 0 : 2;
            return new Intl.NumberFormat('en-US', { style: 'decimal', minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(n);
        },
        // Tapping a chip sets the amount; tapping the selected chip again clears it
        // (only when donating is optional — mandatory assets always need a value).
        pickAmount(amt) {
            const selected = this.contributionAmount === parseFloat(amt);
            this.contribution = (selected && !this.donationCfg?.mandatory) ? '' : String(amt);
        },
        // --- Physical products ---
        // The order itself (which option, how many) is chosen on the page and lives
        // in $store.order; the modal only reads it back and pays for it.
        get isPhysical() {
            return this.asset.asset_type === 'PHYSICAL';
        },
        get order() { return Alpine.store('order'); },
        get unitPrice() { return this.order.unitPrice; },
        formatCurrency(amount) {
            return new Intl.NumberFormat('en-US', { style: 'decimal', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount || 0);
        },
        // The amount actually being charged — used for the CTA label and analytics.
        get effectiveAmount() {
            if (this.isPhysical) return this.order.total;
            if (this.isDonation) return this.contributionAmount;
            if (this.selectedTier) return parseFloat(this.selectedTier.price || 0);
            return parseFloat(this.asset.price || 0);
        },

        get isFree() {
            // Donation assets are free unless the supporter chooses to contribute.
            if (this.isDonation) {
                return this.contributionAmount === 0;
            }
            if (this.isPhysical) {
                return this.unitPrice === 0;
            }
            // Check if this is a free asset (no tier selected or tier price is 0)
            if (this.selectedTier && this.selectedTier.price) {
                return parseFloat(this.selectedTier.price) === 0;
            }
            return parseFloat(this.asset.price || 0) === 0;
        },

        init() {
            // Renewal context — set by the server when a lapsed subscriber lands here.
            try {
                const rd = document.getElementById('renewal-data');
                if (rd && rd.textContent.trim()) {
                    const parsed = JSON.parse(rd.textContent);
                    if (parsed) {
                        this.renewalTierName = parsed.tier_name || null;
                        this.autoOpenRenew = !!parsed.auto_open;
                    }
                }
            } catch (e) { /* no renewal context */ }

            this.$watch('isOpen', value => {
                if (!value) {
                    this.clearModalTimeout();
                }
            });
            window.addEventListener('open-checkout-modal', (event) => {
                const prefillNumber = event.detail ? event.detail.phoneNumber : localStorage.getItem('nyota_phone');
                this.openModal(prefillNumber);
            });

            // Listen for cancellation event
            window.addEventListener('stop-payment-verification', () => {
                console.log('Stopping payment verification due to cancellation');
                this.stopPolling();
                if (this.eventSource) {
                    this.eventSource.close();
                    this.eventSource = null;
                }
                this.status = 'none';
                this.isOpen = false;
            });

            // Check for pending purchase immediately on init (handles page refresh)
            // This avoids race conditions with external events
            const pendingKey = `nyota_purchase_${this.asset.id}`;
            const pendingData = localStorage.getItem(pendingKey);

            if (pendingData) {
                try {
                    const pending = JSON.parse(pendingData);
                    if (pending.status && pending.status.name === 'PENDING' && pending.id) {
                        console.log('[Resumption] Found pending purchase in storage:', pending);
                        // Small delay to ensure Alpine is fully ready
                        setTimeout(() => {
                            this.resumePaymentCheck(pending.id, pending.deal_id, pending.channel_id);
                        }, 500);
                    }
                } catch (e) {
                    console.error('[Resumption] Error parsing pending purchase:', e);
                }
            }

            // --- VISIBILITY API HOOK ---
            // Fixes mobile dropped SSE connections by checking status instantly when browser returns to foreground
            document.addEventListener('visibilitychange', () => {
                if (document.visibilityState === 'visible' && this.status === 'waiting' && this.purchaseId) {
                    console.log('👀 [VISIBILITY] User returned to tab. Instantly verifying payment status...');
                    this.checkPaymentStatus();
                }
            });

            // Arrived here via "Renew Subscription" (?renew=1) — open checkout straight away.
            if (this.autoOpenRenew && !pendingData) {
                this.$nextTick(() => this.openModal());
            }
        },

        openModal(prefillNumber = null, autoRetry = false) {
            this.isOpen = true; this.status = 'ready';
            this.errorMessage = ''; this.statusMessage = '';
            this.phoneNumber = NyotaPhone.display(prefillNumber || localStorage.getItem('nyota_phone') || '');
            this.channelId = crypto.randomUUID();
            this._trackPurchaseOnce = false;

            // Analytics: begin_checkout. For goods the buyer has already chosen an
            // option and a quantity, so report the order being opened, not the base price.
            try {
                var qty = this.isPhysical ? this.order.quantity : 1;
                var unit = this.isPhysical ? this.order.unitPrice : parseFloat(this.asset.price || 0);
                var price = unit * qty;
                if (typeof window.nyotaTrack === 'function') {
                    window.nyotaTrack('begin_checkout',
                        { currency: currencySymbol, value: price, items: [{ item_id: String(this.asset.id), item_name: this.asset.title, item_category: this.asset.asset_type, price: unit, quantity: qty }] },
                        { event: 'InitiateCheckout', params: { content_ids: [String(this.asset.id)], content_type: 'product', value: price, currency: currencySymbol, num_items: qty } }
                    );
                }
            } catch (e) { }

            // Initialize tiers if available
            this.tiers = this.asset.details?.subscription_tiers || [];
            // On renewal, pre-select the plan the customer was previously on (by name);
            // otherwise default to the first tier.
            const priorTier = this.renewalTierName
                ? this.tiers.find(t => t.name === this.renewalTierName)
                : null;
            this.selectedTier = priorTier || (this.tiers.length > 0 ? this.tiers[0] : null);

            // Physical products have no tiers — the choice is the variation the buyer
            // already made on the page ($store.order), which the modal must not reset.
            if (this.isPhysical) {
                this.tiers = [];
                this.selectedTier = null;
            }

            // Donation assets: reset the amount. If a contribution is mandatory,
            // prefill with the minimum (or first suggested amount) so the CTA is valid.
            this.contribution = '';
            const dc = this.donationCfg;
            if (dc && dc.mandatory) {
                const preset = this.suggestedAmounts[0] || dc.min_amount || '';
                this.contribution = preset ? String(preset) : '';
            }

            this.$nextTick(() => { if (this.$refs.phoneInput) this.$refs.phoneInput.focus(); });

            if (autoRetry) {
                // If retrying, specific logic to avoid double-initiation or just immediate start
                this.retryPayment();
            }
        },

        startTimeoutTimer() {
            // DEPRECATED: We no longer arbitrarily reload the page after 15 seconds.
            // This interrupted users who were still entering their mobile money PIN.
            // Reliability is now handled by robust parallel polling and the visibility API.
            this.clearModalTimeout();
        },

        clearModalTimeout() {
            if (this.modalTimeout) {
                clearTimeout(this.modalTimeout);
                this.modalTimeout = null;
            }
        },

        dispatchStatus(status, data = {}) {
            window.dispatchEvent(new CustomEvent('payment-status-change', {
                detail: { status: status, ...data }
            }));
        },

        // Analytics: fire purchase event exactly once (SSE+polling may both detect success)
        _firePurchaseEvent() {
            if (this._trackPurchaseOnce) return;
            this._trackPurchaseOnce = true;
            try {
                var price = this.effectiveAmount;
                var qty = this.isPhysical ? this.order.quantity : 1;
                if (typeof window.nyotaTrack === 'function') {
                    window.nyotaTrack('purchase',
                        { transaction_id: String(this.purchaseId || ''), currency: currencySymbol, value: price, items: [{ item_id: String(this.asset.id), item_name: this.asset.title, item_category: this.asset.asset_type, price: this.isPhysical ? this.unitPrice : price, quantity: qty }] },
                        { event: 'Purchase', params: { content_ids: [String(this.asset.id)], content_type: 'product', content_name: this.asset.title, value: price, currency: currencySymbol } }
                    );
                }
            } catch (e) { }
        },

        closeModal() {
            this.isOpen = false;
            // CRITICAL: Do NOT stop polling or close SSE when modal closes
            // Payment verification must continue in the background
            // Only stop when payment actually succeeds or user explicitly cancels
            console.log('Modal closed, but payment verification continues in background');
        },

        // Re-formats whatever was typed or pasted into "712 345 678".
        formatPhoneNumber() {
            this.phoneNumber = NyotaPhone.display(this.phoneNumber);
        },

        // 0XXXXXXXXX — the one form we ever send to the server or store.
        get phoneCanonical() {
            return NyotaPhone.canonical(this.phoneNumber);
        },

        // +255 712 345 678 — for reading the number back to the buyer.
        get phoneDisplay() {
            return NyotaPhone.international(this.phoneNumber);
        },

        get isPhoneValid() {
            return NyotaPhone.isValid(this.phoneNumber);
        },

        async initiatePayment() {
            if (!this.isPhoneValid) {
                this.errorMessage = 'Please enter a valid phone number.';
                return;
            }

            // Donation validation (mirrored server-side): mandatory needs >= min;
            // optional allows 0 or >= min, but never a sub-minimum non-zero amount.
            if (this.isDonation) {
                const amt = this.contributionAmount;
                const min = this.donationMin;
                if (this.donationCfg.mandatory && amt < Math.max(min, 0.01)) {
                    this.errorMessage = min > 0
                        ? `Please contribute at least ${this.currency}${this.formatAmount(min)}.`
                        : `A contribution is required to continue.`;
                    return;
                }
                if (amt > 0 && amt < min) {
                    this.errorMessage = `The minimum contribution is ${this.currency}${this.formatAmount(min)}.`;
                    return;
                }
            }

            this.status = 'initiating';
            this.errorMessage = '';
            localStorage.setItem('nyota_phone', this.phoneCanonical);

            try {
                const response = await fetch(this.paymentUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        phone_number: this.phoneCanonical,
                        asset_id: this.asset.id,
                        channel_id: this.channelId,
                        tier: this.selectedTier,
                        contribution: this.isDonation ? this.contributionAmount : undefined,
                        variation_id: (this.isPhysical && this.order.selected) ? this.order.selected.id : undefined,
                        quantity: this.isPhysical ? this.order.quantity : undefined,
                        language: navigator.language || 'en'
                    })
                });

                const result = await response.json();

                if (response.ok && result.success) {
                    // --- FREE ASSET: instant success, no payment verification ---
                    if (result.is_free) {
                        this.status = 'success';
                        this.statusMessage = result.message || 'Access granted!';
                        this.dispatchStatus('COMPLETED');
                        localStorage.setItem('nyota_phone', this.phoneCanonical);

                        // Analytics: generate_lead (free asset acquisition)
                        try {
                            if (typeof window.nyotaTrack === 'function') {
                                window.nyotaTrack('generate_lead',
                                    { currency: currencySymbol, value: 0, items: [{ item_id: String(this.asset.id), item_name: this.asset.title, item_category: this.asset.asset_type, price: 0, quantity: 1 }] },
                                    { event: 'Lead', params: { content_ids: [String(this.asset.id)], content_type: 'product', content_name: this.asset.title, value: 0, currency: currencySymbol } }
                                );
                            }
                        } catch (e) { }

                        setTimeout(() => {
                            window.location.href = result.redirect_url || '/library';
                        }, 800);
                        return;
                    }

                    // Analytics: add_payment_info (phone submitted successfully)
                    try {
                        var payPrice = this.effectiveAmount;
                        if (typeof window.nyotaTrack === 'function') {
                            window.nyotaTrack('add_payment_info',
                                { currency: currencySymbol, value: payPrice, payment_type: 'mobile_money', items: [{ item_id: String(this.asset.id), item_name: this.asset.title, item_category: this.asset.asset_type, price: this.isPhysical ? this.unitPrice : payPrice, quantity: this.isPhysical ? this.order.quantity : 1 }] },
                                { event: 'AddPaymentInfo', params: { content_ids: [String(this.asset.id)], content_type: 'product', value: payPrice, currency: currencySymbol } }
                            );
                        }
                    } catch (e) { }

                    // --- PAID ASSET: wait for payment verification ---
                    this.status = 'waiting';
                    this.statusMessage = result.message || 'Check your phone...';
                    this.purchaseId = result.purchase_id;
                    this.dealId = result.deal_id;

                    const pendingPurchase = {
                        id: result.purchase_id,
                        deal_id: result.deal_id,
                        channel_id: this.channelId, // Store channel ID for reconnection
                        status: { name: 'PENDING' }
                    };
                    localStorage.setItem(`nyota_purchase_${this.asset.id}`, JSON.stringify(pendingPurchase));

                    this.dispatchStatus('PENDING', { phoneNumber: this.phoneNumber });

                    // Belt and suspenders: Listen via SSE, but also poll in parallel
                    this.listenForPaymentResult();
                    this.startPolling();
                    this.startTimeoutTimer(); // (Now deprecated/empty)
                } else {
                    this.status = 'failed';
                    this.errorMessage = result.message || 'Could not start payment.';
                }
            } catch (err) {
                this.status = 'failed';
                this.errorMessage = 'A network error occurred.';
            }
        },

        async retryPayment() {
            if (!this.dealId || !this.purchaseId) {
                // Fallback to full initiation if we lost state
                return this.initiatePayment();
            }

            this.status = 'initiating';
            this.errorMessage = '';
            this.stopPolling(); // Stop any existing polling
            this.pollCount = 0; // Reset counter

            try {
                const response = await fetch('/api/retry-payment', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        deal_id: this.dealId,
                        purchase_id: this.purchaseId,
                        phone_number: this.phoneCanonical
                    })
                });

                const result = await response.json();

                if (response.ok && result.success) {
                    this.status = 'waiting';
                    this.statusMessage = result.message || 'New request sent. Check your phone.';
                    this.dispatchStatus('PENDING', { phoneNumber: this.phoneNumber });
                    this.startTimeoutTimer(); // (Now deprecated/empty)

                    // Re-initiate robust checking
                    this.startPolling();

                    // Ensure listener is active (it might have been closed)
                    if (!this.eventSource || this.eventSource.readyState === EventSource.CLOSED) {
                        this.listenForPaymentResult();
                    }
                } else {
                    this.status = 'timeout'; // Go back to timeout state so they can try again
                    this.errorMessage = result.message || 'Retry failed.';
                }
            } catch (e) {
                this.status = 'timeout';
                this.errorMessage = 'Network error during retry.';
            }
        },

        async checkPaymentStatus() {
            if (!this.purchaseId) {
                console.warn('No purchase ID available for status check');
                return;
            }

            console.log(`[POLLING] Checking payment status for purchase #${this.purchaseId}... (${this.pollCount}/${this.maxPolls})`);

            this.pollCount++;
            if (this.pollCount > this.maxPolls) {
                console.warn('[POLLING] Max polling attempts reached. Stopping.');
                this.stopPolling();
                this.status = 'timeout';
                this.errorMessage = 'Payment verification timed out. Please check your phone or retry.';
                if (this.eventSource) this.eventSource.close();
                return;
            }

            try {
                const response = await fetch(`/api/payment-status/${this.purchaseId}`);
                const data = await response.json();

                if (response.ok && data.success) {
                    console.log(`[POLLING] Status received: ${data.status}`);

                    if (data.status === 'COMPLETED') {
                        console.log('[POLLING] ✅ PAYMENT CONFIRMED! Redirecting...');
                        this.status = 'success';
                        this.statusMessage = 'Payment confirmed!';
                        this.clearModalTimeout(); // Clear timeout on success
                        this.stopPolling();
                        if (this.eventSource) this.eventSource.close();

                        // Clear localStorage
                        localStorage.removeItem(`nyota_purchase_${this.asset.id}`);

                        // Analytics: purchase (via polling)
                        this._firePurchaseEvent();

                        // Redirect regardless of modal state
                        setTimeout(() => {
                            window.location.href = data.redirect_url || '/library';
                        }, 1500);
                    } else if (data.status === 'FAILED') {
                        console.log('[POLLING] ❌ Payment failed');
                        this.status = 'failed';
                        this.errorMessage = data.message || 'Payment failed.';
                        this.stopPolling();
                        if (this.eventSource) this.eventSource.close();

                        // Reopen modal to show error
                        if (!this.isOpen) {
                            this.isOpen = true;
                        }
                    }
                    // If PENDING, continue polling (no action needed)
                } else {
                    console.error('[POLLING] Status check failed:', data.message);
                }
            } catch (e) {
                console.error('[POLLING] Error checking payment status:', e);
            }
        },

        startPolling() {
            console.log('🔄 [POLLING] Starting robust background payment verification (every 5 seconds)');
            this.stopPolling(); // Clear any existing interval
            this.pollCount = 0; // Reset counter on fresh start

            // Check immediately, then every 5 seconds
            this.checkPaymentStatus();
            this.pollingInterval = setInterval(() => this.checkPaymentStatus(), 5000);
        },

        stopPolling() {
            if (this.pollingInterval) {
                console.log('⏸️ [POLLING] Stopping payment verification');
                clearInterval(this.pollingInterval);
                this.pollingInterval = null;
            }
        },

        resumePaymentCheck(purchaseId, dealId, channelId) {
            console.log('Resuming payment check after refresh:', { purchaseId, dealId, channelId });

            // Restore state
            this.purchaseId = purchaseId;
            this.dealId = dealId;
            this.phoneNumber = NyotaPhone.display(localStorage.getItem('nyota_phone') || '');
            this.status = 'waiting';
            this.statusMessage = 'Checking payment status...';
            // this.isOpen = true; // User requested NOT to open modal automatically on refresh

            // Background verification continues below...

            if (channelId) {
                // If we have a channel ID, try to reconnect SSE first
                console.log('Found existing channel ID, reconnecting SSE...');
                this.channelId = channelId;
                this.listenForPaymentResult();
            } else {
                // Fallback to polling if no channel ID (legacy support)
                console.log('No channel ID found, falling back to polling...');
                this.checkPaymentStatus();
                this.startPolling();
            }
        },

        listenForPaymentResult() {
            if (this.eventSource) this.eventSource.close();

            // CRITICAL: Always check current status via API when connecting/reconnecting
            // This handles cases where we missed the SSE event during network downtime or refresh
            this.checkPaymentStatus();

            const streamUrl = `/api/payment-stream/${this.channelId}`;
            console.log(`[SSE] Connecting to ${streamUrl}...`);
            this.eventSource = new EventSource(streamUrl);

            this.eventSource.onopen = () => {
                console.log('[SSE] Connection established.');
            };

            this.eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Message received:', data);

                if (data.status === 'SUCCESS') {
                    this.status = 'success';
                    this.statusMessage = data.message || 'Payment successful!';
                    this.dispatchStatus('COMPLETED');
                    this.stopPolling();
                    this.eventSource.close();

                    // Clear localStorage
                    localStorage.removeItem(`nyota_purchase_${this.asset.id}`);

                    // Analytics: purchase (via SSE)
                    this._firePurchaseEvent();

                    setTimeout(() => { window.location.href = data.redirect_url || '/library'; }, 1500);
                } else if (data.status === 'FAILED') {
                    this.status = 'failed';
                    this.errorMessage = data.message || 'Payment failed. Please try again.';
                    this.dispatchStatus('FAILED');
                    this.stopPolling();
                    this.eventSource.close();
                }
                // Note: We no longer send TIMEOUT events. The connection stays open indefinitely.
            };

            this.eventSource.onerror = (error) => {
                // Browser will auto-reconnect on error, but we log it.
                // If it's a fatal error (readyState === 2), we might need to intervene.
                console.warn('[SSE] Connection error/interruption:', this.eventSource.readyState);

                // If closed, try to reconnect after a delay if we're still waiting
                if (this.eventSource.readyState === EventSource.CLOSED && this.status === 'waiting') {
                    console.log('[SSE] Connection closed, attempting reconnect in 3s...');
                    setTimeout(() => this.listenForPaymentResult(), 3000);
                }
            };
        }
    }));

    // checkoutForm — standalone full-page checkout component (used by /checkout/<slug>)
    // Mirrors the modal `checkout` component but uses `state` instead of `status`
    // and derives paymentUrl from the parent element's data-payment-url attribute.
    Alpine.data('checkoutForm', (asset, channelId) => ({
        asset: asset,
        channelId: channelId,
        // National part only ("712 345 678") — the +255 lives in the UI.
        phoneNumber: NyotaPhone.display(localStorage.getItem('nyota_phone') || ''),
        state: 'ready',
        errorMessage: '',
        statusMessage: '',
        purchaseId: null,
        dealId: null,
        pollingInterval: null,
        pollCount: 0,
        maxPolls: 120,
        eventSource: null,
        selectedTier: null,
        contribution: '', // Donor-chosen amount for pay-what-you-want assets
        _trackPurchaseOnce: false,

        get paymentUrl() {
            return this.$el.dataset.paymentUrl || '/api/initiate-payment';
        },

        get donationCfg() {
            const d = this.asset.details && this.asset.details.donation;
            return (d && d.enabled) ? d : null;
        },
        get isDonation() {
            return !!this.donationCfg && !this.selectedTier;
        },
        get donationMin() {
            return this.donationCfg ? parseFloat(this.donationCfg.min_amount || 0) : 0;
        },
        get contributionAmount() {
            const n = parseFloat(this.contribution);
            return isNaN(n) || n < 0 ? 0 : n;
        },
        // Same rules as the modal: unique, sorted, never below the minimum.
        get suggestedAmounts() {
            const min = this.donationMin;
            const seen = new Set();
            return (this.donationCfg?.suggested_amounts || [])
                .map(a => parseFloat(a))
                .filter(n => !isNaN(n) && n > 0 && n >= min && !seen.has(n) && seen.add(n))
                .sort((a, b) => a - b)
                .slice(0, 6);
        },
        formatAmount(amount) {
            const n = parseFloat(amount) || 0;
            const decimals = Number.isInteger(n) ? 0 : 2;
            return new Intl.NumberFormat('en-US', { style: 'decimal', minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(n);
        },
        pickAmount(amt) {
            const selected = this.contributionAmount === parseFloat(amt);
            this.contribution = (selected && !this.donationCfg?.mandatory) ? '' : String(amt);
        },

        // --- Phone entry (fixed +255 prefix; buyer types the national part) ---
        formatPhoneNumber() {
            this.phoneNumber = NyotaPhone.display(this.phoneNumber);
        },
        get phoneCanonical() {
            return NyotaPhone.canonical(this.phoneNumber);
        },
        get phoneDisplay() {
            return NyotaPhone.international(this.phoneNumber);
        },
        get isPhoneValid() {
            return NyotaPhone.isValid(this.phoneNumber);
        },

        get totalPrice() {
            if (this.isDonation) {
                return this.contributionAmount;
            }
            if (this.selectedTier && this.selectedTier.price !== undefined) {
                return parseFloat(this.selectedTier.price) || 0;
            }
            return parseFloat(this.asset.price || 0);
        },

        init() {
            this.selectedTier = (this.asset.details?.subscription_tiers || [])[0] || null;
            const dc = this.donationCfg;
            if (dc && dc.mandatory) {
                const preset = this.suggestedAmounts[0] || dc.min_amount || '';
                this.contribution = preset ? String(preset) : '';
            }

            // Resume a pending payment if one was stored (e.g. page refresh)
            const pendingData = localStorage.getItem(`nyota_purchase_${this.asset.id}`);
            if (pendingData) {
                try {
                    const pending = JSON.parse(pendingData);
                    if (pending.status?.name === 'PENDING' && pending.id) {
                        setTimeout(() => this.resumePaymentCheck(pending.id, pending.deal_id, pending.channel_id), 500);
                    }
                } catch (e) { }
            }

            document.addEventListener('visibilitychange', () => {
                if (document.visibilityState === 'visible' && this.state === 'waiting' && this.purchaseId) {
                    this.checkPaymentStatus();
                }
            });
        },

        async submitPayment() {
            if (!this.isPhoneValid) {
                this.errorMessage = 'Please enter a valid phone number.';
                return;
            }
            if (this.isDonation) {
                const amt = this.contributionAmount;
                const min = this.donationMin;
                if (this.donationCfg.mandatory && amt < Math.max(min, 0.01)) {
                    this.errorMessage = min > 0 ? `Please contribute at least ${this.formatAmount(min)}.` : `A contribution is required to continue.`;
                    return;
                }
                if (amt > 0 && amt < min) {
                    this.errorMessage = `The minimum contribution is ${this.formatAmount(min)}.`;
                    return;
                }
            }
            this.state = 'waiting';
            this.statusMessage = 'Initiating payment...';
            this.errorMessage = '';
            localStorage.setItem('nyota_phone', this.phoneCanonical);

            try {
                const response = await fetch(this.paymentUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        phone_number: this.phoneCanonical,
                        asset_id: this.asset.id,
                        channel_id: this.channelId,
                        tier: this.selectedTier,
                        contribution: this.isDonation ? this.contributionAmount : undefined,
                        variation_id: (this.isPhysical && this.selectedVariation) ? this.selectedVariation.id : undefined,
                        quantity: this.isPhysical ? this.quantity : undefined,
                        language: navigator.language || 'en'
                    })
                });
                const result = await response.json();

                // --- Already owns this item ---
                if (result.already_owned) {
                    if (result.sms_sent) {
                        this.state = 'already_owned';
                        this.statusMessage = result.message;
                    } else {
                        // SMS throttled or not configured — show inline error + library link
                        this.state = 'ready';
                        this.errorMessage = result.message;
                    }
                    return;
                }

                if (response.ok && result.success) {
                    if (result.is_free) {
                        this.state = 'success';
                        this.statusMessage = result.message || 'Access granted!';
                        setTimeout(() => { window.location.href = result.redirect_url || '/library'; }, 800);
                        return;
                    }
                    this.state = 'waiting';
                    this.statusMessage = result.message || 'Check your phone to complete payment.';
                    this.purchaseId = result.purchase_id;
                    this.dealId = result.deal_id;
                    localStorage.setItem(`nyota_purchase_${this.asset.id}`, JSON.stringify({
                        id: result.purchase_id,
                        deal_id: result.deal_id,
                        channel_id: this.channelId,
                        status: { name: 'PENDING' }
                    }));
                    this.listenForPaymentResult();
                    this.startPolling();
                } else {
                    this.state = 'ready';
                    this.errorMessage = result.message || 'Could not start payment.';
                }
            } catch (err) {
                this.state = 'ready';
                this.errorMessage = 'A network error occurred. Please try again.';
            }
        },

        async resumePaymentCheck(purchaseId, dealId, storedChannelId) {
            this.purchaseId = purchaseId;
            this.dealId = dealId;
            if (storedChannelId) this.channelId = storedChannelId;
            this.state = 'waiting';
            this.statusMessage = 'Resuming payment check...';
            this.listenForPaymentResult();
            this.startPolling();
        },

        startPolling() {
            this.stopPolling();
            this.pollCount = 0;
            this.pollingInterval = setInterval(() => this.checkPaymentStatus(), 5000);
        },

        stopPolling() {
            if (this.pollingInterval) {
                clearInterval(this.pollingInterval);
                this.pollingInterval = null;
            }
        },

        async checkPaymentStatus() {
            if (!this.purchaseId) return;
            this.pollCount++;
            if (this.pollCount > this.maxPolls) {
                this.stopPolling();
                this.state = 'ready';
                this.errorMessage = 'Payment timed out. Please try again or contact support.';
                return;
            }
            try {
                const response = await fetch(`/api/payment-status/${this.purchaseId}`);
                if (!response.ok) return;
                const data = await response.json();
                if (data.status === 'COMPLETED') {
                    this._onSuccess(data);
                } else if (data.status === 'FAILED') {
                    this.state = 'ready';
                    this.errorMessage = data.message || 'Payment failed. Please try again.';
                    this.stopPolling();
                }
            } catch (e) { }
        },

        listenForPaymentResult() {
            if (this.eventSource) { this.eventSource.close(); }
            this.eventSource = new EventSource(`/api/payment-stream/${this.channelId}`);
            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.status === 'SUCCESS') this._onSuccess(data);
                    else if (data.status === 'FAILED') {
                        this.state = 'ready';
                        this.errorMessage = data.message || 'Payment failed.';
                        this.stopPolling();
                        this.eventSource.close();
                    }
                } catch (e) { }
            };
            this.eventSource.onerror = () => {
                if (this.eventSource?.readyState === EventSource.CLOSED && this.state === 'waiting') {
                    setTimeout(() => this.listenForPaymentResult(), 3000);
                }
            };
        },

        _onSuccess(data) {
            if (this._trackPurchaseOnce) return;
            this._trackPurchaseOnce = true;
            this.state = 'success';
            this.statusMessage = 'Payment confirmed!';
            this.stopPolling();
            if (this.eventSource) { this.eventSource.close(); }
            localStorage.removeItem(`nyota_purchase_${this.asset.id}`);
            setTimeout(() => { window.location.href = data.redirect_url || '/library'; }, 1500);
        }
    }));

    Alpine.data('adminSupporters', () => ({
        // --- Data ---
        supporters: [], // Start with a guaranteed empty array
        filteredSupporters: [],
        viewMode: 'list',
        searchTerm: '',
        typeFilter: 'all',
        sortBy: 'spent',
        sortAsc: false,
        selectedSupporters: [],
        bulkAction: '',

        init() {
            // --- THIS IS THE FIX ---
            // A much more robust way to initialize the data.
            const dataElement = document.getElementById('supporters-data');
            if (dataElement && dataElement.textContent.trim()) {
                try {
                    const parsedData = JSON.parse(dataElement.textContent);
                    // Ensure the parsed data is actually an array before assigning it
                    if (Array.isArray(parsedData)) {
                        this.supporters = parsedData;
                    } else {
                        console.error("Parsed supporters data is not an array:", parsedData);
                        this.supporters = []; // Fallback to empty array
                    }
                } catch (e) {
                    console.error('Error parsing supporters data:', e);
                    this.supporters = []; // Fallback to empty array on parsing error
                }
            } else {
                this.supporters = []; // Fallback if data element is missing or empty
            }

            this.applyFiltersAndSort();

            this.$watch(() => [this.searchTerm, this.typeFilter, this.sortBy], () => {
                this.applyFiltersAndSort();
            });
        },

        // --- Computed Properties & Logic ---
        applyFiltersAndSort() {
            let temp = [...this.supporters]; // This now works because `supporters` is an array

            if (this.searchTerm.trim()) {
                const s = this.searchTerm.toLowerCase();
                temp = temp.filter(supporter =>
                    supporter.name.toLowerCase().includes(s) ||
                    (supporter.email && supporter.email.toLowerCase().includes(s))
                );
            }

            if (this.typeFilter !== 'all') {
                temp = temp.filter(supporter => {
                    if (this.typeFilter === 'customer') return supporter.purchases > 0;
                    if (this.typeFilter === 'affiliate') return supporter.is_affiliate;
                    if (this.typeFilter === 'subscriber') return supporter.is_subscriber;
                    return true;
                });
            }

            temp.sort((a, b) => {
                let valA, valB;
                switch (this.sortBy) {
                    case 'name': valA = a.name.toLowerCase(); valB = b.name.toLowerCase(); break;
                    case 'recent': valA = new Date(a.join_date); valB = new Date(b.join_date); break;
                    case 'purchases': valA = a.purchases || 0; valB = b.purchases || 0; break;
                    default: valA = a.total_spent || 0; valB = b.total_spent || 0; break; // 'spent'
                }
                // Default to descending sort for money/dates
                if (valA < valB) return 1;
                if (valA > valB) return -1;
                return 0;
            });

            this.filteredSupporters = temp;
        },

        // --- Helper Functions for UI ---
        // These will now work correctly
        getTotalRevenue() {
            return this.supporters.reduce((sum, s) => sum + (s.total_spent || 0), 0);
        },
        getAffiliateCount() {
            return this.supporters.filter(s => s.is_affiliate).length;
        },
        getAverageLTV() {
            const customerCount = this.supporters.filter(s => s.purchases > 0).length;
            if (customerCount === 0) return 0;
            return this.getTotalRevenue() / customerCount;
        },
        formatDate(iso) {
            if (!iso) return 'N/A';
            return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
        },

        // --- UI State Helpers ---
        hasActiveFilters() { return this.searchTerm.trim() || this.typeFilter !== 'all'; },
        getActiveFilters() {
            let filters = [];
            if (this.searchTerm.trim()) filters.push({ key: 'searchTerm', label: `Search: "${this.searchTerm}"` });
            if (this.typeFilter !== 'all') filters.push({ key: 'typeFilter', label: `Type: ${this.typeFilter}` });
            return filters;
        },
        removeFilter(key) { this[key] = (key === 'searchTerm') ? '' : 'all'; },
        clearAllFilters() { this.searchTerm = ''; this.typeFilter = 'all'; },

        // --- Actions ---
        applyBulkAction() { alert(`Applying action "${this.bulkAction}" to ${this.selectedSupporters.length} supporters.`); },
        viewSupporter(id) { alert(`Viewing supporter ${id}`); },
        messageSupporter(id) { alert(`Messaging supporter ${id}`); },

        toggleSelectAll(event) {
            this.selectedSupporters = event.target.checked ? this.filteredSupporters.map(s => s.id) : [];
        },
    }));

    Alpine.data('assetPageController', () => ({
        purchase: null,
        phoneNumber: localStorage.getItem('nyota_phone') || '',

        // --- IMPROVED STATE MANAGEMENT ---
        isRetrying: false,
        isCancelling: false,
        feedbackMessage: '',
        isSuccess: false,

        init() {
            try {
                const dataElement = document.getElementById('purchase-data');
                if (dataElement && dataElement.textContent.trim()) {
                    this.purchase = JSON.parse(dataElement.textContent);
                    // Pre-fill phone number from the pending purchase if available
                    if (this.purchase && this.purchase.phone_number) {
                        this.phoneNumber = this.purchase.phone_number;
                    }
                }
            } catch (e) { this.purchase = null; }
        },

        get purchaseId() { return this.purchase ? this.purchase.id : null; },
        get dealId() { return this.purchase ? this.purchase.payment_gateway_ref : null; },
        get purchaseStatus() { return this.purchase ? (this.purchase.status ? this.purchase.status.name : null) : null; },

        // Computed property to disable buttons during any action
        get isProcessing() {
            return this.isRetrying || this.isCancelling;
        },

        handlePurchaseAction() {
            // If it's a failed or pending purchase, we retry.
            if (this.purchaseId && (this.purchaseStatus === 'FAILED' || this.purchaseStatus === 'PENDING')) {
                this.retryPayment();
            } else {
                // Otherwise, it's a new purchase; open the modal.
                this.$dispatch('open-checkout-modal');
            }
        },

        async retryPayment() {
            if (!this.purchaseId || !this.dealId) {
                this.feedbackMessage = 'Order data is missing. Please try a new purchase.';
                this.isSuccess = false;
                return;
            }
            if (!NyotaPhone.isValid(this.phoneNumber)) {
                this.feedbackMessage = 'Please enter a valid phone number.';
                this.isSuccess = false;
                return;
            }

            this.isRetrying = true;
            this.feedbackMessage = '';

            try {
                const response = await fetch('/api/retry-payment', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        phone_number: NyotaPhone.canonical(this.phoneNumber),
                        deal_id: this.dealId,
                        purchase_id: this.purchaseId
                    })
                });
                const result = await response.json();

                this.feedbackMessage = result.message;
                this.isSuccess = response.ok && result.success;

                if (this.isSuccess) {
                    localStorage.setItem('nyota_phone', NyotaPhone.canonical(this.phoneNumber));
                    // Give user time to read the success message
                    setTimeout(() => window.location.reload(), 2000);
                }
            } catch (err) {
                this.feedbackMessage = 'A network error occurred.';
                this.isSuccess = false;
            } finally {
                // Only stop processing if it wasn't a success, otherwise we wait for reload
                if (!this.isSuccess) {
                    setTimeout(() => {
                        this.isRetrying = false;
                        this.feedbackMessage = '';
                    }, 5000);
                }
            }
        },

        // --- NEW: Method to cancel a pending payment ---
        async cancelPayment() {
            if (!this.purchaseId) {
                this.feedbackMessage = 'Cannot cancel: Order ID is missing.';
                this.isSuccess = false;
                return;
            }

            if (!confirm('Are you sure you want to cancel this pending payment?')) {
                return;
            }

            this.isCancelling = true;
            this.feedbackMessage = '';

            try {
                // NOTE: You will need to create this backend endpoint.
                const response = await fetch('/api/cancel-payment', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ purchase_id: this.purchaseId })
                });

                const result = await response.json();
                this.feedbackMessage = result.message;
                this.isSuccess = response.ok && result.success;

                if (this.isSuccess) {
                    // On success, reload the page to show the purchase button again.
                    setTimeout(() => window.location.reload(), 2000);
                }

            } catch (err) {
                this.feedbackMessage = 'A network error occurred while cancelling.';
                this.isSuccess = false;
            } finally {
                if (!this.isSuccess) {
                    setTimeout(() => {
                        this.isCancelling = false;
                        this.feedbackMessage = '';
                    }, 5000);
                }
            }
        }
    }));

    Alpine.data('activityFeed', (hasQuestionnaire = false, assetId = null) => ({
        ...answerValueHelpers,
        allItems: [],
        hasQuestionnaire,
        assetId,
        filters: { activityType: 'all', paymentStatus: 'all', questFilled: 'all', dateFrom: '', dateTo: '' },
        pageSize: 25,
        currentPage: 1,
        showFilterPanel: false,

        init() {
            // Restore saved filters from localStorage
            if (assetId) {
                try {
                    const saved = localStorage.getItem(`activityFilters_${assetId}`);
                    if (saved) this.filters = { ...this.filters, ...JSON.parse(saved) };
                } catch {}
            }

            try {
                const el = document.getElementById('activity-feed-data');
                const parsed = el ? JSON.parse(el.textContent || '[]') : [];
                this.allItems = parsed.sort((a, b) => new Date(b.date) - new Date(a.date));
            } catch (e) {
                this.allItems = [];
                console.error('Error parsing activity feed data:', e);
            }

            // Persist filter changes and reset page
            this.$watch('filters', (val) => {
                this.currentPage = 1;
                if (assetId) {
                    try { localStorage.setItem(`activityFilters_${assetId}`, JSON.stringify(val)); } catch {}
                }
            }, { deep: true });
        },

        get hasActiveFilters() {
            return this.filters.activityType !== 'all'
                || this.filters.paymentStatus !== 'all'
                || this.filters.questFilled !== 'all'
                || !!this.filters.dateFrom
                || !!this.filters.dateTo;
        },

        get filteredItems() {
            return this.allItems.filter(item => {
                if (this.filters.activityType !== 'all' && item.activity_type !== this.filters.activityType) return false;
                if (this.filters.dateFrom) {
                    if (new Date(item.date) < new Date(this.filters.dateFrom)) return false;
                }
                if (this.filters.dateTo) {
                    if (new Date(item.date) > new Date(this.filters.dateTo + 'T23:59:59')) return false;
                }
                if (item.activity_type === 'purchase') {
                    if (this.filters.paymentStatus !== 'all' && item.payment_status !== this.filters.paymentStatus) return false;
                    if (this.filters.questFilled === 'filled' && !item.filled) return false;
                    if (this.filters.questFilled === 'pending' && item.filled) return false;
                }
                return true;
            });
        },

        get totalPages() {
            return Math.max(1, Math.ceil(this.filteredItems.length / this.pageSize));
        },

        get pagedItems() {
            const start = (this.currentPage - 1) * this.pageSize;
            return this.filteredItems.slice(start, start + this.pageSize);
        },

        get exportUrl() {
            const base = `/admin/assets/${this.assetId}/responses/export`;
            const p = new URLSearchParams();
            if (this.filters.activityType  !== 'all') p.set('activity_type',  this.filters.activityType);
            if (this.filters.paymentStatus !== 'all') p.set('payment_status', this.filters.paymentStatus);
            if (this.filters.questFilled   !== 'all') p.set('quest_filled',   this.filters.questFilled);
            if (this.filters.dateFrom) p.set('date_from', this.filters.dateFrom);
            if (this.filters.dateTo)   p.set('date_to',   this.filters.dateTo);
            return p.toString() ? `${base}?${p}` : base;
        },

        // Returns chips for each active filter so the bar can render them
        get activeFilterChips() {
            const chips = [];
            const typeLabels = { purchase: 'Purchases', comment: 'Comments' };
            const statusLabels = { COMPLETED: 'Completed', PENDING: 'Pending', FAILED: 'Failed' };
            const questLabels = { filled: 'Form filled', pending: 'Awaiting form' };
            if (this.filters.activityType !== 'all') chips.push({ key: 'activityType',  label: typeLabels[this.filters.activityType]  || this.filters.activityType });
            if (this.filters.paymentStatus !== 'all') chips.push({ key: 'paymentStatus', label: statusLabels[this.filters.paymentStatus] || this.filters.paymentStatus });
            if (this.filters.questFilled   !== 'all') chips.push({ key: 'questFilled',   label: questLabels[this.filters.questFilled]   || this.filters.questFilled });
            if (this.filters.dateFrom) chips.push({ key: 'dateFrom', label: `From ${this.filters.dateFrom}` });
            if (this.filters.dateTo)   chips.push({ key: 'dateTo',   label: `To ${this.filters.dateTo}` });
            return chips;
        },

        clearChip(key) {
            if (key === 'dateFrom' || key === 'dateTo') this.filters[key] = '';
            else this.filters[key] = 'all';
        },

        prevPage() { if (this.currentPage > 1) this.currentPage--; },
        nextPage() { if (this.currentPage < this.totalPages) this.currentPage++; },

        resetFilters() {
            this.filters = { activityType: 'all', paymentStatus: 'all', questFilled: 'all', dateFrom: '', dateTo: '' };
            this.currentPage = 1;
            if (assetId) {
                try { localStorage.removeItem(`activityFilters_${assetId}`); } catch {}
            }
        },

        formatDate(iso) {
            try {
                return new Date(iso).toLocaleString(undefined, {
                    month: 'short', day: 'numeric', year: 'numeric',
                    hour: '2-digit', minute: '2-digit'
                });
            } catch { return iso; }
        }
    }));

    // Supporter detail page: one customer's purchases + questionnaire answers
    // across all of the creator's products. Mirrors activityFeed but filters by
    // product instead of activity type, and exports per-supporter.
    Alpine.data('supporterActivity', (supporterId = null) => ({
        ...answerValueHelpers,
        allItems: [],
        products: [],
        supporterId,
        filters: { productId: 'all', paymentStatus: 'all', questFilled: 'all', dateFrom: '', dateTo: '' },
        pageSize: 25,
        currentPage: 1,
        showFilterPanel: false,

        init() {
            if (supporterId) {
                try {
                    const saved = localStorage.getItem(`supporterFilters_${supporterId}`);
                    if (saved) this.filters = { ...this.filters, ...JSON.parse(saved) };
                } catch {}
            }

            try {
                const el = document.getElementById('supporter-activity-data');
                const parsed = el ? JSON.parse(el.textContent || '[]') : [];
                this.allItems = parsed.sort((a, b) => new Date(b.date) - new Date(a.date));
            } catch (e) {
                this.allItems = [];
                console.error('Error parsing supporter activity data:', e);
            }

            try {
                const pel = document.getElementById('supporter-products-data');
                this.products = pel ? JSON.parse(pel.textContent || '[]') : [];
            } catch { this.products = []; }

            this.$watch('filters', (val) => {
                this.currentPage = 1;
                if (supporterId) {
                    try { localStorage.setItem(`supporterFilters_${supporterId}`, JSON.stringify(val)); } catch {}
                }
            }, { deep: true });
        },

        get hasActiveFilters() {
            return this.filters.productId !== 'all'
                || this.filters.paymentStatus !== 'all'
                || this.filters.questFilled !== 'all'
                || !!this.filters.dateFrom
                || !!this.filters.dateTo;
        },

        get filteredItems() {
            return this.allItems.filter(item => {
                if (this.filters.productId !== 'all' && String(item.asset_id) !== String(this.filters.productId)) return false;
                if (this.filters.paymentStatus !== 'all' && item.payment_status !== this.filters.paymentStatus) return false;
                if (this.filters.questFilled === 'filled' && !item.filled) return false;
                if (this.filters.questFilled === 'pending' && item.filled) return false;
                if (this.filters.dateFrom && new Date(item.date) < new Date(this.filters.dateFrom)) return false;
                if (this.filters.dateTo && new Date(item.date) > new Date(this.filters.dateTo + 'T23:59:59')) return false;
                return true;
            });
        },

        get totalPages() {
            return Math.max(1, Math.ceil(this.filteredItems.length / this.pageSize));
        },

        get pagedItems() {
            const start = (this.currentPage - 1) * this.pageSize;
            return this.filteredItems.slice(start, start + this.pageSize);
        },

        get exportUrl() {
            const base = `/admin/supporters/${this.supporterId}/responses/export`;
            const p = new URLSearchParams();
            if (this.filters.productId     !== 'all') p.set('asset_id',       this.filters.productId);
            if (this.filters.paymentStatus !== 'all') p.set('payment_status', this.filters.paymentStatus);
            if (this.filters.questFilled   !== 'all') p.set('quest_filled',   this.filters.questFilled);
            if (this.filters.dateFrom) p.set('date_from', this.filters.dateFrom);
            if (this.filters.dateTo)   p.set('date_to',   this.filters.dateTo);
            return p.toString() ? `${base}?${p}` : base;
        },

        get activeFilterChips() {
            const chips = [];
            const statusLabels = { COMPLETED: 'Completed', PENDING: 'Pending', FAILED: 'Failed' };
            const questLabels = { filled: 'Form filled', pending: 'Awaiting form' };
            if (this.filters.productId !== 'all') {
                const prod = this.products.find(p => String(p.id) === String(this.filters.productId));
                chips.push({ key: 'productId', label: prod ? prod.title : 'Product' });
            }
            if (this.filters.paymentStatus !== 'all') chips.push({ key: 'paymentStatus', label: statusLabels[this.filters.paymentStatus] || this.filters.paymentStatus });
            if (this.filters.questFilled   !== 'all') chips.push({ key: 'questFilled',   label: questLabels[this.filters.questFilled]   || this.filters.questFilled });
            if (this.filters.dateFrom) chips.push({ key: 'dateFrom', label: `From ${this.filters.dateFrom}` });
            if (this.filters.dateTo)   chips.push({ key: 'dateTo',   label: `To ${this.filters.dateTo}` });
            return chips;
        },

        clearChip(key) {
            if (key === 'dateFrom' || key === 'dateTo') this.filters[key] = '';
            else this.filters[key] = 'all';
        },

        prevPage() { if (this.currentPage > 1) this.currentPage--; },
        nextPage() { if (this.currentPage < this.totalPages) this.currentPage++; },

        resetFilters() {
            this.filters = { productId: 'all', paymentStatus: 'all', questFilled: 'all', dateFrom: '', dateTo: '' };
            this.currentPage = 1;
            if (supporterId) {
                try { localStorage.removeItem(`supporterFilters_${supporterId}`); } catch {}
            }
        },

        statusBadgeClass(status) {
            if (status === 'COMPLETED') return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300';
            if (status === 'PENDING')   return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300';
            return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300';
        },

        statusLabel(status) {
            return status ? status.charAt(0) + status.slice(1).toLowerCase() : '';
        },

        formatDate(iso) {
            try {
                return new Date(iso).toLocaleString(undefined, {
                    month: 'short', day: 'numeric', year: 'numeric',
                    hour: '2-digit', minute: '2-digit'
                });
            } catch { return iso; }
        }
    }));

});