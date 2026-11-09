#!/usr/bin/env python3
"""Clicks the first code button on each site and prints its script requests, new pages, and the text near the code."""
import re, time
from playwright.sync_api import sync_playwright
PAGES = {
    "groupon": "https://www.groupon.com/coupons/nike",
    "retailmenot": "https://www.retailmenot.com/view/nike.com",
    "couponcabin": "https://www.couponcabin.com/coupons/nike/",
}
BTN = re.compile(r"^\s*(get|show|reveal|see)\s+(promo\s+)?code", re.I)
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, channel="chromium", args=["--no-sandbox"])
    for name, url in PAGES.items():
        ctx = b.new_context(viewport={"width": 1366, "height": 900})
        log = []
        host = url.split("/")[2].split(".")[-2]
        def on_resp(r, log=log, host=host):
            if host in r.url and r.request.resource_type in ("xhr", "fetch", "document"):
                try: body = r.text()[:500].replace("\n", " ")
                except Exception: body = ""
                log.append(f"{r.request.method} {r.status} {r.url[:220]} :: {body}")
        ctx.on("response", on_resp)
        page = ctx.new_page()
        print(f"\n## {name}", flush=True)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
            print("title:", page.title()[:100])
            n0 = len(log)
            btn = page.get_by_text(BTN).first
            print("button:", btn.evaluate("e => e.outerHTML.slice(0, 400)"))
            btn.click(timeout=10000)
            time.sleep(7)
            for pg in ctx.pages:
                txt = pg.inner_text("body")[:200000]
                hits = re.findall(r"(?i)(?:code|copy)[^\n]{0,15}\n?\s*([A-Z0-9][A-Z0-9_-]{3,24})\b", txt)
                print("page:", pg.url[:200], "| code-like:", hits[:8])
                for sel in ["[class*=code i]", "[data-qa*=code i]", "input[readonly]", "[class*=Code]"]:
                    try:
                        t = [x.strip()[:40] for x in pg.locator(sel).all_inner_texts() if x.strip()][:6]
                        v = [pg.locator(sel).nth(i).input_value() for i in range(min(3, pg.locator(sel).count()))] if sel.startswith("input") else []
                        if t or v: print("   ", sel, t, v)
                    except Exception: pass
            for l in log[n0:][:25]: print("  ", l)
        except Exception as e:
            print("ERR", type(e).__name__, str(e)[:300])
            for l in log[-8:]: print("  ", l)
        ctx.close()
    b.close()
