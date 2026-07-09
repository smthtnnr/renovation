/* Reno Budget Estimator — offline service worker.
   CACHE name carries a build id that the deploy workflow replaces with the
   commit SHA, so every release gets a fresh cache and old ones are purged.
   (Locally the placeholder stays constant, which is fine for dev.) */
const CACHE = "reno-budget-__BUILD_ID__";
const ASSETS = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./vendor/pdf-lib.min.js",
  "./vendor/fonts/mulish-400.woff2",
  "./vendor/fonts/mulish-600.woff2",
  "./vendor/fonts/mulish-700.woff2",
  "./vendor/fonts/mulish-800.woff2",
  "./assets/wedgewood-logo-white.png",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon-512-maskable.png",
  "./icons/apple-touch-icon.png"
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;

  // HTML / navigations: network-first so an online load always shows the
  // latest app, falling back to cache (then index.html) when offline.
  if (req.mode === "navigate" || (req.headers.get("accept") || "").includes("text/html")) {
    e.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put("./index.html", copy));
          return res;
        })
        .catch(() => caches.match(req).then((hit) => hit || caches.match("./index.html")))
    );
    return;
  }

  // Everything else (pdf-lib, icons, manifest): cache-first, with a runtime
  // update so new assets are picked up; the per-release cache name handles busting.
  e.respondWith(
    caches.match(req).then((hit) =>
      hit ||
      fetch(req).then((res) => {
        try {
          if (res && res.ok && new URL(req.url).origin === self.location.origin) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
          }
        } catch (_) {}
        return res;
      })
    )
  );
});
