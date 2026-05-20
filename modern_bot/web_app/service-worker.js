// Service Worker for offline support
const VERSION = '2400';
const CACHE_NAME = `sklad-bot-${VERSION}`;
const swPath = self.location.pathname.replace(/service-worker\.js.*$/, '');
const BASE_PATH = swPath.endsWith('/') ? swPath : `${swPath}/`;

const urlsToCache = [
    BASE_PATH,
    `${BASE_PATH}index.html`,
    `${BASE_PATH}styles.css`,
    `${BASE_PATH}app.js`,
    `${BASE_PATH}quiz_questions.json`,
    `${BASE_PATH}fianit-logo.jpg`
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

// Fetch event - Network First for API, Cache First for static assets
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // API requests: Network First
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(event.request)
                .catch(() => caches.match(event.request))
        );
        return;
    }

    // Static assets: Cache First, then Network
    event.respondWith(
        caches.match(event.request)
            .then((response) => {
                if (response) {
                    // Update cache in background
                    fetch(event.request).then(networkResponse => {
                        if (networkResponse && networkResponse.ok) {
                            caches.open(CACHE_NAME).then(cache => {
                                cache.put(event.request, networkResponse);
                            });
                        }
                    }).catch(() => { });
                    return response;
                }
                return fetch(event.request).then(networkResponse => {
                    // Cache successful responses
                    if (networkResponse && networkResponse.ok) {
                        const cloned = networkResponse.clone();
                        caches.open(CACHE_NAME).then(cache => {
                            cache.put(event.request, cloned);
                        });
                    }
                    return networkResponse;
                });
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
    const pending = await getAllFromStore(store);

    for (const item of pending) {
        try {
            await sendReport(item.data);
            // Remove from pending after successful send
            const deleteTx = db.transaction('pending', 'readwrite');
            deleteTx.objectStore('pending').delete(item.id);

            // Notify all clients
            const clients = await self.clients.matchAll();
            clients.forEach(client => {
                client.postMessage({
                    type: 'SYNC_COMPLETE',
                    id: item.id,
                    timestamp: Date.now()
                });
            });
        } catch (error) {
            console.error('Failed to sync report:', error);
        }
    }
}

async function sendReport(data) {
    const response = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });

    if (!response.ok) {
        throw new Error('Failed to send report');
    }

    return response;
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

function getAllFromStore(store) {
    return new Promise((resolve, reject) => {
        const request = store.getAll();
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

// Listen for messages from main app
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});
