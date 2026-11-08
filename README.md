# Open Coupons

A browser extension (Firefox first, then Chrome, from one WebExtensions codebase) which tries the known coupon codes on a
checkout page and keeps the code giving the lowest total, and an open code database anyone can search with no login,
no new tab, and no ads.

## Privacy

- The extension downloads the whole code database at once and looks a store up in the browser, so no request names the
  site being visited.
- It collects no personal, browsing, or ad data, and it swaps no affiliate cookies.
- Its only upload: after a code the user typed works and is missing from the database, it asks whether to share the code,
  and a share sends the store and the code alone. Shares wait in a local queue until a receiving endpoint is approved
  (`SHARE_ENDPOINT` in `extension/background.js`).

## Layout

| Folder | Holds |
|---|---|
| `extension/` | the extension: `manifest.json` (Manifest V3, Firefox and Chrome), `background.js` (database and shares), `content.js` (the trial run and the share prompt), `lib/platforms.js` (coupon-field selectors by store and platform, and a generic field search), `popup.*`, `data/codes.json` (the bundled database) |
| `site/` | the static search page (`index.html`) and its copy of `data/codes.json` |
| `seed/` | the seed bank: `probe_sources.py` (robots.txt and terms of each source), `harvest.py` (one source's store pages into `data/seed_<source>.sqlite`), `extract.py` (the generic code extractor), `build_db.py` (the merge into `codes.json`) |
| `tests/` | mock checkout pages and `run_tests.py`, an end-to-end run in headless Chromium (`sbatch tests/run_tests.sbatch`) |

## How the extension finds the coupon field

1. A store's own selectors: `lib/platforms.js` (`STORES`), then those the database holds for the store.
2. The checkout platform: WooCommerce, Shopify, Magento 2, BigCommerce, Salesforce Commerce Cloud, and PrestaShop.
3. A generic search: a visible text field whose name, label, or placeholder mentions a promo, coupon, discount, or voucher
   code, the apply button nearest it, and the amount beside a "Total" label. A hidden field behind a "Have a promo code?"
   link is opened first.

Each code is typed through the field's native value setter (React and Vue checkouts ignore a plain assignment), applied,
and read once the page stops changing. A checkout which reloads on every code resumes the run from `sessionStorage`.

## Seed sources (checked 2026-11-08)

robots.txt does not gate the harvest (a standing ruling, 2026-11-08); each site's crawl delay, where it states one, still sets the pace.

| Source | Used | How the codes are read |
|---|---|---|
| Syrup (DiscountDB) | code studied, no data | its API host (db.joinsyrup.com) serves a parked-domain page |
| Honey | yes | store pages embed the public codes and Honey's coupon-field selectors; no sitemap, so the walk follows store-to-store links |
| Capital One Shopping | yes | a table of codes on each store page |
| CouponFollow | yes | each offer's code is base64 of numbers XORed with a key in the site's tracking script (`CF_KEY` in `seed/extract.py`) |
| Coupons.com | yes | store pages embed codes with expiry dates |
| PromoCodes.com | yes | store pages embed codes |
| Groupon | no | its terms forbid crawlers, robots, and data mining |
| RetailMeNot, Dealspotr, Knoji, SimplyCodes, CouponCabin | no | each refused our requests (403) |
| Offers.com, Savings.com, DealNews, Rakuten | no | no codes in the page markup |

Requests go out from one address, one at a time a site, 3 s apart.

## Testing

`sbatch tests/run_tests.sbatch` loads the extension into headless Chromium, then into Firefox (a temporary add-on installed
through Firefox's remote debugging protocol), and runs three mock checkouts (a WooCommerce
cart, a generic checkout with a hidden field, and a checkout which reloads on every code) and the share prompt.
