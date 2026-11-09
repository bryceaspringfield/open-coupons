#!/usr/bin/env python3
"""End-to-end test of the extension in Firefox (Playwright's build), installed as a temporary add-on through Firefox's
remote debugging protocol. Runs the three mock checkouts (started through the .test autorun) and the share prompt.

Usage: run_firefox.py EXTENSION_DIR SCRATCH_DIR
"""
import json
import pathlib
import re
import shutil
import socket
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from run_tests import PORT, TEST_DB, check, results, serve, state, wait_state  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

RDP_PORT = 6123


def rdp_install(path):
    """Installs a temporary add-on: getRoot, then installTemporaryAddon on the addons actor (length-prefixed JSON packets)."""
    s = socket.create_connection(("127.0.0.1", RDP_PORT), timeout=20)
    buf = b""

    def recv():
        nonlocal buf
        while True:
            if b":" in buf:
                n, rest = buf.split(b":", 1)
                if len(rest) >= int(n):
                    pkt, buf = rest[: int(n)], rest[int(n):]
                    return json.loads(pkt)
            buf += s.recv(65536)

    def send(obj):
        d = json.dumps(obj).encode()
        s.sendall(str(len(d)).encode() + b":" + d)

    recv()  # the server's greeting
    send({"to": "root", "type": "getRoot"})
    root = recv()
    while "addonsActor" not in root:
        root = recv()
    send({"to": root["addonsActor"], "type": "installTemporaryAddon", "addonPath": str(path)})
    reply = recv()
    s.close()
    return reply


def main(ext_src, scratch):
    scratch = pathlib.Path(scratch)
    shutil.rmtree(scratch, ignore_errors=True)
    ext = scratch / "ext"
    shutil.copytree(ext_src, ext)
    # The test database: every shard file holds the three test stores, so the lookup finds them whichever shard a store hashes to.
    # No refresh during a test: the published database must not replace the test stores.
    bg = ext / "background.js"
    bg.write_text(re.sub(r'const DB_URL = "[^"]*";', 'const DB_URL = "";', bg.read_text()))
    shutil.rmtree(ext / "data", ignore_errors=True)
    (ext / "data" / "shards").mkdir(parents=True)
    (ext / "data" / "index.json").write_text(json.dumps({"generated": "test", "stores": 3, "codes": 11, "shards": 64}))
    for i in range(64):
        (ext / "data" / "shards" / f"{i}.json").write_text(json.dumps(TEST_DB))
    serve()
    prefs = {"devtools.debugger.remote-enabled": True, "devtools.chrome.enabled": True,
             "devtools.debugger.prompt-connection": False, "xpinstall.signatures.required": False,
             "network.dns.localDomains": "woo.test,generic.test,reload.test",
             "extensions.webextensions.restrictedDomains": ""}
    with sync_playwright() as p:
        ctx = p.firefox.launch_persistent_context(str(scratch / "profile"), headless=True, firefox_user_prefs=prefs,
                                                  args=["-start-debugger-server", str(RDP_PORT)])
        time.sleep(2)
        reply = rdp_install(ext)
        check("firefox: add-on installed", "addon" in reply, str(reply)[:200])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        cases = [("woo", "woo.html", "SAVE20", "64.00"), ("generic", "generic.html", "SAVE20", "96.00"),
                 ("reload", "reload.html", "SAVE20", "48.00")]
        for name, path, want_code, want_total in cases:
            t0 = time.time()
            page.goto(f"http://{name}.test:{PORT}/{path}#oc-autorun")
            s = wait_state(page, "done:", 120)
            applied = page.evaluate("() => document.body.dataset.applied")
            check(f"firefox {name}: best code applied", s == f"done:{want_code}" and applied == want_code,
                  f"state={s} applied={applied} seconds={time.time() - t0:.1f}")
            check(f"firefox {name}: total shown", want_total in page.inner_text("body"), want_total)
        page.goto(f"http://woo.test:{PORT}/woo.html")
        wait_state(page, "offer", 20)
        page.fill("input[name=coupon_code]", "SECRET15")
        page.click("button[name=apply_coupon]")
        s = wait_state(page, "share:", 15)
        check("firefox manual code: share prompt", s == "share:SECRET15", s)
        check("firefox: no page errors", not errors, errors[:3])
        ctx.close()
    print(f"SUMMARY\t{sum(results)} of {len(results)} passed")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
