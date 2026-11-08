#!/usr/bin/env python3
"""Fetch robots.txt and the terms page of each candidate coupon source; write one JSON summary.

For each source: whether robots.txt admits a generic crawler on a sample store page, and each sentence of the
terms mentioning scraping, crawling, robots, or automated access. Requests run concurrently across sources,
one request at a time within a source, 2 s apart.
"""
import concurrent.futures as cf
import json
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser

UA = "Mozilla/5.0 (X11; Linux x86_64) coupon-research/0.1"
# source: (base URL, sample store path, candidate terms paths)
SOURCES = {
    "discountdb": ("https://discountdb.ch", "/api/v1/syrup/coupons?domain=nordvpn.com", ["/terms", "/legal", "/privacy"]),
    "discountdb_vercel": ("https://discountdb.vercel.app", "/", ["/terms", "/legal"]),
    "honey": ("https://www.joinhoney.com", "/shop/amazon", ["/terms", "/legal/terms"]),
    "capital_one_shopping": ("https://capitaloneshopping.com", "/s/amazon.com/coupon", ["/terms", "/legal/terms"]),
    "groupon": ("https://www.groupon.com", "/coupons/amazon", ["/legal/termsofuse", "/terms"]),
    "retailmenot": ("https://www.retailmenot.com", "/view/amazon.com", ["/static/terms/", "/terms"]),
    "coupons_com": ("https://www.coupons.com", "/coupon-codes/amazon", ["/terms-of-use", "/terms"]),
    "couponfollow": ("https://couponfollow.com", "/site/amazon.com", ["/terms", "/legal/terms"]),
    "dealspotr": ("https://dealspotr.com", "/promo-codes/amazon.com", ["/terms", "/terms-of-service"]),
    "knoji": ("https://amazon.knoji.com", "/promo-codes/", ["/terms", "/terms-of-service"]),
    "wethrift": ("https://www.wethrift.com", "/amazon", ["/terms", "/terms-of-service"]),
    "slickdeals": ("https://slickdeals.net", "/coupons/amazon/", ["/legal/terms", "/terms"]),
    "couponbirds": ("https://www.couponbirds.com", "/codes/amazon.com", ["/terms", "/terms-of-use"]),
    "savings_com": ("https://www.savings.com", "/coupons/amazon.com", ["/terms", "/terms-of-use"]),
    "offers_com": ("https://www.offers.com", "/amazon/", ["/terms/", "/terms-of-use/"]),
    "simplycodes": ("https://simplycodes.com", "/store/amazon.com", ["/terms", "/terms-of-service"]),
    "couponcabin": ("https://www.couponcabin.com", "/coupons/amazon/", ["/terms/", "/terms-of-use/"]),
    "rakuten": ("https://www.rakuten.com", "/amazon.com", ["/help/article/terms-conditions-360002101688", "/terms"]),
    "dealnews": ("https://www.dealnews.com", "/coupons/Amazon/", ["/terms.html", "/terms"]),
    "promocodes_com": ("https://www.promocodes.com", "/amazon-coupons", ["/terms", "/terms-of-use"]),
}
TERMS_RX = re.compile(r"[^.]{0,300}\b(scrap\w*|crawl\w*|robot\w*|spider\w*|automated|data mining|harvest\w*)\b[^.]{0,300}\.", re.I)
GAP_S = 2.0


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(3_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # network errors are data here
        return f"ERR {type(e).__name__}: {e}"[:120], ""


def text_of(html):
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html))


def probe(name, base, sample, terms_paths):
    out = {"source": name, "base": base}
    st, robots = get(base + "/robots.txt")
    out["robots_status"] = st
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(robots.splitlines())
    out["robots_admits_sample"] = rp.can_fetch("*", base + sample) if st == 200 else None
    try:  # Python 3.6 raises AttributeError when robots.txt has no "User-agent: *" group
        out["crawl_delay"] = rp.crawl_delay("*") if st == 200 else None
    except AttributeError:
        out["crawl_delay"] = None
    out["robots_disallow_star"] = [l.strip() for l in robots.splitlines() if l.lower().startswith("disallow")][:40]
    for p in terms_paths:
        time.sleep(GAP_S)
        st, html = get(base + p)
        if st == 200 and len(html) > 2000:
            t = text_of(html)
            out["terms_url"] = base + p
            out["terms_hits"] = sorted({m.group(0).strip() for m in TERMS_RX.finditer(t)})[:12]
            break
        out.setdefault("terms_tried", []).append(f"{p} {st}")
    time.sleep(GAP_S)
    st, body = get(base + sample)
    out["sample_status"] = st
    out["sample_bytes"] = len(body)
    out["sample_head"] = body[:300] if base.endswith(".ch") else None
    return out


def main(path):
    with cf.ThreadPoolExecutor(len(SOURCES)) as ex:  # one thread a source; each source stays serial at GAP_S
        res = list(ex.map(lambda kv: probe(kv[0], *kv[1]), SOURCES.items()))
    # DiscountDB's open API: merchant list and version, for the seed pull's size.
    for ep in ["/api/v1/syrup/version", "/api/v1/syrup/merchants", "/api/v1/coupons/search?limit=2"]:
        st, body = get("https://api.discountdb.ch" + ep)
        res.append({"source": "discountdb_api", "endpoint": ep, "status": st, "bytes": len(body), "head": body[:600]})
    json.dump(res, open(path, "w"), indent=1)
    for r in res:
        print(json.dumps({k: r.get(k) for k in ("source", "endpoint", "robots_status", "robots_admits_sample", "crawl_delay", "sample_status", "status", "bytes")}))


if __name__ == "__main__":
    main(sys.argv[1])
