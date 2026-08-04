// Exercises the checkout components from static/js/main.js: the donation amount
// logic (quick picks, minimums, what the CTA claims) and the phone field, for both
// the modal on the asset page and the standalone /checkout page.

const assert = require('assert');
const { loadMain } = require('./load_main');

const { registry, stores } = loadMain();

let failures = 0;
function test(name, fn) {
    try {
        fn();
    } catch (err) {
        failures++;
        console.error(`  FAIL ${name}\n       ${err.message}`);
    }
}

function donationAsset(donation, extra = {}) {
    return Object.assign({
        id: 1,
        title: 'Support the work',
        asset_type: 'DIGITAL_PRODUCT',
        price: 0,
        details: { donation },
    }, extra);
}

// A component instance without Alpine's reactivity: the getters and methods under
// test are plain functions over plain state.
function modal(asset) {
    return registry.checkout(asset, 'TZS', '/api/initiate-payment');
}

function page(asset) {
    return registry.checkoutForm(asset, 'channel-1');
}

const BOTH = [['modal', modal], ['page', page]];

// The order the buyer builds on the product page. Seeds the shared store the way
// its init() would from #asset-data, so the modal reads a real choice.
function order(asset) {
    const s = stores.order;
    s.isPhysical = asset.asset_type === 'PHYSICAL';
    s.basePrice = parseFloat(asset.price || 0);
    s.variations = (asset.details && asset.details.variations) || [];
    s.selected = s.variations.find(v => !v.sold_out) || null;
    s.quantity = 1;
    return s;
}

// ---------------------------------------------------------------------------
// Quick-pick amounts
// ---------------------------------------------------------------------------

BOTH.forEach(([label, build]) => {
    test(`${label}: suggested amounts are offered in order`, () => {
        const c = build(donationAsset({
            enabled: true, min_amount: 0, suggested_amounts: [48000, 12000, 24000],
        }));
        assert.deepStrictEqual(c.suggestedAmounts, [12000, 24000, 48000]);
    });

    test(`${label}: amounts below the minimum are never offered`, () => {
        // Offering a chip the server rejects is a dead end for the supporter.
        const c = build(donationAsset({
            enabled: true, min_amount: 6000, suggested_amounts: [1000, 5000, 12000, 24000],
        }));
        assert.deepStrictEqual(c.suggestedAmounts, [12000, 24000]);
    });

    test(`${label}: duplicate and unusable amounts are dropped`, () => {
        const c = build(donationAsset({
            enabled: true, min_amount: 0,
            suggested_amounts: [12000, 12000, 0, -5, 'abc', null, 24000],
        }));
        assert.deepStrictEqual(c.suggestedAmounts, [12000, 24000]);
    });

    test(`${label}: no suggestions configured is not an error`, () => {
        const c = build(donationAsset({ enabled: true, min_amount: 6000 }));
        assert.deepStrictEqual(c.suggestedAmounts, []);
        assert.strictEqual(c.isDonation, true);
    });

    test(`${label}: at most six chips are shown`, () => {
        const c = build(donationAsset({
            enabled: true, min_amount: 0,
            suggested_amounts: [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000],
        }));
        assert.strictEqual(c.suggestedAmounts.length, 6);
    });
});

// ---------------------------------------------------------------------------
// Picking, clearing and typing an amount
// ---------------------------------------------------------------------------

BOTH.forEach(([label, build]) => {
    test(`${label}: tapping a chip fills the amount`, () => {
        const c = build(donationAsset({ enabled: true, min_amount: 0, suggested_amounts: [12000] }));
        c.pickAmount(12000);
        assert.strictEqual(c.contribution, '12000');
        assert.strictEqual(c.contributionAmount, 12000);
    });

    test(`${label}: tapping the selected chip again clears it when optional`, () => {
        const c = build(donationAsset({
            enabled: true, min_amount: 0, mandatory: false, suggested_amounts: [12000],
        }));
        c.pickAmount(12000);
        c.pickAmount(12000);
        assert.strictEqual(c.contribution, '');
        assert.strictEqual(c.contributionAmount, 0);
    });

    test(`${label}: a mandatory donation cannot be cleared by tapping twice`, () => {
        const c = build(donationAsset({
            enabled: true, min_amount: 6000, mandatory: true, suggested_amounts: [12000],
        }));
        c.pickAmount(12000);
        c.pickAmount(12000);
        assert.strictEqual(c.contributionAmount, 12000);
    });

    test(`${label}: a typed amount overrides the chip`, () => {
        const c = build(donationAsset({ enabled: true, min_amount: 0, suggested_amounts: [12000] }));
        c.pickAmount(12000);
        c.contribution = '15500';
        assert.strictEqual(c.contributionAmount, 15500);
    });

    test(`${label}: nonsense in the amount field reads as zero, never negative`, () => {
        const c = build(donationAsset({ enabled: true, min_amount: 0 }));
        c.contribution = 'abc';
        assert.strictEqual(c.contributionAmount, 0);
        c.contribution = '-500';
        assert.strictEqual(c.contributionAmount, 0);
    });
});

