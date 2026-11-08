// Coupon-field selectors by store and by checkout platform, and a generic search used when neither matches.
// Each config may name: input, apply, reveal (a link showing a hidden field), success, failure, total, remove.
(() => {
  const STORES = {
    "applebees.com": {
      input: "#txtPromoCode", apply: ".btnPromoApply", success: ".lnkPromoRemove", failure: ".invalid-feedback",
      total: ".order-price", remove: ".lnkPromoRemove",
    },
    "nordvpn.com": {
      input: "input[name='couponCode']", reveal: "p[data-testid='coupon-show-form-button'] > a",
      apply: "button[data-testid='coupon-apply-button']", success: "div[data-testid='coupon-applied-message']",
      failure: "div[data-testid='coupon-error-alert']", total: "span[data-testid='CartSummary-total-amount']",
      remove: "button[data-testid='coupon-delete-applied-button']",
    },
  };

  const PLATFORMS = {
    woocommerce: {
      detect: () => !!document.querySelector("body.woocommerce-cart, body.woocommerce-checkout, .woocommerce"),
      input: "input[name='coupon_code']", apply: "button[name='apply_coupon'], input[name='apply_coupon']",
      reveal: ".showcoupon", success: ".woocommerce-message", failure: ".woocommerce-error",
      total: ".order-total .amount, .cart_totals .order-total .amount", remove: ".woocommerce-remove-coupon",
    },
    shopify: {
      detect: () => !!(window.Shopify || document.querySelector("meta[name='shopify-checkout-api-token'], [data-shopify]")),
      input: "input[name='reductions'], input[name='discount'], #checkout_reduction_code, input#discount",
      apply: "button[aria-label*='pply'], #checkout_submit, button[name='checkout[submit]']",
      failure: "#error-for-reduction_code, [id^='error-for-ReductionsInput']",
      total: ".payment-due__price, [data-checkout-payment-due-target], .total-line--total .total-line__price",
      remove: "button[aria-label^='Remove'], .tag__button",
    },
    magento2: {
      detect: () => !!document.querySelector("#discount-coupon-form, form#discount-coupon-form, body.checkout-cart-index"),
      input: "#coupon_code, #discount-code", apply: "#discount-coupon-form button.action.apply, .action-apply",
      reveal: "#block-discount-heading", success: ".message-success", failure: ".message-error",
      total: ".grand.totals .price, tr.grand.totals .amount .price", remove: ".action-cancel, button.action.cancel",
    },
    bigcommerce: {
      detect: () => !!(window.BCData || document.querySelector("[data-test='redeemable-code-input']")),
      input: "[data-test='redeemable-code-input'], #redeemableCode", apply: "[data-test='redeemable-code-submit'], #applyRedeemableButton",
      reveal: "[data-test='redeemable-label']", failure: ".form-inlineMessage, [data-test='redeemable-code-error']",
      total: "[data-test='cart-total'] [data-test='cart-price-value'], .cart-priceItem--total .cart-priceValue",
      remove: "[data-test='cart-price-item'] .cart-priceItem-link, .redeemable-remove",
    },
    salesforce_commerce: {
      detect: () => !!document.querySelector(".promo-code-form, form.promo-code-form, #couponCode"),
      input: "#couponCode, input[name='couponCode']", apply: ".promo-code-btn, button.promo-code-submit",
      success: ".coupon-price-adjustment", failure: ".coupon-error-message, .coupon-missing-error",
      total: ".grand-total, .order-value .grand-total-sum", remove: ".remove-coupon",
    },
    prestashop: {
      detect: () => !!(window.prestashop || document.querySelector("input[name='discount_name']")),
      input: "input[name='discount_name']", apply: "form[action*='cart'] button[type='submit'] span, .promo-code button",
      reveal: ".promo-code-button a, .cart-voucher a.collapse-button", failure: ".promo-code .alert-danger, .js-error",
      total: ".cart-total .value, .cart-summary-line.cart-total .value",
    },
  };

  const FIELD_RX = /promo|coupon|discount|voucher|redeem|reduction|offer.?code|promotional|rabatt|gutschein|c[oó]digo|cupon|cupón|remise|sconto/i;
  const FIELD_EXCLUDE_RX = /e-?mail|search|zip|postal|card.?number|cc-|phone|address|name\b|password|newsletter|quantity|qty/i;
  const APPLY_RX = /^\s*(apply|redeem|submit|use|add|ok|go|enter|activate|valider|appliquer|anwenden|einl[oö]sen|aplicar|applica)\b/i;
  const REVEAL_RX = /(have|add|enter|apply|got|use).{0,25}(promo|coupon|discount|voucher|gift|offer)|(promo|coupon|discount|voucher).{0,8}code\??$/i;
  const TOTAL_LABEL_RX = /^(order\s+|estimated\s+|grand\s+|cart\s+)?total(\s+due|\s+to\s+pay|\s*\(.*\))?\s*:?$|^amount due$|^you pay$/i;

  function visible(el) {
    if (!el || !el.isConnected) return false;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
  }

  function describe(el) {
    const label = el.id ? document.querySelector(`label[for="${CSS.escape(el.id)}"]`) : null;
    return [el.id, el.name, el.placeholder, el.getAttribute("aria-label"), el.getAttribute("autocomplete"),
      el.className, label && label.textContent].filter(Boolean).join(" ");
  }

  function findInputGeneric() {
    const inputs = [...document.querySelectorAll("input:not([type]), input[type='text'], input[type='search'], input[type='tel']")];
    return inputs.find((el) => visible(el) && FIELD_RX.test(describe(el)) && !FIELD_EXCLUDE_RX.test(el.name || "") &&
      !/search/i.test(el.type)) || null;
  }

  function findApplyNear(input) {
    let scope = input;
    for (let depth = 0; depth < 5 && scope; depth++) {
      scope = scope.parentElement;
      if (!scope) break;
      const buttons = [...scope.querySelectorAll("button, input[type='submit'], input[type='button'], [role='button']")].filter(visible);
      const named = buttons.find((b) => APPLY_RX.test(b.textContent || b.value || b.getAttribute("aria-label") || ""));
      if (named) return named;
      if (buttons.length === 1) return buttons[0];
    }
    return null;
  }

  function findRevealGeneric() {
    const els = [...document.querySelectorAll("a, button, summary, [role='button'], label, span, div[tabindex]")];
    return els.find((el) => visible(el) && el.children.length <= 2 && REVEAL_RX.test((el.textContent || "").trim().slice(0, 60))) || null;
  }

  // Parses "$1,234.56", "1.234,56 €", or "1 234,56" into a number; null when no amount is present.
  function parseAmount(text) {
    const m = String(text || "").replace(/ /g, " ").match(/-?\d[\d.,\s]*/);
    if (!m) return null;
    let s = m[0].replace(/\s/g, "");
    const lastDot = s.lastIndexOf("."), lastComma = s.lastIndexOf(",");
    if (lastComma > lastDot && s.length - lastComma - 1 <= 2) s = s.replace(/\./g, "").replace(",", ".");
    else s = s.replace(/,/g, "");
    const v = parseFloat(s);
    return Number.isFinite(v) ? v : null;
  }

  // Finds the order total by its label ("Total", "Order total", "Estimated total") when no selector names it.
  function findTotalGeneric() {
    const cands = [];
    for (const el of document.querySelectorAll("td, th, dt, span, div, p, strong, b, label")) {
      if (el.children.length > 2 || !visible(el)) continue;
      const t = (el.textContent || "").trim();
      if (t.length > 40 || !TOTAL_LABEL_RX.test(t)) continue;
      // The amount sits in the label's row: a later sibling, or the parent's text.
      let row = el.parentElement;
      for (let d = 0; d < 3 && row; d++, row = row.parentElement) {
        const amt = [...row.querySelectorAll("*")].filter((x) => x !== el && x.children.length === 0 && /\d/.test(x.textContent) &&
          /[$€£¥₹]|\d[.,]\d{2}\b/.test(x.textContent));
        if (amt.length) { cands.push(amt[amt.length - 1]); break; }
      }
    }
    // The last labeled total on the page is the amount charged.
    return cands.length ? cands[cands.length - 1] : null;
  }

  function q(sel) {
    if (!sel) return null;
    let els;
    try { els = document.querySelectorAll(sel); } catch (_) { return null; }  // a selector from the database may be invalid CSS
    for (const el of els) if (visible(el)) return el;
    return null;
  }

  // Returns {source, config, input, apply, total} for the current page, or null when no coupon field is present.
  // extra: selectors the database holds for this store, used where this file names none.
  function locate(store, extra) {
    let source = null, cfg = {};
    if (STORES[store]) { source = "store:" + store; cfg = STORES[store]; }
    else if (extra && extra.input) { source = "database:" + store; cfg = extra; }
    else {
      for (const [name, p] of Object.entries(PLATFORMS)) {
        try { if (p.detect()) { source = "platform:" + name; cfg = p; break; } } catch (_) { /* a detector failing means no match */ }
      }
    }
    const input = q(cfg.input) || findInputGeneric();
    if (!input) return { source, cfg, input: null, reveal: q(cfg.reveal) || findRevealGeneric() };
    const apply = q(cfg.apply) || findApplyNear(input);
    const total = q(cfg.total) || findTotalGeneric();
    return { source: source || "generic", cfg, input, apply, total };
  }

  globalThis.OC_PLATFORMS = { STORES, PLATFORMS, locate, parseAmount, visible, q, findTotalGeneric, FIELD_RX };
})();
