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

main();
