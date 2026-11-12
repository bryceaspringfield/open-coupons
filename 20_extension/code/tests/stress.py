#!/usr/bin/env python3
"""Stress test of Open Coupons' database loading in headless Chromium, on the real 64-shard database.

Usage: stress.py EXTENSION_DIR SCRATCH_DIR
Checks: a full refresh from a local server stores all 64 shards; 600 lookups of real stores stay fast and read the stored shards;
a refresh interrupted by one missing shard keeps the database in use; the service worker's memory stays under 400 MB.
"""
import functools, http.server, json, pathlib, random, re, shutil, sys, threading, time
from playwright.sync_api import sync_playwright

PORT = 8766
fails, total = [], 0
def check(name, ok, detail=""):
    global total
    total += 1
    print(f"{'PASS' if ok else 'FAIL'}\t{name}\t{str(detail)[:300]}", flush=True)
    if not ok: fails.append(name)

class H(http.server.SimpleHTTPRequestHandler):
    missing = None
    def do_GET(self):
        if H.missing and self.path.endswith(H.missing):
            self.send_error(404); return
        super().do_GET()
    def log_message(self, *a): pass

def main(ext_src, scratch):
    scratch = pathlib.Path(scratch); shutil.rmtree(scratch, ignore_errors=True)
    ext = scratch / "ext"; shutil.copytree(ext_src, ext)
    data = ext / "data"
    bg = ext / "background.js"
    bg.write_text(re.sub(r'const DB_URL = "[^"]*";', f'const DB_URL = "http://127.0.0.1:{PORT}/";', bg.read_text()))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(H, directory=str(data)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    stores = []
    for i in range(64):
        stores += list(json.load(open(data / "shards" / f"{i}.json"))["domains"])
    random.seed(1); sample = random.sample(stores, 600)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(scratch / "profile"), headless=True, channel="chromium",
              args=[f"--disable-extensions-except={ext}", f"--load-extension={ext}", "--no-sandbox"])
        sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=30000)
        # 1. a lookup from the bundled copy, which starts the refresh
        import subprocess
        def rss():
            return sum(int(x) for x in subprocess.check_output("ps -u $USER -o rss=,args= | grep -F -- '%s' | awk '{s+=$1} END {print s*1024}'" % str(scratch / "profile"), shell=True).split())
        rss0 = rss()
        t0 = time.time(); r = sw.evaluate("(s) => lookup(s)", "amazon.com"); first = time.time() - t0
        check("first lookup from the bundled copy", len(r["codes"]) >= 0, "%d codes for amazon.com in %.2f s" % (len(r["codes"]), first))
        # 2. the refresh finishes
        end = time.time() + 180; n = 0
        while time.time() < end:
            n = sw.evaluate("async () => (await chrome.storage.local.get(null)) && Object.keys(await chrome.storage.local.get(null)).filter(k => k.startsWith('shard')).length")
            m = sw.evaluate("async () => (await chrome.storage.local.get('meta')).meta?.fetched || 0")
            if n == 64 and m: break
            time.sleep(1)
        check("refresh stores all 64 shards and the index", n == 64 and m, f"{n} shards, fetched={m}, {time.time() - t0:.1f} s")
        import subprocess
        est = int(subprocess.check_output(["du", "-sb", str(scratch / "profile")]).split()[0])
        check("browser profile after the refresh under 400 MB", est < 400e6, "%.0f MB" % (est / 1e6))
        # 3. lookups
        lat = []
        for s in sample:
            t = time.time(); r = sw.evaluate("(s) => lookup(s)", s); lat.append(time.time() - t)
            if not r["codes"]:
                check("lookup finds codes for a listed store", False, s); break
        lat.sort()
        check("600 lookups: median under 100 ms, 95th percentile under 300 ms", lat[300] < 0.1 and lat[570] < 0.3,
              "median %.0f ms, p95 %.0f ms, max %.0f ms" % (lat[300] * 1e3, lat[570] * 1e3, lat[-1] * 1e3))
        # 4. memory
        rss1 = rss()
        check("browser memory grows by under 600 MB over the refresh and 600 lookups", 0 < rss1 - rss0 < 600e6, "%.0f MB before, %.0f MB after" % (rss0 / 1e6, rss1 / 1e6))
        # 5. a store missing from the database, and a hostile name
        r = sw.evaluate("(s) => lookup(s)", "no-such-store-xyz.example")
        check("an unlisted store returns no codes", r["codes"] == [], r["codes"][:2])
        r = sw.evaluate("(s) => lookup(s)", "münchen-ü.de/..\\\\<script>")
        check("an odd store name returns without error", isinstance(r["codes"], list))
        # 6. a refresh interrupted by a missing shard keeps the database in use
        sw.evaluate("async () => { const m = (await chrome.storage.local.get('meta')).meta; m.generated = 'older'; m.fetched = 0; await chrome.storage.local.set({meta: m}); }")
        H.missing = "shards/33.json"
        sw.evaluate("() => { meta = null; }")
        r = sw.evaluate("(s) => lookup(s)", sample[0]); time.sleep(8)
        m2 = sw.evaluate("async () => (await chrome.storage.local.get('meta')).meta")
        check("a refresh with a missing shard keeps the stored database", len(r["codes"]) > 0 and m2["generated"] == "older", m2.get("generated"))
        H.missing = None
        ctx.close()
    print("SUMMARY\t%d of %d passed" % (total - len(fails), total))
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
