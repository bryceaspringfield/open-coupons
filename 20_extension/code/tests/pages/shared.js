// The mock store's rules: a code takes a share or an amount off the subtotal; unknown codes fail.
window.MOCK_CODES = { SAVE10: { pct: 10 }, SAVE20: { pct: 20 }, TAKE5: { off: 5 }, SECRET15: { pct: 15 } };
window.mockTotal = (sub, code) => {
  const c = window.MOCK_CODES[(code || "").toUpperCase()];
  if (!c) return sub;
  return Math.round((c.pct ? sub * (1 - c.pct / 100) : sub - c.off) * 100) / 100;
};
