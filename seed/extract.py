#!/usr/bin/env python3
"""Generic extractor of coupon codes from a coupon site's store page.

Codes come from code-like JSON keys in the page's embedded data ("code", "couponCode", "promoCode", ...), read after
unescaping JSON nested in strings, and from CouponFollow's <span data-code="true">CODE</span> markup. Each code takes
the nearest description-like field. The store's own domain is the most common host among the page's offer links.

Self-test on stored sample pages: extract.py SAMPLE.sqlite
"""
import collections
import re
import sys
import urllib.parse

CODE_KEY_RX = re.compile(r'"(code|couponCode|coupon_code|promoCode|promo_code|promocode|offerCode|voucherCode|discountCode)"\s*:\s*"([^"]{3,32})"')
EXPIRY_RX = re.compile(r'"(expiredAt|expirationDate|expiration_date|endTime|expires|expiresAt|endDate)"\s*:\s*"([0-9]{4}-[0-9]{2}-[0-9]{2})')
DESC_RX = re.compile(r'"(description|generatedDescription|title|headline|offerText|offer_title|name)"\s*:\s*"([^"]{6,300})"')
CF_RX = re.compile(r'<span data-code="true"[^>]*>\s*([^<\s]{2,32})\s*</span>')
CF_TITLE_RX = re.compile(r"<h3[^>]*>(.*?)</h3>", re.S)
URL_RX = re.compile(r'"(url|link|merchantUrl|storeUrl|website|domain|affiliateUrl|deepLink)"\s*:\s*"(https?://[^"]+)"')
CODE_OK_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{2,31}$")
STOP = {"COUPON", "CODE", "CODES", "DEAL", "DEALS", "SALE", "NULL", "TRUE", "FALSE", "NONE", "USD", "EUR", "GBP", "CAD", "AUD",
        "PROMO", "OFFER", "ONLINE", "INSTORE", "IN_STORE", "PRINTABLE", "CASHBACK", "SHIPPING", "REWARD", "UNDEFINED", "EXPIRED",
        "ACTIVE", "VERIFIED", "NOCODE", "NO_CODE", "SEE_DEAL", "GET_DEAL", "SHOW_CODE"}
# Hosts of the coupon sites, affiliate networks, and CDNs, which are never the store.
NOT_STORE = re.compile(r"(joinhoney|capitaloneshopping|couponfollow|coupons\.com|promocodes|discountcodes|anrdoezrs|dpbolvw|jdoqocy|"
                       r"tkqlhce|kqzyfj|awin1|shareasale|linksynergy|impact|pntra|pjtra|sjv\.io|go2cloud|rakuten|cloudfront|"
                       r"storyblok|atolls|dlnws|cf-static|rebates\.jp|akamai|googleapis|gstatic|facebook|twitter|instagram|pinterest|youtube|apple\.com/app|play\.google)", re.I)
HONEY_SEL_RX = re.compile(r'"(pns_site(?:SelCartCodeBox|SelCartCodeSubmit|SelCartTotalPrice|PreApplyCodeAction|RemoveCodeAction|'
                          r'SelCartDiscountPrice|SelCartInitCodeRegex))"\s*:\s*"((?:[^"\\]|\\.)*)"')
TWO_LABEL = {"co.uk", "org.uk", "com.au", "co.nz", "co.jp", "com.br", "com.mx", "co.in", "com.sg", "co.za", "com.ar", "com.hk", "co.kr"}


def store_key(host):
    host = host.lower().strip().strip(".")
    host = re.sub(r"^https?://", "", host).split("/")[0].split(":")[0]
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    return ".".join(labels[-3:]) if ".".join(labels[-2:]) in TWO_LABEL else ".".join(labels[-2:])


def unescape(html):
    for _ in range(2):  # JSON nested once or twice inside strings
        html = html.replace('\\\\"', '"').replace('\\"', '"').replace("\\u002F", "/").replace("\\u002f", "/").replace("\\/", "/")
    return html


def code_ok(c):
    # Lowercase words with no digit are field values (e.g., "facebook"), and long hex strings are record IDs.
    return bool(CODE_OK_RX.match(c)) and any(ch.isalpha() for ch in c) and c.upper() not in STOP and not re.search(r"[a-z]_[a-z]", c) \
        and not (c.islower() and not any(ch.isdigit() for ch in c)) and not re.fullmatch(r"[0-9a-f]{16,}", c) \
        and not re.fullmatch(r"[a-z]+(-[a-z0-9]+)+", c)


def clean(t):
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), t)[:300] if t else None


def nearest(rx, text, pos, span=1500):
    best = None
    for m in rx.finditer(text, max(0, pos - span), pos + span):
        d = abs(m.start() - pos)
        if best is None or d < best[0]:
            best = (d, m)
    return best[1] if best else None


def extract(html, source=""):
    text = unescape(html)
    codes = {}
    for m in CODE_KEY_RX.finditer(text):
        c = m.group(2).strip()
        if not code_ok(c):
            continue
        window = text[max(0, m.start() - 1500): m.start() + 1500]
        if not re.search(r"discount|% ?off|expir|coupon|deal|offer|save|promo", window, re.I):
            continue
        d = nearest(DESC_RX, text, m.start())
        e = nearest(EXPIRY_RX, text, m.start(), 900)
        codes.setdefault(c, {"code": c, "description": clean(d.group(2)) if d else None, "extra": f"expires={e.group(2)}" if e else None})
    for m in CF_RX.finditer(html):
        c = m.group(1).strip()
        if not code_ok(c):
            continue
        titles = list(CF_TITLE_RX.finditer(html, max(0, m.start() - 6000), m.start()))
        t = re.sub(r"<[^>]+>|\s+", " ", titles[-1].group(1)).strip() if titles else None
        codes.setdefault(c, {"code": c, "description": t[:300] if t else None})
    hosts = collections.Counter()
    for m in URL_RX.finditer(text):
        h = urllib.parse.urlsplit(m.group(2)).netloc
        if h and not NOT_STORE.search(h):
            hosts[store_key(h)] += 1
    selectors = {m.group(1): m.group(2).encode().decode("unicode_escape", "ignore") for m in HONEY_SEL_RX.finditer(text)} if source == "honey" else {}
    return {"codes": list(codes.values()), "store_host": hosts.most_common(1)[0][0] if hosts else None, "selectors": selectors}


if __name__ == "__main__":
    import sqlite3
    con = sqlite3.connect(sys.argv[1])
    for url, body in con.execute("select url, body from pages where status=200 and url not like '%robots%' and url not like '%terms%' and url not like '%sitemap%'"):
        src = "honey" if "joinhoney" in url else ""
        r = extract(body.decode("utf-8", "replace"), src)
        print(f"{len(r['codes']):>3} codes  store={r['store_host']}  sel={len(r['selectors'])}  {url}")
        for c in r["codes"][:6]:
            print(f"      {c['code']:<16} {(c['description'] or '')[:90]}")
