#!/usr/bin/env python3
"""End-to-end test of the extension in headless Chromium against the mock checkout pages; prints one line a test and a summary.

Usage: run_tests.py EXTENSION_DIR SCRATCH_DIR
The mock pages are served on 127.0.0.1, reached as woo.test, generic.test, and reload.test through a host-resolver rule.
"""
import functools
import http.server
import json
import pathlib
import shutil
import sys
import threading
import time

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
PORT = 8765
TEST_DB = {
    "generated": "test",
    "domains": {
        "woo.test": [{"c": c, "s": "test"} for c in ["SAVE10", "BADCODE", "SAVE20", "TAKE5"]],
        "generic.test": [{"c": c, "s": "test"} for c in ["NOPE", "TAKE5", "SAVE20", "SAVE10"]],
        "reload.test": [{"c": c, "s": "test"} for c in ["XX1", "SAVE10", "SAVE20"]],
    },
}
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}\t{name}\t{detail}", flush=True)


def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(HERE / "pages"))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()


def state(page):
    return page.evaluate("() => document.querySelector('[data-oc-state]')?.dataset.ocState || ''")


def wait_state(page, prefix, timeout=90):
    end = time.time() + timeout
    s = ""
    while time.time() < end:
        try:
            s = state(page)
        except Exception:
            s = ""  # the page is mid-navigation
        if s.startswith(prefix):
            return s
        time.sleep(0.25)
    return s


def try_now(ctx, sw):
    sw.evaluate("""async () => {
        const [tab] = await chrome.tabs.query({active: true});
        await chrome.tabs.sendMessage(tab.id, {action: 'tryNow'});
    }""")


def main(ext_src, scratch):
    scratch = pathlib.Path(scratch)
    ext = scratch / "ext"
    shutil.rmtree(scratch, ignore_errors=True)
    shutil.copytree(ext_src, ext)
    (ext / "data" / "codes.json").write_text(json.dumps(TEST_DB))
    serve()
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(scratch / "profile"), headless=True, channel="chromium",
            args=[f"--disable-extensions-except={ext}", f"--load-extension={ext}",
                  f"--host-resolver-rules=MAP *.test 127.0.0.1", "--no-sandbox"])
        sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=30000)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        # Unit checks of the two helpers, loaded into a blank page.
        page.goto(f"http://woo.test:{PORT}/shared.js")
        for f in ["lib/domains.js", "lib/platforms.js"]:
            page.add_script_tag(path=str(ext / f))
        keys = page.evaluate("""() => ['www.amazon.com','shop.example.co.uk','nordcheckout.com','a.b.c.target.com']
            .map(OC_DOMAINS.storeKey)""")
        check("storeKey", keys == ["amazon.com", "example.co.uk", "nordvpn.com", "target.com"], keys)
        amts = page.evaluate("""() => ['$1,234.56','1.234,56 €','£60.00','Total: USD 80','12,5 €','no amount']
            .map(OC_PLATFORMS.parseAmount)""")
        check("parseAmount", amts == [1234.56, 1234.56, 60, 80, 12.5, None], amts)

        cases = [("woo", "woo.html", "SAVE20", "64.00"), ("generic", "generic.html", "SAVE20", "96.00"),
                 ("reload", "reload.html", "SAVE20", "48.00")]
        for name, path, want_code, want_total in cases:
            page.goto(f"http://{name}.test:{PORT}/{path}")
            s = wait_state(page, "offer", 20)
            check(f"{name}: offer shown", s == "offer", s)
            t0 = time.time()
            try_now(ctx, sw)
            s = wait_state(page, "done:", 120)
            applied = page.evaluate("() => document.body.dataset.applied")
            total_text = page.inner_text("body")
            check(f"{name}: best code applied", s == f"done:{want_code}" and applied == want_code,
                  f"state={s} applied={applied} seconds={time.time() - t0:.1f}")
            check(f"{name}: total shown", want_total in total_text, want_total)

        # A code the user types which works and is missing from the database: the share prompt appears.
        page.goto(f"http://woo.test:{PORT}/woo.html")
        wait_state(page, "offer", 20)
        page.fill("input[name=coupon_code]", "SECRET15")
        page.click("button[name=apply_coupon]")
        s = wait_state(page, "share:", 15)
        check("manual code: share prompt", s == "share:SECRET15", s)
        r = sw.evaluate("""() => new Promise(res => chrome.storage.local.get(['shareQueue'], g => res(g.shareQueue || [])))""")
        check("manual code: nothing queued before consent", r == [], r)
        page.fill("input[name=coupon_code]", "SAVE10")
        page.click("button[name=apply_coupon]")
        time.sleep(3)
        s = state(page)
        check("known code: no share prompt", not s.startswith("share:SAVE10"), s)

        check("no page errors", not errors, errors[:3])
        ctx.close()
    print(f"SUMMARY\t{sum(results)} of {len(results)} passed")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
