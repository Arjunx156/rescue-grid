/* Rescue Grid service worker: the field app keeps working on a weak or absent signal.
   - pages under /field: network first, last good copy when offline
   - build assets: cache first (they are content-hashed)
   - map tiles: stale-while-revalidate, capped
   - the current assignment: network first with the cached answer as fallback
   - push: show the assignment and open it on tap */

const VERSION = "rg-v1";
const PAGES = `${VERSION}-pages`;
const ASSETS = `${VERSION}-assets`;
const TILES = `${VERSION}-tiles`;
const DATA = `${VERSION}-data`;
const MAX_TILES = 600;

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(PAGES).then((c) => c.addAll(["/field"]).catch(() => undefined)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) return cached;
    throw err;
  }
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) cache.put(request, response.clone());
  return response;
}

async function trim(cacheName, max) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  for (const key of keys.slice(0, Math.max(0, keys.length - max))) await cache.delete(key);
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const fresh = fetch(request)
    .then((response) => {
      if (response.ok) {
        cache.put(request, response.clone());
        trim(cacheName, MAX_TILES);
      }
      return response;
    })
    .catch(() => cached);
  return cached || fresh;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  if (url.hostname === "tiles.openfreemap.org") {
    event.respondWith(staleWhileRevalidate(request, TILES));
    return;
  }
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/_next/static/") || url.pathname === "/maplibre-gl-worker.mjs") {
    event.respondWith(cacheFirst(request, ASSETS));
    return;
  }
  if (url.pathname === "/api/v1/field/assignments/current" || url.pathname.startsWith("/api/v1/field/assignments/")) {
    event.respondWith(networkFirst(request, DATA));
    return;
  }
  if (request.mode === "navigate" && url.pathname.startsWith("/field")) {
    event.respondWith(networkFirst(request, PAGES).catch(() => caches.match("/field")));
  }
});

self.addEventListener("push", (event) => {
  let data = { title: "Rescue Grid", body: "New update", url: "/field" };
  try {
    data = { ...data, ...event.data.json() };
  } catch {
    /* plain text or empty push */
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      tag: "assignment",
      renotify: true,
      requireInteraction: true,
      vibrate: [200, 100, 200],
      data: { url: data.url },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = event.notification.data?.url || "/field";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const w of windows) {
        if (new URL(w.url).pathname.startsWith("/field")) {
          w.navigate(target);
          return w.focus();
        }
      }
      return self.clients.openWindow(target);
    }),
  );
});
