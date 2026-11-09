// Background script: looks up the code database and the preferences, and sends a shared code only after the user agreed to share it.
const api = globalThis.browser ?? globalThis.chrome;

// The published database, the same files for every user: index.json (the date and the counts) and N shard files, each holding the
// stores whose domain hashes to it. A refresh downloads every shard, so no request names the site being visited; a lookup reads
// one shard (about 1 MB) from the browser's storage, or from the bundled copy before the first refresh.
const DB_URL = "https://bryceaspringfield.github.io/open-coupons/data/";
// Where an agreed share goes (a POST of {store, code}). Empty until a receiving endpoint is approved; shares wait in a local queue.
const SHARE_ENDPOINT = "";
const REFRESH_MS = 24 * 3600 * 1000;
const DEFAULT_PREFS = { autoOffer: true, shareAsk: true };

let meta = null;      // {generated, stores, codes, shards, fetched}
let refreshing = false;
const bundled = (name) => fetch(api.runtime.getURL("data/" + name)).then((r) => r.json());

// FNV-1a (32 bits) of the domain's UTF-8 bytes, modulo the shard count; build_db.py computes the same.
function shardOf(domain, n) {
  let h = 0x811c9dc5;
  for (const b of new TextEncoder().encode(domain)) h = Math.imul(h ^ b, 0x01000193) >>> 0;
  return h % n;
}

async function loadMeta() {
  if (!meta) {
    const got = await api.storage.local.get(["meta"]);
    meta = got.meta || { ...(await bundled("index.json")), fetched: 0 };
    api.storage.local.remove("db");  // the single-file database of versions before 0.3.0
  }
  if (DB_URL && !refreshing && Date.now() - (meta.fetched || 0) > REFRESH_MS) refreshDb();
  return meta;
}

async function lookup(store) {
  const m = await loadMeta();
  const key = "shard" + shardOf(store, m.shards);
  // A stored shard belongs to the refreshed database only when its shard count matches the index in use.
  const got = m.fetched ? await api.storage.local.get([key]) : {};
  const part = got[key] || await bundled(`shards/${shardOf(store, m.shards)}.json`);
  return { codes: part.domains[store] || [], selectors: (part.selectors || {})[store] || null, generated: m.generated };
}

async function refreshDb() {
  refreshing = true;
  try {
    const get = async (name) => { const r = await fetch(DB_URL + name, { credentials: "omit", cache: "no-cache" }); if (!r.ok) throw new Error(name); return r.json(); };
    const fresh = await get("index.json");
    if (!fresh.shards) return;
    if (fresh.generated !== meta.generated || !meta.fetched) {
      const todo = [...Array(fresh.shards).keys()];
      // Four downloads at once; each shard is stored as it arrives, so memory holds a few shards at a time.
      await Promise.all([0, 1, 2, 3].map(async () => {
        for (let i = todo.pop(); i !== undefined; i = todo.pop()) {
          const part = await get(`shards/${i}.json`);
          if (!part.domains) throw new Error("shard " + i);
          await api.storage.local.set({ ["shard" + i]: part });
        }
      }));
    }
    meta = { ...fresh, fetched: Date.now() };
    await api.storage.local.set({ meta });
  } catch (_) { /* offline or a partial download: keep the copy in use and try again at the next lookup */ }
  finally { refreshing = false; }
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
      case "codes": return lookup(String(msg.store));
      case "prefs": return prefs();
      case "setPrefs": { const p = { ...(await prefs()), ...msg.prefs }; await api.storage.local.set({ prefs: p }); return p; }
      case "share": return share(String(msg.store).slice(0, 253), String(msg.code).slice(0, 64));
      case "status": {
        const d = await loadMeta();
        const q = (await api.storage.local.get(["shareQueue"])).shareQueue || [];
        return { generated: d.generated, stores: d.stores, queued: q.length };
      }
      default: return null;
    }
  })().then(sendResponse);
  return true;  // the response is sent asynchronously
});
