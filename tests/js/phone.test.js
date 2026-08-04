// Checks NyotaPhone — the helper that drives the +255 phone field — against the
// same input shapes the Python normalizer is tested with. Run via
// `node tests/js/phone.test.js` (test_phone_js.py drives it under pytest).

const path = require('path');
const fs = require('fs');

// main.js registers Alpine components on DOMContentLoaded; requiring it in Node
// only needs the module.exports at the top of the file, so stub the two globals
// its top-level code touches.
global.window = undefined;
global.document = { addEventListener() {} };

const source = fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'main.js'), 'utf8');
const module_ = { exports: {} };
new Function('module', 'document', source)(module_, global.document);
const { NyotaPhone } = module_.exports;

let failures = 0;

function check(label, actual, expected) {
    const ok = actual === expected;
    if (!ok) {
        failures++;
        console.error(`  FAIL ${label}\n       expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
    return ok;
}

// --- Every shape a buyer might type or paste collapses to the same 9 digits ---
const NATIONAL = '712345678';
[
    '712345678',
    '0712345678',
    '255712345678',
    '+255712345678',
    '00255712345678',
    '+255 712 345 678',
    '0712 345 678',
    '0712-345-678',
    '0712.345.678',
    '+255 (0) 712 345 678',
    '  0712345678  ',
    '+255712345678999',        // over-long paste is trimmed to 9 digits
].forEach(raw => check(`national(${JSON.stringify(raw)})`, NyotaPhone.national(raw), NATIONAL));

// --- Typing digit by digit never fights the buyer ---
check('typing "0"', NyotaPhone.national('0'), '');
check('typing "07"', NyotaPhone.national('07'), '7');
check('typing "071"', NyotaPhone.national('071'), '71');
// A bare "255" is left alone until it can only be a country code.
check('typing "2"', NyotaPhone.national('2'), '2');
check('typing "255"', NyotaPhone.national('255'), '255');
check('typing "2557"', NyotaPhone.national('2557'), '7');

// --- Display formatting ---
check('display grouping', NyotaPhone.display('0712345678'), '712 345 678');
check('display partial (4)', NyotaPhone.display('0712'), '712');
check('display partial (5)', NyotaPhone.display('07123'), '712 3');
check('display partial (7)', NyotaPhone.display('0712345'), '712 345');
check('display empty', NyotaPhone.display(''), '');
check('display null', NyotaPhone.display(null), '');

// --- What we submit: the canonical local form the server and DB use ---
check('canonical from national', NyotaPhone.canonical('712 345 678'), '0712345678');
check('canonical from international', NyotaPhone.canonical('+255 712 345 678'), '0712345678');
check('canonical empty', NyotaPhone.canonical(''), '');

// --- Read-back ---
check('international', NyotaPhone.international('0712345678'), '+255 712 345 678');
check('international empty', NyotaPhone.international(''), '');

// --- Validity gates the submit button ---
[
    ['712345678', true],
    ['0712345678', true],
    ['+255 712 345 678', true],
    ['612345678', true],       // 06 range
    ['812345678', false],      // not a TZ mobile prefix
    ['71234567', false],       // too short
    ['', false],
].forEach(([raw, expected]) => check(`isValid(${JSON.stringify(raw)})`, NyotaPhone.isValid(raw), expected));

if (failures) {
    console.error(`\n${failures} NyotaPhone assertion(s) failed`);
    process.exit(1);
}
console.log('NyotaPhone: all assertions passed');
