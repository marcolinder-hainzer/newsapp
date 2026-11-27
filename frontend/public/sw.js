// Minimaler Service Worker: App-Hülle offline verfügbar, Daten immer frisch aus dem Netz.
// Funktioniert unter "/" (eigener Server) ebenso wie unter "/<repo>/" (GitHub Pages).
const CACHE = "weitblick-v4";
const BASE = new URL("./", self.location).pathname;
const SHELL = [BASE, `${BASE}manifest.webmanifest`, `${BASE}icon.svg`];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys
      // Alte App-Caches löschen – gespeicherte Stimmen (weitblick-voices-*) bleiben erhalten
      .filter((k) => k !== CACHE && !k.startsWith("weitblick-voices"))
      .map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith(`${BASE}api/`) || url.pathname.startsWith(`${BASE}data/`)) return; // Daten immer live
  if (url.pathname.startsWith(`${BASE}vendor/`) || url.pathname.endsWith("piper-worker.js")) return; // Sprachausgabe
  if (url.pathname.startsWith(`${BASE}assets/`)) {
    event.respondWith(
      caches.match(event.request).then((hit) => hit || fetch(event.request).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(event.request, copy));
        return res;
      }))
    );
    return;
  }
  if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request).catch(() => caches.match(BASE)));
  }
});
