// Ai-Lens service worker: lets the site install as an app and open offline.
//
// Network first for everything, so news is always fresh when online; the last
// copy of each page, script and data file is kept for offline use. Each deploy
// stamps a new VERSION (python/build_static.py), which clears the old cache.
const VERSION = 'dev';
const CACHE = `ai-lens-${VERSION}`;
const SHELL = ['./', 'index.html', 'news.html', 'invest.html', 'reflections.html', 'favicon.svg'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);
  // Same-site GETs only; audio streams with range requests and is too large to keep.
  if (req.method !== 'GET' || url.origin !== location.origin || req.headers.has('range')
      || url.pathname.endsWith('.m4a')) return;
  event.respondWith(fetch(req).then((res) => {
    if (res.ok && res.type === 'basic') {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy));
    }
    return res;
  }).catch(() => caches.match(req, { ignoreSearch: req.mode === 'navigate' })
    // Offline and never visited: open the cached timeline instead of an error page.
    .then((hit) => hit || (req.mode === 'navigate' ? caches.match('index.html') : Response.error()))));
});
