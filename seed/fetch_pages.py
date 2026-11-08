#!/usr/bin/env python3
"""Fetch a list of URLs into one SQLite file (table pages: url, status, fetched, body), politely.

Usage: fetch_pages.py URLS.txt OUT.sqlite [--gap SECONDS]
Hosts run in parallel; each host gets one request at a time, GAP seconds apart (or its robots.txt crawl delay, if longer).
A URL already stored with status 200 is skipped. A host answering 403 or 429 twice is dropped for the run.
"""
import argparse
import concurrent.futures as cf
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from collections import defaultdict

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
lock = threading.Lock()


def get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
                                               "Accept-Language": "en-US,en;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(8_000_000)
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return -1, str(e).encode()[:300]


def host_worker(host, urls, db_path, gap):
    con = sqlite3.connect(db_path, timeout=60)
    base = f"https://{host}"
    rp = urllib.robotparser.RobotFileParser()
    st, body = get(base + "/robots.txt")
    rp.parse(body.decode("utf-8", "replace").splitlines() if st == 200 else [])
    try:
        delay = rp.crawl_delay("*") or 0
    except AttributeError:
        delay = 0
    wait = max(gap, float(delay))
    refusals = done = 0
    for url in urls:
        if st == 200 and not rp.can_fetch("*", url):
            with lock:
                con.execute("insert or replace into pages values (?,?,?,?)", (url, -2, time.time(), b"robots.txt disallows"))
                con.commit()
            continue
        time.sleep(wait)
        code, data = get(url)
        with lock:
            con.execute("insert or replace into pages values (?,?,?,?)", (url, code, time.time(), data))
            con.commit()
        done += 1
        if code in (403, 429):
            refusals += 1
            if refusals >= 2:
                break
    con.close()
    return host, done, refusals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("urls")
    ap.add_argument("out")
    ap.add_argument("--gap", type=float, default=3.0)
    a = ap.parse_args()
    con = sqlite3.connect(a.out)
    con.execute("create table if not exists pages (url text primary key, status int, fetched real, body blob)")
    have = {u for (u,) in con.execute("select url from pages where status = 200")}
    con.close()
    by_host = defaultdict(list)
    for line in open(a.urls):
        u = line.strip()
        if u and not u.startswith("#") and u not in have:
            by_host[urllib.parse.urlsplit(u).netloc].append(u)
    with cf.ThreadPoolExecutor(max(1, len(by_host))) as ex:  # one thread a host; each host stays serial at its gap
        for host, done, ref in ex.map(lambda kv: host_worker(kv[0], kv[1], a.out, a.gap), by_host.items()):
            print(f"{host}\tfetched={done}\trefusals={ref}", flush=True)


if __name__ == "__main__":
    main()
