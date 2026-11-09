// Content script: finds a coupon field, offers to try the known codes, keeps the code giving the lowest total, and
// offers to share a code the user typed which worked and is missing from the database. It sends nothing on its own.
(() => {
  if (window.__openCouponsLoaded) return;
  window.__openCouponsLoaded = true;

  const api = globalThis.browser ?? globalThis.chrome;
  const P = globalThis.OC_PLATFORMS;
  const store = globalThis.OC_DOMAINS.storeKey(location.hostname);
  const RUN_KEY = "__open_coupons_run";
  const MAX_CODES = 40;
  const SETTLE_QUIET_MS = 700, SETTLE_MAX_MS = 7000, SETTLE_MIN_MS = 400;
  const CHECKOUT_URL_RX = /cart|checkout|basket|\bbag\b|order|payment|billing|purchase|subscribe|plans?\b|pricing/i;
  const ERROR_RX = /invalid|not valid|isn.t valid|expired|not applicable|doesn.t exist|does not exist|cannot be applied|can.t be applied|not eligible|unable to apply|minimum|not recognized|ungültig|no válido|non valide/i;

  let known = [];          // [{c: code, d: description, s: [sources]}]
  let storeSel = null;     // {input, apply, total} from the database, when it has selectors for this store
  let running = false;
  let ui = null;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const send = (msg) => api.runtime.sendMessage(msg).catch(() => null);

  // ---------- page interaction ----------

  // Sets a field's value through the native setter, since React and Vue track the value there and ignore a plain assignment.
  function setValue(input, value) {
    input.focus();
    const proto = Object.getPrototypeOf(input);
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set || Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    setter.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function submit(loc) {
    if (loc.apply && P.visible(loc.apply)) {
      loc.apply.disabled = false;
      loc.apply.click();
      return;
    }
    const opts = { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true };
    loc.input.dispatchEvent(new KeyboardEvent("keydown", opts));
    loc.input.dispatchEvent(new KeyboardEvent("keyup", opts));
    if (loc.input.form && typeof loc.input.form.requestSubmit === "function") loc.input.form.requestSubmit();
  }

  // Resolves once the page stops changing: SETTLE_QUIET_MS without a DOM mutation, after at least SETTLE_MIN_MS, within SETTLE_MAX_MS.
  function settle() {
    return new Promise((resolve) => {
      const start = Date.now();
      let last = start;
      const obs = new MutationObserver(() => { last = Date.now(); });
      obs.observe(document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true });
      const timer = setInterval(() => {
        const now = Date.now();
        if ((now - start >= SETTLE_MIN_MS && now - last >= SETTLE_QUIET_MS) || now - start >= SETTLE_MAX_MS) {
          clearInterval(timer); obs.disconnect(); resolve();
        }
      }, 100);
    });
  }

  function readTotal(loc) {
    const el = (loc.cfg && P.q(loc.cfg.total)) || P.findTotalGeneric();
    return el ? P.parseAmount(el.textContent) : null;
  }

  function signal(loc) {
    const cfg = loc.cfg || {};
    if (cfg.success && P.q(cfg.success)) return "success";
    if (cfg.failure && P.q(cfg.failure)) return "failure";
    // An error message in the coupon field's container counts as a refusal.
    let box = loc.input;
    for (let d = 0; d < 3 && box && box.parentElement; d++) box = box.parentElement;
    if (box && ERROR_RX.test(box.innerText || "")) return "failure";
    return null;
  }

  async function locateWithReveal() {
    let loc = P.locate(store, storeSel);
    if (!loc.input && loc.reveal) {
      loc.reveal.click();
      await sleep(600);
      loc = P.locate(store, storeSel);
    }
    return loc.input ? loc : null;
  }

  async function removeApplied(loc) {
    const btn = loc.cfg && P.q(loc.cfg.remove);
    if (btn) { btn.click(); await settle(); }
  }

  // Tries one code and returns {code, total, signal}.
  async function tryCode(code) {
    let loc = await locateWithReveal();
    if (!loc) return { code, total: null, signal: "no-field" };
    await removeApplied(loc);
    loc = (await locateWithReveal()) || loc;
    setValue(loc.input, code);
    submit(loc);
    await settle();
    loc = (await locateWithReveal()) || loc;
    return { code, total: readTotal(loc), signal: signal(loc) };
  }

  // ---------- the trial run, resumable across a page reload ----------

  function saveRun(run) { sessionStorage.setItem(RUN_KEY, JSON.stringify(run)); }
  function loadRun() {
    try {
      const run = JSON.parse(sessionStorage.getItem(RUN_KEY) || "null");
      return run && Date.now() - run.updated < 120000 ? run : null;
    } catch (_) { return null; }
  }

  function pickBest(run) {
    let best = null;
    for (const r of run.results) {
      if (r.signal === "no-field") continue;
      // A lowered total outranks text read near the field, since error-like text (e.g., a minimum order note) may sit there all along.
      const lowered = r.total != null && run.base != null && r.total < run.base - 0.004;
      if (!lowered && r.signal !== "success") continue;
      if (!best || (r.total ?? Infinity) < (best.total ?? Infinity)) best = r;
    }
    return best;
  }

  async function runTrials(run) {
    running = true;
    showProgress(run);
    while (run.next < run.codes.length && !run.stopped) {
      const code = run.codes[run.next];
      run.next += 1; run.updated = Date.now(); run.pending = code; saveRun(run);
      const res = await tryCode(code);
      run.pending = null; run.results.push(res); run.updated = Date.now(); saveRun(run);
      showProgress(run);
    }
    const best = pickBest(run);
    if (best) {
      // Marked first, since a checkout which reloads on submit restarts this script mid-apply.
      run.finalizing = best.code; run.updated = Date.now(); saveRun(run);
      const res = await tryCode(best.code);
      if (res.total != null) best.total = res.total;
    } else {
      const loc = await locateWithReveal();
      if (loc) { await removeApplied(loc); setValue(loc.input, ""); }
    }
    sessionStorage.removeItem(RUN_KEY);
    running = false;
    showDone(run, best);
  }

  async function startRun() {
    const loc = await locateWithReveal();
    if (!loc) { showMessage("No coupon field found on this page. Open the cart or checkout page and try again."); return; }
    const run = { store, codes: known.slice(0, MAX_CODES).map((k) => k.c), next: 0, results: [], base: readTotal(loc),
      started: Date.now(), updated: Date.now(), pending: null, stopped: false };
    await runTrials(run);
  }

  async function resumeRun(run) {
    if (run.finalizing) {
      const best = pickBest(run) || { code: run.finalizing, total: null };
      const loc = await locateWithReveal();
      const now = loc ? readTotal(loc) : null;
      if (now != null) best.total = now;
      sessionStorage.removeItem(RUN_KEY);
      showDone(run, best);
      return;
    }
    if (run.pending) {
      // The page reloaded while a code was being tried: record the result now visible.
      const loc = await locateWithReveal();
      run.results.push({ code: run.pending, total: loc ? readTotal(loc) : null, signal: loc ? signal(loc) : null });
      run.pending = null;
    }
    await runTrials(run);
  }

  // ---------- noticing a code the user typed ----------

  function watchManualEntry() {
    let armed = null;
    const arm = () => {
      if (running) return;
      const loc = P.locate(store, storeSel);
      if (!loc.input || !loc.input.value.trim()) return;
      armed = { code: loc.input.value.trim(), base: readTotal(loc) };
      settle().then(() => checkManual(armed));
    };
    document.addEventListener("click", (e) => {
      const loc = P.locate(store, storeSel);
      if (loc.input && loc.apply && (e.target === loc.apply || loc.apply.contains(e.target))) arm();
    }, true);
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      const loc = P.locate(store, storeSel);
      if (loc.input && e.target === loc.input) arm();
    }, true);
  }

  async function checkManual(armed) {
    if (!armed || running) return;
    const code = armed.code;
    if (known.some((k) => k.c.toUpperCase() === code.toUpperCase())) return;
    const loc = P.locate(store, storeSel);
    if (!loc.input) return;
    const total = readTotal(loc), sig = signal(loc);
    const worked = sig === "success" || (sig !== "failure" && total != null && armed.base != null && total < armed.base - 0.004);
    if (!worked) return;
    const prefs = (await send({ action: "prefs" })) || {};
    if (prefs.shareAsk === false) return;
    showSharePrompt(code);
  }

  // ---------- the panel (a shadow root, unstyled by the page) ----------

  function panel() {
    if (ui) return ui;
    const host = document.createElement("div");
    host.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647;";
    const root = host.attachShadow({ mode: "closed" });
    root.innerHTML = `<style>
      .box{font:14px/1.4 system-ui,sans-serif;background:#fff;color:#1a1a1a;border:1px solid #c8c8c8;border-radius:8px;
        box-shadow:0 4px 16px rgba(0,0,0,.18);padding:12px 14px;max-width:320px}
      .t{font-weight:600;margin-bottom:6px}.row{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}
      button{font:inherit;border-radius:6px;border:1px solid #888;background:#f4f4f4;padding:4px 10px;cursor:pointer}
      button.p{background:#1f6f43;border-color:#1f6f43;color:#fff}.m{color:#555;font-size:12px}code{font-weight:600}
      @media (prefers-color-scheme: dark){.box{background:#1f1f1f;color:#eee;border-color:#444}button{background:#333;color:#eee}.m{color:#aaa}}
    </style><div class="box"></div>`;
    document.documentElement.appendChild(host);
    ui = { host, box: root.querySelector(".box") };
    return ui;
  }
  function close() { if (ui) { ui.host.remove(); ui = null; } }
  function render(html, buttons = [], state = "") {
    const { box, host } = panel();
    host.dataset.ocState = state;
    box.innerHTML = html + (buttons.length ? `<div class="row"></div>` : "");
    const row = box.querySelector(".row");
    for (const [label, fn, primary] of buttons) {
      const b = document.createElement("button");
      b.textContent = label; if (primary) b.className = "p";
      b.addEventListener("click", fn);
      row.appendChild(b);
    }
  }
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const money = (v) => (v == null ? "unknown" : v.toFixed(2));

  function showOffer() {
    const n = Math.min(known.length, MAX_CODES);
    render(`<div class="t">Open Coupons</div><div>${n} known code${n === 1 ? "" : "s"} for ${esc(store)}. Try them and keep the one giving the lowest total?</div>`,
      [["Try codes", () => startRun(), true], ["Not now", () => { sessionStorage.setItem("__open_coupons_dismissed", "1"); close(); }]], "offer");
  }
  function showProgress(run) {
    render(`<div class="t">Trying codes: ${run.results.length} of ${run.codes.length}</div>
      <div class="m">Total before codes: ${money(run.base)}. Lowest so far: ${money(pickBest(run)?.total ?? null)}.</div>`,
      [["Stop", () => { run.stopped = true; saveRun(run); }]], "progress");
  }
  function showDone(run, best) {
    if (best) {
      const saved = run.base != null && best.total != null ? ` Total ${money(run.base)} to ${money(best.total)}.` : "";
      render(`<div class="t">Applied <code>${esc(best.code)}</code></div><div>${saved} Tried ${run.results.length} codes.</div>`, [["Close", close, true]], "done:" + best.code);
    } else {
      render(`<div class="t">No code lowered the total</div><div class="m">Tried ${run.results.length} codes on ${esc(store)}.</div>`, [["Close", close, true]], "done:none");
    }
  }
  function showMessage(text) { render(`<div>${esc(text)}</div>`, [["Close", close]], "message"); }
  function showSharePrompt(code) {
    render(`<div class="t">The code <code>${esc(code)}</code> worked</div>
      <div>Share it with the open code database? It sends the site (${esc(store)}) and the code, and nothing else.</div>`,
      [["Share", async () => { const r = await send({ action: "share", store, code }); showMessage(r && r.sent ? "Shared. Thank you." : "Saved; it is sent once sharing opens."); }, true],
       ["No", close], ["Never ask", async () => { await send({ action: "setPrefs", prefs: { shareAsk: false } }); close(); }]], "share:" + code);
  }

  // ---------- start ----------

  async function init() {
    const res = await send({ action: "codes", store });
    known = (res && res.codes) || [];
    storeSel = (res && res.selectors) || null;
    watchManualEntry();
    const run = loadRun();
    if (run && run.store === store) { resumeRun(run); return; }
    if (!known.length || sessionStorage.getItem("__open_coupons_dismissed")) return;
    const prefs = (await send({ action: "prefs" })) || {};
    if (prefs.autoOffer === false) return;
    // Test pages on the reserved .test domain start a run from the URL, since a test browser cannot press the panel's buttons.
    const autorun = /\.test$/.test(location.hostname) && location.hash === "#oc-autorun";
    // Look for the field now and twice more as single-page checkouts render.
    for (const wait of [0, 2000, 5000]) {
      await sleep(wait);
      const loc = P.locate(store, storeSel);
      if (loc.input || (loc.reveal && (CHECKOUT_URL_RX.test(location.pathname) || P.findTotalGeneric()))) {
        if (autorun) { history.replaceState(null, "", location.pathname + location.search); startRun(); } else showOffer();
        return;
      }
    }
  }

  api.runtime.onMessage.addListener((msg) => {
    if (msg && msg.action === "tryNow") { startRun(); }
  });

  init();
})();