// ---------------------------------------------------------------------------
// What the buyer is told they'll pay
// ---------------------------------------------------------------------------

BOTH.forEach(([label, build]) => {
    test(`${label}: whole amounts drop the cents`, () => {
        const c = build(donationAsset({ enabled: true, min_amount: 0 }));
        assert.strictEqual(c.formatAmount(12000), '12,000');
        assert.strictEqual(c.formatAmount('24000'), '24,000');
        assert.strictEqual(c.formatAmount(0), '0');
    });

    test(`${label}: cents are shown when there are any`, () => {
        const c = build(donationAsset({ enabled: true, min_amount: 0 }));
        assert.strictEqual(c.formatAmount(12000.5), '12,000.50');
    });
});

test('modal: the charged amount follows the contribution', () => {
    const c = modal(donationAsset({ enabled: true, min_amount: 6000, suggested_amounts: [12000] }));
    assert.strictEqual(c.effectiveAmount, 0);
    assert.strictEqual(c.isFree, true, 'no contribution yet — the CTA offers to continue free');
    c.pickAmount(12000);
    assert.strictEqual(c.effectiveAmount, 12000);
    assert.strictEqual(c.isFree, false);
});

test('page: the charged amount follows the contribution', () => {
    const c = page(donationAsset({ enabled: true, min_amount: 6000, suggested_amounts: [12000] }));
    assert.strictEqual(c.totalPrice, 0);
    c.pickAmount(12000);
    assert.strictEqual(c.totalPrice, 12000);
});

test('modal: a stale price on a donation asset is never charged', () => {
    // Donation assets are free at base; only the contribution is billed.
    const c = modal(donationAsset({ enabled: true, min_amount: 0 }, { price: 50000 }));
    assert.strictEqual(c.effectiveAmount, 0);
    c.contribution = '7000';
    assert.strictEqual(c.effectiveAmount, 7000);
});

test('modal: donation pricing yields to a selected subscription tier', () => {
    const c = modal(donationAsset({ enabled: true, min_amount: 6000 }));
    c.selectedTier = { name: 'Monthly', price: '5000' };
    assert.strictEqual(c.isDonation, false);
    assert.strictEqual(c.effectiveAmount, 5000);
});

test('modal: physical products are never treated as donations', () => {
    const asset = donationAsset({ enabled: true, min_amount: 6000 }, {
        asset_type: 'PHYSICAL', price: 20000,
    });
    order(asset);
    const c = modal(asset);
    assert.strictEqual(c.isDonation, false);
    assert.strictEqual(c.effectiveAmount, 20000);
});

// ---------------------------------------------------------------------------
// Physical goods: the order built on the product page
// ---------------------------------------------------------------------------

function goods(variations, price = 20000) {
    return { id: 7, title: 'Kanga', asset_type: 'PHYSICAL', price, details: { variations } };
}

test('order: the first available option is pre-selected', () => {
    const s = order(goods([
        { id: 'a', name: 'Red', sold_out: true },
        { id: 'b', name: 'Green' },
    ]));
    assert.strictEqual(s.selected.id, 'b', 'a sold-out option is never the default');
    assert.strictEqual(s.soldOut, false);
});

test('order: everything sold out leaves nothing selected', () => {
    const s = order(goods([{ id: 'a', name: 'Red', sold_out: true }]));
    assert.strictEqual(s.selected, null);
    assert.strictEqual(s.soldOut, true);
});

test('order: a sold-out option cannot be picked', () => {
    const s = order(goods([{ id: 'a', name: 'Red' }, { id: 'b', name: 'Green', sold_out: true }]));
    s.pick(s.variations[1]);
    assert.strictEqual(s.selected.id, 'a');
});

