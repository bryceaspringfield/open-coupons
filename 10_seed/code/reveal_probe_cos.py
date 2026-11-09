#!/usr/bin/env python3
"""Clicks Capital One Shopping's first code button (forced past overlays) and prints its requests and any revealed code."""
import time
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = b.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36")
    log = []
    def on_resp(r):
        if "capitaloneshopping" in r.url and r.request.resource_type in ("xhr", "fetch", "document"):
            try: body = r.text()[:400].replace("\n", " ")
            except Exception: body = ""
            log.append(f"{r.request.method} {r.status} {r.url[:200]} :: {body}")
    ctx.on("response", on_resp)
    page = ctx.new_page()
    page.goto("https://capitaloneshopping.com/s/nike.com/coupon", wait_until="domcontentloaded", timeout=60000)
    time.sleep(4)
    btns = page.locator("button")
    texts = [t.strip()[:40] for t in btns.all_inner_texts()]
    print("buttons:", [t for t in texts if t][:30])
    n0 = len(log)
    target = page.locator("button", has_text="Code").first
    print("outer:", target.evaluate("e => e.outerHTML.slice(0, 600)"))
    try:
        target.click(force=True, timeout=8000)
    except Exception as e:
        print("click err", str(e)[:200])
    time.sleep(6)
    for pg in ctx.pages:
        print("page:", pg.url[:200])
        print("dialog text:", [t[:200] for t in pg.locator("[role=dialog], dialog, [class*=modal]").all_inner_texts()][:3])
    for l in log[n0:]: print("  ", l)
    b.close()
