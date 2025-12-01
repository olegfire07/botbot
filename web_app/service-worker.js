// Service Worker for offline support
const VERSION = '2322';
const CACHE_NAME = `sklad-bot-${VERSION}`;
const swPath = self.location.pathname.replace(/service-worker\.js.*$/, '');
const BASE_PATH = swPath.endsWith('/') ? swPath : `${swPath}/`;
const urlsToCache = [
    BASE_PATH,
    `${BASE_PATH}index.html`
];

// Install event - cache resources
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(urlsToCache))
    );
    self.skipWaiting();
});

// Activate event - clean old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    return self.clients.claim();
});

// Fetch event - serve from cache, fallback to network
self.addEventListener('fetch', (event) => {
    event.respondWith(
        caches.match(event.request)
            .then((response) => {
                if (response) {
                    return response;
                }
                return fetch(event.request);
            })
    );
});

// Background sync for offline submissions
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-reports') {
        event.waitUntil(syncPendingReports());
    }
});

async function syncPendingReports() {
    const db = await openDB();
    const tx = db.transaction('pending', 'readonly');
    const store = tx.objectStore('pending');
    const pending = await store.getAll();

    for (const item of pending) {
        try {
            await sendReport(item.data);
            // Remove from pending after successful send
            const deleteTx = db.transaction('pending', 'readwrite');
            await deleteTx.objectStore('pending').delete(item.id);
        } catch (error) {
            console.error('Failed to sync report:', error);
        }
    }
}

async function sendReport(data) {
    const response = await fetch('/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });

    if (!response.ok) {
        throw new Error('Failed to send report');
    }

    return response.json();
}

function openDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open('ReportsDB', 1);

        request.onerror = () => reject(request.error);
        request.onsuccess = () => resolve(request.result);

        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            if (!db.objectStoreNames.contains('pending')) {
                db.createObjectStore('pending', { keyPath: 'id', autoIncrement: true });
            }
        };
    });
}
