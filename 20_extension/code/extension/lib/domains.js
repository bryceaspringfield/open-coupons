// Maps a page's host name to the store key the code database uses (the registrable domain, e.g., "shop.example.co.uk" -> "example.co.uk").
(() => {
  // Second-level suffixes where the store name sits one label further left.
  const TWO_LABEL_SUFFIXES = new Set([
    "co.uk", "org.uk", "ac.uk", "com.au", "net.au", "co.nz", "co.jp", "com.br", "com.mx", "co.in", "com.sg", "com.tr",
    "co.za", "com.ar", "com.hk", "com.tw", "co.kr", "com.cn", "co.il", "com.my", "com.ph", "co.id",
  ]);
  // Hosted checkout domains which belong to another store.
  const CHECKOUT_ALIASES = {
    "nordcheckout.com": "nordvpn.com",
  };

  function storeKey(host) {
    host = String(host || "").toLowerCase().replace(/\.$/, "");
    const labels = host.split(".");
    if (labels.length <= 2) return CHECKOUT_ALIASES[host] || host;
    const last2 = labels.slice(-2).join(".");
    const key = TWO_LABEL_SUFFIXES.has(last2) ? labels.slice(-3).join(".") : last2;
    return CHECKOUT_ALIASES[key] || key;
  }

  globalThis.OC_DOMAINS = { storeKey };
})();
