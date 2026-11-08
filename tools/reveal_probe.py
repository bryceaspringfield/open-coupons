#!/usr/bin/env python3
"""Opens a store page, clicks its first code button, and prints each same-site request with a short response sample."""
import sys, time
from playwright.sync_api import sync_playwright

PAGES = {
    "couponfollow": ("https://couponfollow.com/site/nike.com", "article[data-has-code='true'] button, article[data-has-code='true'] [role=button], article[data-has-code='true'] a"),
    "capital_one_shopping": ("https://capitaloneshopping.com/s/nike.com/coupon", "button:has-text('Code'), button:has-text('code'), a:has-text('Code')"),
}
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox"])
    for name, (url, sel) in PAGES.items():
        ctx = b.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36")
        page = ctx.new_page()
        host = url.split("/")[2]
        log = []
        def on_resp(r, log=log, host=host):
            if host.split(".")[-2] in r.url and r.request.resource_type in ("xhr", "fetch", "document"):
                try: body = r.text()[:300].replace("\n", " ")
                except Exception: body = ""
                log.append(f"{r.request.method} {r.status} {r.url[:160]} :: {body}")
        page.on("response", on_resp)
        print(f"## {name}", flush=True)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)
            n0 = len(log)
            els = page.locator(sel)
            print("buttons:", els.count())
            if els.count():
                with ctx.expect_page(timeout=8000) as newp:
                    els.first.click(timeout=8000)
                np_ = newp.value
                np_.on("response", on_resp)
                time.sleep(5)
                print("new page:", np_.url[:200])
                for f in [np_, page]:
                    try: print("code-like text:", f.locator("[data-code], .code, [class*=code]").all_inner_texts()[:8])
                    except Exception as e: print("text err", e)
            for l in log[n0:]: print("  ", l)
        except Exception as e:
            print("ERR", type(e).__name__, str(e)[:200])
            for l in log[-10:]: print("  ", l)
        ctx.close()
    b.close()
