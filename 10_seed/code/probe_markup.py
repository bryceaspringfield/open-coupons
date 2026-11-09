#!/usr/bin/env python3
"""For each stored store page: embedded JSON blobs (script ids, state globals) and contexts of code-like keys."""
import re, sqlite3, sys
con = sqlite3.connect(sys.argv[1])
for url, st, body in con.execute("select url, status, body from pages where status=200 and url not like '%robots%' and url not like '%terms%' order by url"):
    h = body.decode("utf-8", "replace")
    print(f"\n## {url}")
    ids = re.findall(r'<script[^>]*(?:id|type)="([^"]+)"[^>]*>', h)
    print("   scripts:", sorted(set(ids))[:12])
    print("   globals:", sorted(set(re.findall(r'window\.(__[A-Z_]+__|[A-Za-z_]*[Ss]tate[A-Za-z_]*)\s*=', h)))[:8])
    keys = re.findall(r'\\?"([A-Za-z_]*(?:[Cc]ode|[Cc]oupon)[A-Za-z_]*)\\?"\s*:\s*\\?"([^"\\]{0,40})', h)
    from collections import Counter
    c = Counter(k for k, v in keys)
    print("   keys:", c.most_common(10))
    for k, v in keys[:0]: pass
    samp = [(k, v) for k, v in keys if re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{3,24}", v)][:8]
    print("   samples:", samp)
    attrs = Counter(re.findall(r'(data-[a-z-]*code[a-z-]*)="', h))
    print("   attrs:", attrs.most_common(6))
