#!/usr/bin/env python3
"""Headed Chromium (run under xvfb-run) with the bypass skill's stealth patches registered before any page script.
For each site: waits out the bot check, clicks the first code button, and prints the requests, pages, and code-like text."""
import os, re, sqlite3, time
from playwright.sync_api import sync_playwright

src = open(os.path.expanduser("~/.claude/skills/efficiency/bypass/scripts/stealth-inject.mjs")).read()
arr = src[src.index("STEALTH_SCRIPTS"):src.index("export async function")]
PATCHES = "\n".join(f"try {{ {s} }} catch (e) {{}}" for s in re.findall(r"`([\s\S]*?)`", arr))
PAGES = {"groupon": "https://www.groupon.com/coupons/nike", "retailmenot": "https://www.retailmenot.com/view/nike.com",
         "couponcabin": "https://www.couponcabin.com/coupons/nike/"}
BTN = re.compile(r"^\s*(get|show|reveal|see)\s+(promo\s+)?code", re.I)
BLOCK = re.compile(r"just a moment|un momento|access restricted|attention required", re.I)
out = sqlite3.connect("10_seed/output/sample2_pages.sqlite")
print("stealth patches:", PATCHES.count("try {"))
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(f"/tmp/coupons_probe_{os.getpid()}", headless=False, channel="chromium",
        viewport={"width": 1366, "height": 900}, locale="en-US", args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
    ctx.add_init_script(PATCHES)
    for name, url in PAGES.items():
        log = []
        host = url.split("/")[2].split(".")[-2]
        def on_resp(r, log=log, host=host):
            if host in r.url and r.request.resource_type in ("xhr", "fetch"):
                try: body = r.text()[:400].replace("\n", " ")
                except Exception: body = ""
                log.append(f"{r.request.method} {r.status} {r.url[:200]} :: {body}")
        ctx.on("response", on_resp)
        page = ctx.new_page()
        print(f"\n## {name}", flush=True)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            for _ in range(30):
                if not BLOCK.search(page.title()): break
                time.sleep(1)
            print("title:", page.title()[:90])
            if BLOCK.search(page.title()):
                ctx.remove_listener("response", on_resp); page.close(); continue
            n0 = len(log)
            page.get_by_text(BTN).first.click(timeout=15000)
            time.sleep(8)
            for pg in ctx.pages:
                try:
                    h = pg.content()
                    out.execute("insert or replace into pages values (?,?,?,?)", (f"probe3:{name}:{pg.url}", 200, time.time(), h.encode()))
                    out.commit()
                    txt = pg.inner_text("body")
                    print("page:", pg.url[:160], "| code-like:", re.findall(r"\b[A-Z][A-Z0-9]{3,19}\b", txt[:60000])[:12])
                except Exception as e:
                    print("page err", pg.url[:120], str(e)[:100])
            for l in log[n0:][:15]: print("  ", l)
        except Exception as e:
            print("ERR", type(e).__name__, str(e)[:250])
        ctx.remove_listener("response", on_resp)
        for pg in ctx.pages[1:]: pg.close()
    ctx.close()
