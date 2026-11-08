#!/usr/bin/env python3
"""Harvest the coupon codes a source publishes on its store pages, into data/seed_<source>.sqlite.

Usage: harvest.py SOURCE [--gap S] [--limit N] [--list-only]
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
    "capital_one_shopping": ("https://capitaloneshopping.com", ["/sitemap.xml"], r"^https://capitaloneshopping\.com/s/([^/?#]+\.[a-z.]+)/coupon/?$", 1),
    # CouponFollow is left out: its pages show 3 characters of each code, and robots.txt disallows the reveal path (/code/go/).
    "coupons_com": ("https://www.coupons.com", ["/sitemap.xml"], r"^https://www\.coupons\.com/coupon-codes/[^/?#]+/?$", None),
    "promocodes_com": ("https://www.promocodes.com", ["/sitemap-stores.xml"], r"^https://www\.promocodes\.com/[^/?#]+-coupons/?$", None),
}


def get(url, timeout=45):
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
            pages.extend(l for l in locs if rx.match(l) and rp.can_fetch("*", l))
    return sorted(set(pages))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=sorted(SOURCES))
    ap.add_argument("--gap", type=float, default=3.0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--list-only", action="store_true")
    a = ap.parse_args()
    base, roots, pattern, key_group = SOURCES[a.source]

    con = sqlite3.connect(f"data/seed_{a.source}.sqlite")
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
        gap = max(a.gap, float(rp.crawl_delay("*") or 0))
    except AttributeError:
        gap = a.gap

    if not con.execute("select count(*) from store_pages").fetchone()[0]:
        pages = sitemap_pages(base, roots, pattern, gap, rp)
        con.executemany("insert or ignore into store_pages values (?, ?)", [(u, time.time()) for u in pages])
        con.commit()
    todo = [u for (u,) in con.execute("select url from store_pages where url not in (select url from pages_done) order by url")]
    total = con.execute("select count(*) from store_pages").fetchone()[0]
    print(f"{a.source}: {total} store pages, {len(todo)} to fetch, gap {gap} s", flush=True)
    if a.list_only:
        return
    if a.limit:
        todo = todo[: a.limit]

    refusals = 0
    key_rx = re.compile(pattern)
    for i, url in enumerate(todo):
        time.sleep(gap)
        st, body = get(url)
        if st in (403, 429):
            refusals += 1
            print(f"refused {st} at {url}", flush=True)
            if refusals >= 3:
                print("stopping: three refusals", flush=True)
                break
            time.sleep(60 * refusals)
            continue
        refusals = 0
        html = body.decode("utf-8", "replace") if st == 200 else ""
        res = extract.extract(html, a.source) if html else {"codes": [], "store_host": None, "selectors": {}}
        key = None
        if key_group:
            key = extract.store_key(urllib.parse.unquote(key_rx.match(url).group(key_group)))
        elif res["store_host"] and a.source != "coupons_com":  # its pages link only affiliate and review hosts
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
        con.commit()
        if i % 200 == 0:
            n = con.execute("select count(*) from codes").fetchone()[0]
            print(f"{i + 1}/{len(todo)} pages; {n} codes stored", flush=True)
    n = con.execute("select count(*) from codes").fetchone()[0]
    print(f"done: {n} codes stored from {con.execute('select count(*) from pages_done').fetchone()[0]} pages", flush=True)


if __name__ == "__main__":
    main()
