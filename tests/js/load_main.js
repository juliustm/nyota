// Loads static/js/main.js in Node and hands back the Alpine component factories.
//
// main.js registers its components inside an 'alpine:init' listener, so we stand in
// a minimal document/Alpine/localStorage and collect the registry. This keeps the
// tests honest: they exercise the components that actually ship, not a copy.

const fs = require('fs');
const path = require('path');

function loadMain() {
    const registry = {};
    const stores = {};
    const store = {};

    const fakeDocument = {
        listeners: {},
        addEventListener(name, cb) {
            (this.listeners[name] = this.listeners[name] || []).push(cb);
        },
        getElementById() { return null; },
    };

    global.localStorage = {
        getItem: key => (key in store ? store[key] : null),
        setItem: (key, value) => { store[key] = String(value); },
        removeItem: key => { delete store[key]; },
    };
    // Alpine calls a store's init() on registration and hands the same object back
    // to every reader — components under test reach shared state through Alpine.store().
    global.Alpine = {
        data(name, factory) { registry[name] = factory; },
        store(name, value) {
            if (value === undefined) return stores[name];
            stores[name] = value;
            if (typeof value.init === 'function') value.init();
            return value;
        },
    };
    global.window = { addEventListener() {} };
    global.document = fakeDocument;

    const source = fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'main.js'), 'utf8');
    const module_ = { exports: {} };
    new Function('module', 'document', 'window', 'localStorage', 'Alpine', source)(
        module_, fakeDocument, global.window, global.localStorage, global.Alpine
    );

    (fakeDocument.listeners['alpine:init'] || []).forEach(cb => cb());

    return { registry, stores, store, NyotaPhone: module_.exports.NyotaPhone };
}

module.exports = { loadMain };
