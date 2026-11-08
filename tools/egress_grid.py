#!/usr/bin/env python3
"""Tests each blocked coupon site through every egress the broker lists, with three clients, and prints one table row a cell.

Usage: egress_grid.py OUT.tsv
Egresses: the node's own address ("direct") and each line of ~/.cache/wb_broker/egresses.d/* (name, proxy URL, exit IP, kind).
Clients: curl_cffi with no impersonation, with Safari's TLS fingerprint, and with Chrome's. Each egress runs in its own
thread; within an egress, requests go 2 s apart. A cell passes when the page answers 200 with no challenge page.
"""
import concurrent.futures as cf
import glob
import os
import re
import sys
import time

from curl_cffi import requests as creq

SITES = {
    "retailmenot": "https://www.retailmenot.com/view/nike.com",
    "dealspotr": "https://dealspotr.com/promo-codes/nike.com",
    "knoji": "https://nike.knoji.com/promo-codes/",
    "simplycodes": "https://simplycodes.com/store/nike.com",
    "couponcabin": "https://www.couponcabin.com/coupons/nike/",
    "groupon": "https://www.groupon.com/coupons/nike",
}
CLIENTS = [None, "safari", "chrome"]
UA = {None: "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"}
CHALLENGE = re.compile(r"just a moment|cf-chl|captcha|access denied|are you a robot|px-captcha|datadome|request blocked|verify you are human", re.I)
GAP = 2.0


def egresses():
    out = [("direct", None, "node", "nat")]
    for f in sorted(glob.glob(os.path.expanduser("~/.cache/wb_broker/egresses.d/*"))):
        for line in open(f):
            p = line.rstrip("\n").split("\t")
            if len(p) >= 4 and p[1].startswith("http"):
                out.append((p[0], p[1], p[2], p[3]))
    return out


def one(egress):
    name, proxy, ip, kind = egress
    rows = []
    for site, url in SITES.items():
        for client in CLIENTS:
            time.sleep(GAP)
            t0 = time.time()
            try:
                kw = {"impersonate": client} if client else {"headers": {"User-Agent": UA[None]}}
                r = creq.get(url, proxies={"http": proxy, "https": proxy} if proxy else None, timeout=30, **kw)
                body = r.text[:400000]
                chal = bool(CHALLENGE.search(body[:60000])) or r.headers.get("cf-mitigated") == "challenge"
                verdict = "PASS" if r.status_code == 200 and not chal and len(body) > 20000 else "fail"
                rows.append((site, name, kind, ip, client or "plain", r.status_code, len(body), int(chal), verdict, round(time.time() - t0, 1)))
            except Exception as e:
                rows.append((site, name, kind, ip, client or "plain", f"ERR {type(e).__name__}", 0, 0, "fail", round(time.time() - t0, 1)))
    return rows


def main(out):
    eg = egresses()
    with open(out, "w") as f:
        f.write("site\tegress\tkind\tip\tclient\tstatus\tbytes\tchallenge\tverdict\tseconds\n")
        with cf.ThreadPoolExecutor(len(eg)) as ex:  # one thread an egress; each egress stays serial at GAP
            for rows in ex.map(one, eg):
                for r in rows:
                    f.write("\t".join(map(str, r)) + "\n")
                f.flush()
    import collections
    rows = [l.rstrip("\n").split("\t") for l in open(out)][1:]
    print(f"{len(eg)} egresses, {len(rows)} cells")
    for site in SITES:
        cells = [r for r in rows if r[0] == site]
        passed = [r for r in cells if r[8] == "PASS"]
        print(f"{site}: {len(passed)} of {len(cells)} cells pass; statuses {collections.Counter(r[5] for r in cells).most_common(4)}")
        for r in passed[:6]:
            print(f"    pass: {r[1]} ({r[2]}) {r[4]} {r[6]} bytes")


if __name__ == "__main__":
    main(sys.argv[1])
