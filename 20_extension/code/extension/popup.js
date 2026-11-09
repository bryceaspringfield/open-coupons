const api = globalThis.browser ?? globalThis.chrome;

async function main() {
  const [tab] = await api.tabs.query({ active: true, currentWindow: true });
  let store = null;
  try { store = tab && tab.url && /^https?:/.test(tab.url) ? globalThis.OC_DOMAINS.storeKey(new URL(tab.url).hostname) : null; } catch (_) { store = null; }

  const summary = document.getElementById("summary"), table = document.getElementById("codes"), tryBtn = document.getElementById("try");
  if (store) {
    document.getElementById("title").textContent = store;
    const res = await api.runtime.sendMessage({ action: "codes", store });
    const codes = (res && res.codes) || [];
    summary.textContent = codes.length ? `${codes.length} known code${codes.length === 1 ? "" : "s"}` : "No known codes for this site.";
    for (const k of codes) {
      const tr = table.insertRow();
      const c = tr.insertCell(); c.className = "code"; c.textContent = k.c;
      const d = tr.insertCell(); d.className = "d"; d.textContent = k.d || "";
      const b = tr.insertCell(); const btn = document.createElement("button"); btn.textContent = "Copy";
      btn.addEventListener("click", async () => { await navigator.clipboard.writeText(k.c); btn.textContent = "Copied"; });
      b.appendChild(btn);
    }
    if (codes.length) {
      tryBtn.hidden = false;
      tryBtn.addEventListener("click", async () => { await api.tabs.sendMessage(tab.id, { action: "tryNow" }); window.close(); });
    }
  } else {
    summary.textContent = "Open a store's page to see its codes.";
  }

  priceErrors(store);

  const prefs = await api.runtime.sendMessage({ action: "prefs" });
  for (const key of ["autoOffer", "shareAsk"]) {
    const box = document.getElementById(key);
    box.checked = prefs[key] !== false;
    box.addEventListener("change", () => api.runtime.sendMessage({ action: "setPrefs", prefs: { [key]: box.checked } }));
  }
  const st = await api.runtime.sendMessage({ action: "status" });
  document.getElementById("status").textContent =
    `Database of ${st.generated || "unknown date"}: ${st.stores} stores.` + (st.queued ? ` ${st.queued} shared code(s) waiting to send.` : "");
}

// Price errors (merged from the price-error-finder project, 2026-11-09): the public list the cluster builds each hour, with each
// deal's check on the store's own page. The request is the same file whatever page is open, so it tells the site nothing about the tab.
const ERRORS_URL = "https://bryceaspringfield.github.io/price-error-finder/items.json";
const ALL_URL = "https://bryceaspringfield.github.io/price-error-finder/";

async function priceErrors(store) {
  const sum = document.getElementById("errSummary"), table = document.getElementById("errors");
  let data;
  try {
    const r = await fetch(ERRORS_URL, { cache: "no-cache", credentials: "omit" });
    data = await r.json();
  } catch (_) {
    sum.textContent = "The price error list did not load.";
    return;
  }
  const items = data.items || [];
  const live = items.filter(i => i.v === "active");
  if (!store) {
    sum.textContent = `${live.length} deals the cluster found still live on the store's page, of ${items.length} posted in the last ${data.days} days.`;
    return;
  }
  const label = store.split(".")[0];
  const here = items.filter(i => {
    let h = "";
    try { h = globalThis.OC_DOMAINS.storeKey(new URL(i.vu || i.u).hostname) || ""; } catch (_) { h = ""; }
    return (h === store || i.s === label) && i.v !== "gone";
  }).sort((a, b) => (b.v === "active") - (a.v === "active") || (b.d || 0) - (a.d || 0));
  sum.textContent = here.length ? `${here.length} at ${store}; the first ${Math.min(here.length, 8)} below.` : `None posted for ${store} in the last ${data.days} days.`;
  const usd = x => x == null ? "" : "$" + x.toLocaleString("en-US", { minimumFractionDigits: x % 1 ? 2 : 0, maximumFractionDigits: 2 });
  for (const i of here.slice(0, 8)) {
    const tr = table.insertRow();
    const p = tr.insertCell(); p.className = "pr"; p.textContent = usd(i.vp != null ? i.vp : i.pr);
    const t = tr.insertCell(); t.className = "d";
    const a = document.createElement("a"); a.href = i.vu || i.u; a.target = "_blank"; a.rel = "noopener"; a.textContent = i.t.slice(0, 90);
    t.appendChild(a);
    t.appendChild(document.createTextNode(i.v === "active" ? " (live when checked)" : i.v === "changed" ? " (price changed)" : " (not checked)"));
  }
  document.getElementById("errAll").href = ALL_URL + "#" + encodeURIComponent(JSON.stringify({ seller: label, cats: data.categories, age: 14 }));
}

main();
