#!/usr/bin/env python3
"""Prints, for each stored page: status, size, scraping-related sentences of terms pages, and code-like markup of store pages."""
import re, sqlite3, sys
con = sqlite3.connect(sys.argv[1])
TERMS = re.compile(r"[^.]{0,250}\b(scrap\w*|crawl\w*|robots?\b|spider\w*|automated (means|systems?|tools?|devices?|process\w*)|data mining|harvest\w*|systematic\w*)\b[^.]{0,250}\.", re.I)
CODE_HINTS = re.compile(r'(data-code="[^"]{2,30}"|"code"\s*:\s*"[^"]{2,30}"|"couponCode"\s*:\s*"[^"]{2,30}"|"promoCode"\s*:\s*"[^"]{2,30}"|data-clipboard-text="[^"]{2,30}"|"offerCode"\s*:\s*"[^"]{2,30}")')
for url, st, body in con.execute("select url, status, body from pages order by url"):
    html = (body or b"").decode("utf-8", "replace")
    text = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)))
    print(f"\n## {st} {len(html):>8} {url}")
    if "robots.txt" in url:
        print("   ", " | ".join(l for l in html.splitlines() if re.match(r"(?i)(user-agent|disallow|crawl-delay)", l))[:400]); continue
    if re.search(r"terms|legal", url):
        hits = sorted({m.group(0).strip() for m in TERMS.finditer(text)})
        for h in hits[:5]: print("   T:", h[:330])
        if not hits: print("   T: no scraping clause found; text chars", len(text))
        continue
    hints = CODE_HINTS.findall(html)
    print("   codes:", len(hints), [h[0][:50] for h in hints[:6]])
    print("   title:", (re.search(r"(?is)<title>(.*?)</title>", html) or [None, ""])[1][:100].strip())
