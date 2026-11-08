# Open tasks

- Test in Firefox (load `extension/` from about:debugging); the automated test covers Chromium only.
- Choose the share endpoint (recommended: a Google Form or a small Cloudflare Worker writing to this repo's issues), then set `SHARE_ENDPOINT`.
- Publish the search page and the database (`DB_URL`) once Bryce approves; until then the repo and site stay private.
- Add a check of Firefox's `data_collection_permissions` value before any store submission, which waits for Bryce's approval.
