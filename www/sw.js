/* Service worker - cache local do app.
   App shell + bioengine ficam em cache. As bibliotecas do Pyodide são
   cacheadas sob demanda; na versão APK esses arquivos já vêm embutidos. */
const CACHE = "bioestat-v5-clean-ui";
const SHELL = [
  "./", "./index.html", "./styles.css?v=bioestat-clean-2", "./app.js?v=bioestat-clean-2", "./exemplos.js",
  "./manifest.webmanifest",
  "./calc/calda.html", "./calc/campo.html",
  "./lib/xlsx.full.min.js", "./lib/jspdf.umd.min.js",
  "./bioengine/__init__.py", "./bioengine/detect.py", "./bioengine/diagnostics.py",
  "./bioengine/doseresponse.py", "./bioengine/posthoc.py", "./bioengine/anova.py",
  "./bioengine/glmcount.py", "./bioengine/decide.py", "./bioengine/tempo.py",
  "./icons/icon-192.png", "./icons/icon-512.png"
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const path = new URL(req.url).pathname;
  const interfaceFresh = req.mode === "navigate" ||
    /\/(index\.html|app\.js|styles\.css|exemplos\.js|manifest\.webmanifest|sw\.js)$/.test(path);
  if (interfaceFresh) {
    e.respondWith(
      fetch(req).then(resp => {
        if (resp && resp.status === 200) {
          const copia = resp.clone();
          caches.open(CACHE).then(c => c.put(req, copia));
        }
        return resp;
      }).catch(() => caches.match(req))
    );
    return;
  }
  // estratégia: cache-first com atualização em segundo plano (stale-while-revalidate)
  e.respondWith(
    caches.match(req).then(cached => {
      const rede = fetch(req).then(resp => {
        if (resp && resp.status === 200 && (req.url.startsWith(self.location.origin) || req.url.includes("pyodide") || req.url.includes("jsdelivr"))) {
          const copia = resp.clone();
          caches.open(CACHE).then(c => c.put(req, copia));
        }
        return resp;
      }).catch(() => cached);
      return cached || rede;
    })
  );
});
