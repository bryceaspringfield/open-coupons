#!/usr/bin/env python3
"""Merges 10_seed/output/seed_<source>.sqlite (and 10_seed/output/shared_codes.tsv, the codes users chose to share) into one code database.

Writes data/index.json and data/shards/<n>.json under 20_extension/code/extension/ (bundled with the extension) and 99_overall/writeup/site/ (read by the search page and the daily refresh), and
prints one line of counts per source. A store page known only by its slug ("slug:nike") takes the one store key from another
source whose first label is that slug (nike -> nike.com), else <slug>.com; a slug matching several keys is dropped. Codes past their expiry date are dropped.
"""
import collections
import datetime
import glob
import json
import os
import re
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCE_URLS = {
    "honey": "https://www.joinhoney.com",
    "capital_one_shopping": "https://capitaloneshopping.com",
    "coupons_com": "https://www.coupons.com",
    "promocodes_com": "https://www.promocodes.com",
    "simplycodes": "https://simplycodes.com",
    "retailmenot": "https://www.retailmenot.com",
    "groupon": "https://www.groupon.com/coupons",
    "couponfollow": "https://couponfollow.com",
    "shared": "codes users of the extension chose to share",
}


HONEY_SEL = {"pns_siteSelCartCodeBox": "input", "pns_siteSelCartCodeSubmit": "apply", "pns_siteSelCartTotalPrice": "total"}
JQUERY_ONLY = re.compile(r":(contains|eq|gt|lt|first|last|even|odd|hidden|checkbox|text|button|input|selected|animated|header)\b")


def css_only(sel):
    """Keeps the parts of a jQuery selector list which are plain CSS; strips :visible, which the extension checks itself."""
    parts, depth, cur = [], 0, ""
    for ch in sel:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            parts.append(cur); cur = ""
        else:
            cur += ch
    parts.append(cur)
    keep = [p.replace(":visible", "").strip() for p in parts]
    keep = [p for p in keep if p and not JQUERY_ONLY.search(p)]
    return ", ".join(keep) or None


def selectors():
    """Store -> {input, apply, total}, from the selectors Honey publishes on its store pages."""
    out = collections.defaultdict(dict)
    path = os.path.join(ROOT, "10_seed", "output", "seed_honey.sqlite")
    if os.path.exists(path):
        for key, name, value in sqlite3.connect(path).execute("select store_key, name, value from selectors"):
            v = css_only(value) if name in HONEY_SEL else None
            if v:
                out[key][HONEY_SEL[name]] = v
    return {k: v for k, v in out.items() if "input" in v}


N_SHARDS = 64  # 2026-11-09: 75 MB over 64 files is about 1.2 MB a file, which a browser parses in about 10 ms


def shard_of(domain):
    """FNV-1a (32 bits) of the domain's UTF-8 bytes, modulo N_SHARDS; background.js and the search page compute the same."""
    h = 0x811C9DC5
    for b in domain.encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h % N_SHARDS


def main():
    today = datetime.date.today().isoformat()
    rows, stats = [], collections.Counter()
    for path in sorted(glob.glob(os.path.join(ROOT, "10_seed", "output", "seed_*.sqlite"))):
        src = re.match(r"seed_(.+?)(?:_r\d+)?(?:_s\d+)?\.sqlite", os.path.basename(path)).group(1)
        con = sqlite3.connect(path)
        for key, code, desc, page, seen, extra in con.execute("select store_key, code, description, page_url, seen, extra from codes"):
            exp = re.search(r"expires=(\d{4}-\d{2}-\d{2})", extra or "")
            if exp and exp.group(1) < today:
                stats[src, "expired"] += 1
                continue
            rows.append((src, key, code, desc, seen))
        con.close()
    shared = os.path.join(ROOT, "10_seed", "output", "shared_codes.tsv")
    if os.path.exists(shared):
        for line in open(shared):
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 3 and not line.startswith("#"):
                rows.append(("shared", parts[0].lower(), parts[1], None, parts[2]))

    keys = {k for _, k, *_ in rows if not k.startswith("slug:")}
    by_label = collections.defaultdict(set)
    for k in keys:
        by_label[k.split(".")[0]].add(k)

    stores = collections.defaultdict(dict)  # store -> CODE (upper) -> record
    for src, key, code, desc, seen in rows:
        if key.startswith("slug:"):
            cands = by_label.get(key[5:].replace("-", ""), set()) | by_label.get(key[5:], set())
            if len(cands) == 1:
                key = next(iter(cands))
            elif not cands:
                # No other source names the store: take <slug>.com, since a wrong guess only means its codes fail at checkout.
                key = key[5:].replace("-", "") + ".com"
                stats[src, "slug guessed .com"] += 1
            else:
                stats[src, "slug ambiguous"] += 1
                continue
        rec = stores[key].setdefault(code.upper(), {"c": code, "d": None, "s": [], "seen": seen})
        if src not in rec["s"]:
            rec["s"].append(src)
        rec["d"] = rec["d"] or desc
        rec["seen"] = max(rec["seen"] or "", seen or "")
        stats[src, "kept"] += 1

    domains = {}
    for key in sorted(stores):
        recs = list(stores[key].values())
        recs.sort(key=lambda r: (len(r["s"]), r["seen"] or ""), reverse=True)  # codes listed by more sources first, then the newest
        domains[key] = [{k: v for k, v in r.items() if v} for r in recs]
    n_codes = sum(len(v) for v in domains.values())
    sel = selectors()
    db = {"generated": today, "stores": len(domains), "codes": n_codes,
          "sources": {s: SOURCE_URLS.get(s, s) for s in sorted({r[0] for r in rows})}, "domains": domains,
          "selectors": {k: v for k, v in sel.items() if k in domains}}
    # The database is cut into N_SHARDS files by a hash of the store's domain, so the extension parses one small file a lookup.
    meta = {k: v for k, v in db.items() if k not in ("domains", "selectors")}
    meta["shards"] = N_SHARDS
    parts = [{"domains": {}, "selectors": {}} for _ in range(N_SHARDS)]
    for key, recs in domains.items():
        parts[shard_of(key)]["domains"][key] = recs
    for key, v in db["selectors"].items():
        parts[shard_of(key)]["selectors"][key] = v
    size = 0
    for out in ("20_extension/code/extension/data", "99_overall/writeup/site/data"):
        d = os.path.join(ROOT, out)
        os.makedirs(os.path.join(d, "shards"), exist_ok=True)
        for name, obj in [("index.json", meta)] + [(f"shards/{i}.json", part) for i, part in enumerate(parts)]:
            p = os.path.join(d, name)
            tmp = f"{p}.{os.getpid()}.tmp"  # one name per process, since harvest shards ending together run build_db at once
            with open(tmp, "w") as f:
                json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)
            if os.path.getsize(tmp) > 0:
                size += os.path.getsize(tmp)
                os.replace(tmp, p)
    for src in sorted({s for s, _ in stats}):
        print(src, {k: v for (s, k), v in stats.items() if s == src})
    print(f"selectors for {len(db['selectors'])} stores")
    print(f"database: {len(domains)} stores, {n_codes} codes, {size // 2} bytes in {N_SHARDS} shards")


if __name__ == "__main__":
    main()
