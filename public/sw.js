// Offline support. The app shell is cached on install. The Transformers.js
// bundle and ONNX Runtime files from the CDN are cached the first time they
// load. Model weights are cached by Transformers.js itself (Cache API).
const SHELL = "grasscheck-shell-v3";
const RUNTIME = "grasscheck-runtime-v2";
const FILES = ["./", "index.html", "style.css", "app.js", "core.js", "labels.json", "manifest.webmanifest", "icon.svg"];
// Loaded on the very first visit, before this worker controls the page, so
// fetch them up front. The ONNX weights are cached by Transformers.js.
const MODEL = "https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/";
const REMOTE = [
  "https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.3.1/dist/transformers.min.js",
  MODEL + "preprocessor_config.json",
  MODEL + "config.json",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    Promise.all([
      caches.open(SHELL).then((c) => c.addAll(FILES)),
      caches.open(RUNTIME).then((c) => c.addAll(REMOTE)).catch(() => {}),
    ]).then(() => self.skipWaiting())
  );
});
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => ![SHELL, RUNTIME].includes(k)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  if (url.origin === location.origin) {
    // Network first for our own files so updates land, cache when offline.
    e.respondWith(
      fetch(e.request)
        .then((r) => { const copy = r.clone(); caches.open(SHELL).then((c) => c.put(e.request, copy)); return r; })
        .catch(() => caches.match(e.request, { ignoreSearch: true }))
    );
  } else if (url.hostname === "cdn.jsdelivr.net" || (url.hostname === "huggingface.co" && url.pathname.endsWith(".json"))) {
    e.respondWith(
      caches.match(e.request).then((hit) => hit || fetch(e.request).then((r) => {
        const copy = r.clone();
        caches.open(RUNTIME).then((c) => c.put(e.request, copy));
        return r;
      }))
    );
  }
});
