#!/usr/bin/env python3
"""Harvest the coupon codes a source publishes on its store pages, into 10_seed/output/seed_<source>.sqlite.

Usage: harvest.py SOURCE [--gap S] [--limit N] [--list-only] [--egress NAME --shard I/N]
With --shard, this copy takes the store pages whose CRC32 falls in shard I of N and writes 10_seed/output/seed_<source>_s<I>.sqlite,
and --egress sends its requests through that egress of ~/.cache/wb_broker/egresses.d/ (one shard an egress address).
RetailMeNot and Groupon show each code only on request: each code offer on a store page takes one more request.
Reads the source's sitemap for its store pages, then fetches each page once (resumable: pages already fetched are
skipped), GAP seconds apart from one address, and keeps only the extracted codes, never the page. The codes come from
one generic extractor (extract.py) shared by every source.
"""
import argparse
import gzip
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

sys.path.insert(0, __import__("os").path.dirname(__file__))
import extract  # noqa: E402

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
# source: (site root, sitemap roots, store-page pattern, store key from URL: a regex group holding the store's domain, or None)
SOURCES = {
    "honey": ("https://www.joinhoney.com", ["/sitemap.xml"], r"^https://www\.joinhoney\.com/shop/[^/?#]+/?$", None),
    "simplycodes": ("https://simplycodes.com", ["/sitemap/index.xml"], r"^https://simplycodes\.com/store/([^/?#]+\.[a-z.]+)/?$", 1),
    "capital_one_shopping": ("https://capitaloneshopping.com", ["/sitemap.xml"], r"^https://capitaloneshopping\.com/s/([^/?#]+\.[a-z.]+)/coupon/?$", 1),
    "couponfollow": ("https://couponfollow.com", ["/sitemap/index.xml"], r"^https://couponfollow\.com/site/([^/?#]+\.[a-z.]+)/?$", 1),
    "coupons_com": ("https://www.coupons.com", ["/sitemap.xml"], r"^https://www\.coupons\.com/coupon-codes/[^/?#]+/?$", None),
    "retailmenot": ("https://www.retailmenot.com", ["/sitemap.xml"], r"^https://www\.retailmenot\.com/view/([^/?#]+\.[a-z.]+)/?$", 1),
    "groupon": ("https://www.groupon.com", ["/sitemap.xml"], r"^https://www\.groupon\.com/coupons/[a-z0-9-]+/?$", None),
    "promocodes_com": ("https://www.promocodes.com", ["/sitemap-stores.xml"], r"^https://www\.promocodes\.com/[^/?#]+-coupons/?$", None),
}


# Honey publishes no sitemap; its store pages link about 11 other stores each, so the walk starts from these and follows links.
SEEDS = {"honey": ["nike", "target", "amazon", "walmart", "bestbuy", "macys", "sephora", "ulta", "kohls", "wayfair", "adidas",
                   "lowes", "homedepot", "etsy", "chewy", "gap", "oldnavy", "nordstrom", "expedia", "hotels-com"]}
LINK_RX = re.compile(r'(?:https://www\.joinhoney\.com)?/shop/([a-z0-9][a-z0-9-]*)(?=["/?\\])')
NOT_STORE_SLUGS = {"share", "p"}
# CouponFollow's CDN answered 406 to 80 of 148 pages at 3 s apart (2026-11-08); it gets 6 s.
GAP_BY_SOURCE = {"couponfollow": 6.0}
MAX_REFUSALS = 10


# Sites refusing urllib's TLS fingerprint get curl_cffi's Safari one (egress grid, 2026-11-08: 403 to urllib, 200 to Safari's).
IMPERSONATE = {"simplycodes": "safari", "groupon": "safari", "retailmenot": "safari", "couponcabin": "safari"}
CLIENT = None
PROXY = None


