/* static/js/sw.js - Minimal Service Worker for Nyota PWA */

const CACHE_NAME = 'nyota-static-v1';

self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
    // Simple pass-through for now to satisfy PWA requirements
    event.respondWith(fetch(event.request));
});
