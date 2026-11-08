# Open tasks

- Choose the share endpoint (recommended: a Google Form or a small Cloudflare Worker writing to this repo's issues), then set `SHARE_ENDPOINT`.
- Publish the search page and the database (`DB_URL`) once Bryce approves; until then the repo and site stay private.
- Add a check of Firefox's `data_collection_permissions` value before any store submission, which waits for Bryce's approval.
- Commit the rebuilt `codes.json` once the harvests end (each harvest job rebuilds it on exit; PromoCodes, the longest at 20,496 pages, ends near 2026-11-09 13:00 ET).
