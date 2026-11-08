// Background script: holds the code database and the preferences, and sends a shared code only after the user agreed to share it.
// The whole database is downloaded at once and looked up in the browser, so no request names the site being visited.
const api = globalThis.browser ?? globalThis.chrome;

// The published database (one JSON file, the same for every user). Empty until the code site is public; the bundled copy serves until then.
const DB_URL = "";
// Where an agreed share goes (a POST of {store, code}). Empty until a receiving endpoint is approved; shares wait in a local queue.
const SHARE_ENDPOINT = "";
const REFRESH_MS = 24 * 3600 * 1000;
const DEFAULT_PREFS = { autoOffer: true, shareAsk: true };

let db = null;  // {generated, domains: {store: [{c, d, s}]}}

async function loadDb() {
  if (db) return db;
  const got = await api.storage.local.get(["db"]);
  if (got.db) { db = got.db; }
  else {
    const r = await fetch(api.runtime.getURL("data/codes.json"));
    db = await r.json();
    db.fetched = 0;
    await api.storage.local.set({ db });
  }
  if (DB_URL && Date.now() - (db.fetched || 0) > REFRESH_MS) refreshDb();
  return db;
}

async function refreshDb() {
  try {
    const r = await fetch(DB_URL, { credentials: "omit", cache: "no-cache" });
    if (!r.ok) return;
    const fresh = await r.json();
    if (!fresh.domains) return;
    fresh.fetched = Date.now();
    db = fresh;
    await api.storage.local.set({ db });
  } catch (_) { /* offline: keep the stored copy */ }
}

async function prefs() {
  const got = await api.storage.local.get(["prefs"]);
  return { ...DEFAULT_PREFS, ...(got.prefs || {}) };
}

async function share(store, code) {
  const got = await api.storage.local.get(["shareQueue"]);
  const queue = got.shareQueue || [];
  if (!queue.some((x) => x.store === store && x.code === code)) queue.push({ store, code });
  let sent = false;
  if (SHARE_ENDPOINT) {
    const keep = [];
    for (const item of queue) {
      try {
        const r = await fetch(SHARE_ENDPOINT, { method: "POST", credentials: "omit", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ store: item.store, code: item.code }) });
        if (r.ok) { if (item.store === store && item.code === code) sent = true; } else keep.push(item);
      } catch (_) { keep.push(item); }
    }
    queue.length = 0; queue.push(...keep);
  }
  await api.storage.local.set({ shareQueue: queue });
  return { sent, queued: queue.length };
}

api.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    switch (msg && msg.action) {
      case "codes": { const d = await loadDb(); return { codes: d.domains[msg.store] || [], selectors: (d.selectors || {})[msg.store] || null, generated: d.generated }; }
      case "prefs": return prefs();
      case "setPrefs": { const p = { ...(await prefs()), ...msg.prefs }; await api.storage.local.set({ prefs: p }); return p; }
      case "share": return share(String(msg.store).slice(0, 253), String(msg.code).slice(0, 64));
      case "status": {
        const d = await loadDb();
        const q = (await api.storage.local.get(["shareQueue"])).shareQueue || [];
        return { generated: d.generated, stores: Object.keys(d.domains).length, queued: q.length };
      }
      default: return null;
    }
  })().then(sendResponse);
  return true;  // the response is sent asynchronously
});