test('order: an option without its own price is sold at the base price', () => {
    const s = order(goods([{ id: 'a', name: 'Red' }, { id: 'b', name: 'Green', price: 25000 }]));
    assert.strictEqual(s.unitPrice, 20000);
    s.pick(s.variations[1]);
    assert.strictEqual(s.unitPrice, 25000);
});

test('order: the total is the chosen option times the quantity', () => {
    const s = order(goods([{ id: 'a', name: 'Red', price: 2000 }]));
    s.inc();
    s.inc();
    assert.strictEqual(s.quantity, 3);
    assert.strictEqual(s.total, 6000);
    s.dec();
    assert.strictEqual(s.total, 4000);
});

test('order: the quantity never drops below one or runs away', () => {
    const s = order(goods([{ id: 'a', name: 'Red', price: 2000 }]));
    s.dec();
    assert.strictEqual(s.quantity, 1);
    for (let i = 0; i < 200; i++) s.inc();
    assert.strictEqual(s.quantity, 100);
});

test('order: per-option prices are only surfaced when they differ', () => {
    // Repeating one identical number on every card is noise a first-time buyer
    // has to read past.
    const same = order(goods([{ id: 'a', name: 'Red' }, { id: 'b', name: 'Green', price: 20000 }]));
    assert.strictEqual(same.pricesVary, false);
    const differ = order(goods([{ id: 'a', name: 'Red' }, { id: 'b', name: 'Green', price: 25000 }]));
    assert.strictEqual(differ.pricesVary, true);
    // A price the buyer can never pay is not a difference worth showing.
    const gone = order(goods([
        { id: 'a', name: 'Red' },
        { id: 'b', name: 'Green' },
        { id: 'c', name: 'Blue', price: 35000, sold_out: true },
    ]));
    assert.strictEqual(gone.pricesVary, false);
});

test('modal: the amount charged is the order made on the page', () => {
    const asset = goods([{ id: 'a', name: 'Red' }, { id: 'b', name: 'Green', price: 25000 }]);
    const s = order(asset);
    const c = modal(asset);
    s.pick(s.variations[1]);
    s.inc();
    assert.strictEqual(c.unitPrice, 25000);
    assert.strictEqual(c.effectiveAmount, 50000);
    assert.strictEqual(c.isFree, false);
});

test('modal: opening checkout keeps the choice already made', () => {
    // The modal used to reset the variation and quantity on open, quietly
    // discarding what the buyer picked beside the photos.
    const asset = goods([{ id: 'a', name: 'Red' }, { id: 'b', name: 'Green', price: 25000 }]);
    const s = order(asset);
    s.pick(s.variations[1]);
    s.inc();
    const c = modal(asset);
    c.$watch = () => { };
    c.$nextTick = () => { };
    c.openModal();
    assert.strictEqual(s.selected.id, 'b');
    assert.strictEqual(s.quantity, 2);
    assert.strictEqual(c.effectiveAmount, 50000);
});

test('modal: a disabled donation config is inert', () => {
    const c = modal(donationAsset({ enabled: false, min_amount: 6000 }, { price: 10000 }));
    assert.strictEqual(c.isDonation, false);
    assert.strictEqual(c.effectiveAmount, 10000);
});

// ---------------------------------------------------------------------------
// The phone field
// ---------------------------------------------------------------------------

BOTH.forEach(([label, build]) => {
    test(`${label}: whatever is typed is reduced to the national digits`, () => {
        const c = build(donationAsset({ enabled: true, min_amount: 0 }));
        ['0712345678', '+255712345678', '255 712 345 678', '712345678'].forEach(raw => {
            c.phoneNumber = raw;
            c.formatPhoneNumber();
            assert.strictEqual(c.phoneNumber, '712 345 678', `from ${raw}`);
            assert.strictEqual(c.phoneCanonical, '0712345678');
        });
    });

    test(`${label}: an incomplete number keeps the submit button shut`, () => {
        const c = build(donationAsset({ enabled: true, min_amount: 0 }));
        c.phoneNumber = '712 345';
        assert.strictEqual(c.isPhoneValid, false);
        c.phoneNumber = '712 345 678';
        assert.strictEqual(c.isPhoneValid, true);
    });

    test(`${label}: the number is read back in full international form`, () => {
        const c = build(donationAsset({ enabled: true, min_amount: 0 }));
        c.phoneNumber = '0712345678';
        assert.strictEqual(c.phoneDisplay, '+255 712 345 678');
    });
});

if (failures) {
    console.error(`\n${failures} checkout assertion(s) failed`);
    process.exit(1);
}
console.log('checkout components: all assertions passed');