def egress_proxy(name):
    import glob, os
    for f in glob.glob(os.path.expanduser("~/.cache/wb_broker/egresses.d/*")):
        for line in open(f):
            p = line.rstrip("\n").split("\t")
            if p and p[0] == name:
                return p[1]
    raise SystemExit(f"egress {name} not listed")


def get(url, timeout=45):
    if CLIENT:
        from curl_cffi import requests as creq
        try:
            r = creq.get(url, impersonate=CLIENT, timeout=timeout, proxies={"http": PROXY, "https": PROXY} if PROXY else None)
            data = r.content[:12_000_000]
            if data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)
            return r.status_code, data
        except Exception as e:
            return -1, str(e).encode()[:300]
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xml;q=0.9,*/*;q=0.8",
                                               "Accept-Language": "en-US,en;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(12_000_000)
            if url.endswith(".gz") or data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)
            return r.status, data
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return -1, str(e).encode()[:300]


def sitemap_pages(base, roots, pattern, gap, rp):
    """Walks the sitemap index breadth-first and returns the store-page URLs matching the pattern."""
    rx = re.compile(pattern)
    queue, seen, pages = [base + r for r in roots], set(), []
    while queue:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        time.sleep(gap)
        st, body = get(sm)
        if st != 200:
            print(f"sitemap {sm} status {st}", flush=True)
            continue
        xml = body.decode("utf-8", "replace")
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
        if "<sitemapindex" in xml:
            queue.extend(urllib.parse.unquote(l) if "%" not in l else l for l in locs)
        else:
            pages.extend(l for l in locs if rx.match(l))
    return sorted(set(pages))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=sorted(SOURCES))
    ap.add_argument("--gap", type=float, default=3.0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--list-only", action="store_true")
    ap.add_argument("--egress", default=None)
    ap.add_argument("--shard", default="0/1")
    ap.add_argument("--max-minutes", type=float, default=0, help="stop cleanly after this many minutes")
    a = ap.parse_args()
    base, roots, pattern, key_group = SOURCES[a.source]
    global CLIENT, PROXY
    CLIENT = IMPERSONATE.get(a.source)
    PROXY = egress_proxy(a.egress) if a.egress else None
    shard, nshard = map(int, a.shard.split("/"))

    con = sqlite3.connect(f"10_seed/output/seed_{a.source}" + (f"_s{shard}" if nshard > 1 else "") + ".sqlite")
    con.executescript("""
      create table if not exists store_pages (url text primary key, listed real);
      create table if not exists pages_done (url text primary key, status int, fetched real, n_codes int, store_key text);
      create table if not exists codes (store_key text, code text, description text, page_url text, seen text, extra text,
                                        primary key (store_key, code));
      create table if not exists selectors (store_key text, name text, value text, primary key (store_key, name));
    """)
    rp = urllib.robotparser.RobotFileParser()
    st, body = get(base + "/robots.txt")
    rp.parse(body.decode("utf-8", "replace").splitlines() if st == 200 else [])
    try:
        gap = max(a.gap, GAP_BY_SOURCE.get(a.source, 0), float(rp.crawl_delay("*") or 0))
    except AttributeError:
        gap = max(a.gap, GAP_BY_SOURCE.get(a.source, 0))

    first = f"10_seed/output/seed_{a.source}_s0.sqlite"
    if nshard > 1 and shard > 0 and not con.execute("select count(*) from store_pages").fetchone()[0] and __import__("os").path.exists(first):
        # Shards share shard 0's store list, since a sitemap fetched through a proxy can fail and leave a shard empty.
        con.executemany("insert or ignore into store_pages values (?, ?)", sqlite3.connect(first).execute("select url, listed from store_pages"))
        con.commit()
    if not con.execute("select count(*) from store_pages").fetchone()[0]:
        pages = sitemap_pages(base, roots, pattern, gap, rp)
        pages += [f"{base}/shop/{slug}" for slug in SEEDS.get(a.source, [])]
        con.executemany("insert or ignore into store_pages values (?, ?)", [(u, time.time()) for u in pages])
        con.commit()
    # A page answered with a refusal (403, 406, 429) or an error is retried on the next run.
    con.execute("delete from pages_done where status not in (200, 404, 410)")
    con.commit()
    import zlib
    todo = [u for (u,) in con.execute("select url from store_pages where url not in (select url from pages_done) order by url")
            if nshard == 1 or zlib.crc32(u.encode()) % nshard == shard]
    total = con.execute("select count(*) from store_pages").fetchone()[0]
    print(f"{a.source}: {total} store pages, {len(todo)} to fetch, gap {gap} s", flush=True)
    if a.list_only:
        return
    if a.limit:
        todo = todo[: a.limit]

    refusals = 0
    key_rx = re.compile(pattern)
    t_start = time.time()
    while todo:
        if a.max_minutes and time.time() - t_start > a.max_minutes * 60:
            break
        url = todo.pop(0)
        i = con.execute("select count(*) from pages_done").fetchone()[0]
        time.sleep(gap)
        st, body = get(url)
        if st in (403, 406, 429):
            # A refusal is left out of pages_done, so the next run retries it; ten in a row end this run.
            refusals += 1
            print(f"refused {st} at {url}", flush=True)
            if refusals >= MAX_REFUSALS:
                print(f"stopping: {MAX_REFUSALS} refusals in a row", flush=True)
                break
            time.sleep(30 * refusals)
            continue
        refusals = 0
        html = body.decode("utf-8", "replace") if st == 200 else ""
        key = extract.store_key(urllib.parse.unquote(key_rx.match(url).group(key_group))) if key_group else None
        res = extract.extract(html, a.source, key) if html else {"codes": [], "store_host": None, "selectors": {}}
        for rurl, _label in extract.reveals(html, a.source, base) if html else []:
            time.sleep(gap)
            rst, rbody = get(rurl)
            got = extract.reveal_code(a.source, rbody) if rst == 200 else None
            if got:
                res["codes"].append(got)
                if got.get("store_host") and not key:
                    key = extract.store_key(got["store_host"])
        if not key and res["store_host"] and a.source != "coupons_com":  # its pages link only affiliate and review hosts
            key = extract.store_key(res["store_host"])
        if not key:
            # The build step resolves "slug:<name>" against the store keys other sources give.
            key = "slug:" + re.sub(r"-coupons$", "", url.rstrip("/").rsplit("/", 1)[-1])
        day = time.strftime("%Y-%m-%d")
        if key:
            con.executemany("insert or replace into codes values (?,?,?,?,?,?)",
                            [(key, c["code"], c.get("description"), url, day, c.get("extra")) for c in res["codes"]])
            con.executemany("insert or replace into selectors values (?,?,?)", [(key, n, v) for n, v in res["selectors"].items()])
        con.execute("insert or replace into pages_done values (?,?,?,?,?)", (url, st, time.time(), len(res["codes"]), key))
        if a.source == "honey" and html:
            new = {f"{base}/shop/{m}" for m in LINK_RX.findall(extract.unescape(html)) if m not in NOT_STORE_SLUGS}
            have = {u for (u,) in con.execute("select url from store_pages")}
            fresh = sorted(new - have)
            con.executemany("insert or ignore into store_pages values (?, ?)", [(u, time.time()) for u in fresh])
            todo.extend(fresh)
        con.commit()
        if i % 200 == 0:
            n = con.execute("select count(*) from codes").fetchone()[0]
            print(f"{i + 1}/{len(todo)} pages; {n} codes stored", flush=True)
    n = con.execute("select count(*) from codes").fetchone()[0]
    left = len(todo)
    print(f"remaining {left}", flush=True)
    print(f"done: {n} codes stored from {con.execute('select count(*) from pages_done').fetchone()[0]} pages", flush=True)


if __name__ == "__main__":
    main()
