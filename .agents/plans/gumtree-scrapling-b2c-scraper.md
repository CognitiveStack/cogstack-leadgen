# Feature: Gumtree B2C Scraper — Scrapling StealthyFetcher

The following plan should be complete, but validate documentation and codebase patterns before implementing.

Pay special attention to the output JSON schema — it must be drop-in compatible with the existing `gumtree-leads-YYYY-MM-DD.json` format consumed by `b2c_run.py` on bigtorig.

## Feature Description

Replace the failed `gumtree_scraper.js` (curl-impersonate via Docker) with a Python scraper using Scrapling's `StealthyFetcher` + `solve_cloudflare=True`. Scrapling uses **patchright** (a binary-patched Playwright fork) that removes automation signals at the runtime level and actively solves Cloudflare Turnstile/Interstitial challenges — the root cause of every previous bypass failure on Gumtree.co.za.

The scraper fetches Gumtree "Wanted Ads" listings for vehicle tracker keywords, extracts individual ad pages, and parses: title, description, phone number (critical — only source with phone numbers visible), location, adid, and URL. Output is a JSON file compatible with the existing b2c_run.py pipeline.

## User Story

As Charles (pipeline engineer),
I want Gumtree "Wanted" ads for vehicle trackers scraped reliably with phone numbers extracted,
So that the B2C call centre has warm leads with direct contact numbers instead of cold name-only leads.

## Problem Statement

Gumtree.co.za is the only SA source where consumer phone numbers appear directly on listings. It uses Cloudflare-gated JS rendering that blocks all free bypass methods:

| Method | Result |
|---|---|
| curl-impersonate (Docker, x86_64) | Returns 98-byte JS shell — no listings |
| Playwright + stealth plugin | Listings don't render — JS-gated, CDN challenge |
| Direct HTTP with real UA | Same 98-byte JS shell |

Root cause: Cloudflare Turnstile/Interstitial challenge runs before listings are served. Neither curl-impersonate nor vanilla Playwright removes the CDP runtime markers, automation flags, and canvas/WebRTC fingerprints that Cloudflare checks.

## Solution Statement

Scrapling's `StealthyFetcher` uses **patchright** — a binary-patched Playwright that removes all known automation signals at the runtime level (CDP markers, `navigator.webdriver`, canvas noise, WebRTC leaks). Combined with `solve_cloudflare=True`, it actively waits for and solves the Cloudflare challenge iframe before returning the page.

Implementation:
1. New Python script `scripts/gumtree_scrapling.py` with same CLI interface as the old JS scraper
2. Uses `StealthySession` (keeps browser open across pages — solves Cloudflare once, reuses session)
3. Searches the same 3 keyword URLs as the JS scraper
4. Extracts ad links → fetches individual pages → parses title/description/phone/location/price/adid
5. Outputs `gumtree-leads-YYYY-MM-DD.json` in exact same schema as old scraper
6. Add `scrapling[fetchers]` to `pyproject.toml`

## Feature Metadata

**Feature Type**: Enhancement (replacing blocked implementation)
**Estimated Complexity**: Low-Medium
**Primary Systems Affected**: `scripts/gumtree_scrapling.py` (new), `pyproject.toml` (dependency add)
**Dependencies**: `scrapling[fetchers]>=0.4.2`, system Chromium (via `scrapling install`)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ BEFORE IMPLEMENTING

- `scripts/gumtree_scraper.js` (lines 1–195) — The JS scraper being replaced. **Must match its output schema exactly**: `{ title, description, phone, location, price, adid, url, scraped_at }`. Also match its CLI flags (`--max N`, `--out /path`) and stdout JSON format.
- `scripts/gumtree_scraper.js` (lines 134–138) — The 3 SEARCH_URLS to replicate in Python.
- `scripts/gumtree_scraper.js` (lines 50–131) — Phone extraction logic, ad link extraction regex, block detection strings — replicate these patterns in Python.
- `test_b2c_webhook.py` (lines 1–30) — Coding style: dotenv loading, env var handling, print-based logging with emoji. Mirror this style.
- `pyproject.toml` — Current deps: `httpx>=0.28.1`, `python-dotenv>=1.2.1`, Python 3.13+. Add `scrapling[fetchers]` here.
- `skills/cogstack-b2c-leadgen/SKILL.md` (lines 45–68) — Gumtree section. The `b2c_run.py` on bigtorig reads `memory/gumtree-leads-YYYY-MM-DD.json` — the output path must match.

### New Files to Create

- `scripts/gumtree_scrapling.py` — Python replacement scraper using Scrapling StealthyFetcher
- `test_gumtree_scrapling.py` — Standalone test/validation script (fetches 1 listing page, dumps results)

### Files to Update

- `pyproject.toml` — Add `scrapling[fetchers]>=0.4.2` to dependencies

### Relevant Documentation — READ BEFORE IMPLEMENTING

- [Scrapling GitHub README](https://github.com/D4Vinci/Scrapling)
  - Sections: StealthyFetcher, solve_cloudflare, installation
  - Why: Primary source for import paths and parameter names
- [Scrapling ReadTheDocs](https://scrapling.readthedocs.io/en/latest/index.html)
  - Why: Full API reference for StealthySession and Response object

### Patterns to Follow

**Script entry point pattern** (from `test_b2c_webhook.py`):
```python
if __name__ == "__main__":
    main()
```

**Env/arg handling pattern** (from `test_b2c_webhook.py` lines 21-25):
```python
from dotenv import load_dotenv
load_dotenv()
```

**Print logging pattern** (from `test_b2c_webhook.py` lines 140–170):
```python
print(f"[gumtree] Starting — max {max_ads} ads → {out_path}")
print(f"[gumtree] ✓ \"{title}\" | phone: {phone or 'none'} | loc: {location or '?'}")
```
Use `[gumtree]` prefix consistently (matches original JS scraper's stderr logging style).

**CLI arg pattern** (from `gumtree_scraper.js` lines 19–26 — replicate same flags):
```
--max N      (default 15)
--out /path  (default memory/gumtree-leads-YYYY-MM-DD.json)
```

**Output JSON schema** (must match exactly — `b2c_run.py` reads this):
```python
{
    "title": str | None,
    "description": str | None,
    "phone": str | None,       # e.g. "+27821234567" (no spaces/dashes)
    "location": str | None,
    "price": str | None,
    "adid": str | None,
    "url": str,
    "scraped_at": str          # ISO8601 e.g. "2026-03-17T09:00:00.000Z"
}
```

**Block detection** (from `gumtree_scraper.js` lines 95–98 — check for these strings):
```python
BLOCK_SIGNALS = ["The request is blocked", "Access Denied", "cf-challenge"]
```

**Phone normalisation** (from `gumtree_scraper.js` lines 52–56):
```python
import re
PHONE_RE = re.compile(r'(?:\+27|27|0)[6-8]\d[\s\-]?\d{3}[\s\-]?\d{4}')
# Normalise: strip spaces and dashes → "+27821234567"
```

**Ad link extraction** (from `gumtree_scraper.js` lines 58–71 — Gumtree URL pattern):
```
Accept:  https://www.gumtree.co.za/a-{anything}
Reject:  URLs containing /s-user/ or /s-my-gumtree/
Strip:   query params (split on '?')
Dedupe:  use a set()
```

**AdID extraction** (from `gumtree_scraper.js` lines 73–81):
```
Try 1: data-adid="(\d+)" attribute in HTML
Try 2: last numeric segment of the URL
```

**Sleep between requests** (from `gumtree_scraper.js` line 170):
```python
import random, time
time.sleep(0.8 + random.random() * 1.2)  # 800–2000ms jitter
```

---

## IMPLEMENTATION PLAN

### Phase 1: Dependency Setup

Add Scrapling to `pyproject.toml` and install on bigtorig. This must happen before writing the script.

### Phase 2: Core Scraper Script

Create `scripts/gumtree_scrapling.py` with StealthySession, Cloudflare solving, and the same extraction logic as the JS scraper.

### Phase 3: Validation Test Script

Create `test_gumtree_scrapling.py` — a minimal one-page test that validates the Cloudflare bypass is working before running a full scrape.

### Phase 4: Deploy to bigtorig

Copy the new script to bigtorig's workspace and update `b2c_run.py` to call `gumtree_scrapling.py` instead of `gumtree_scraper.js`.

---

## STEP-BY-STEP TASKS

### Task 1: UPDATE `pyproject.toml` — add Scrapling dependency

- **ADD**: `"scrapling[fetchers]>=0.4.2"` to `dependencies` list
- **GOTCHA**: The `[fetchers]` extra is required — bare `scrapling` does not include Playwright/patchright. Without it, `StealthyFetcher` will raise an `ImportError`.
- **VALIDATE**: `uv sync && uv run python -c "from scrapling.fetchers import StealthyFetcher; print('OK')"`

### Task 2: CREATE `scripts/gumtree_scrapling.py`

- **IMPLEMENT**: Python script with the following structure:
  1. Argument parsing (`--max`, `--out`) — mirror JS scraper's CLI interface exactly
  2. Constants: `SEARCH_URLS` (same 3 URLs as JS scraper), `BLOCK_SIGNALS`
  3. Helper functions: `extract_phone()`, `extract_ad_links()`, `extract_adid()`, `parse_ad_page()`
  4. Main function using `StealthySession` with `solve_cloudflare=True`, `network_idle=True`
  5. Output: write `gumtree-leads-YYYY-MM-DD.json` + print stdout JSON (for shell piping)

- **IMPORTS**:
```python
import argparse
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from scrapling.fetchers import StealthySession
from dotenv import load_dotenv
```

- **StealthySession config to use**:
```python
StealthySession(
    headless=True,
    solve_cloudflare=True,
    network_idle=True,
    disable_resources=True,   # skip fonts/images for speed
    block_webrtc=True,        # prevent IP leak through WebRTC
    hide_canvas=True,         # canvas noise for fingerprint evasion
    timeout=90000,            # 90s — Cloudflare solving needs time
    retries=3,
)
```

- **GOTCHA 1**: `solve_cloudflare=True` automatically raises timeout to 60000ms, but Gumtree's challenge can be slow — set `timeout=90000` explicitly to override.
- **GOTCHA 2**: Do NOT use `disable_resources=True` on listing pages that load ad links via AJAX — set `disable_resources=False` (or omit) for the listing page fetch, only use it for individual ad pages where JS content is already loaded.
- **GOTCHA 3**: Gumtree listing page HTML uses `/a-` URL prefix for individual ad links. The ad links in the HTML may be relative (`/a-car-parts/...`) or absolute. Normalise to absolute.
- **GOTCHA 4**: `phone` field in output must be normalised — no spaces or dashes. e.g. `"+27821234567"` not `"+27 82 123 4567"`.
- **GOTCHA 5**: `scraped_at` must be ISO8601 format matching the JS scraper output: `datetime.now(timezone.utc).isoformat()`.
- **GOTCHA 6**: `b2c_run.py` on bigtorig uses the output file path `memory/gumtree-leads-YYYY-MM-DD.json` relative to the workspace root (`~/.openclaw/workspace/`). The `--out` default must produce a path the script can write to. In this repo, the default is `scripts/../memory/gumtree-leads-YYYY-MM-DD.json`.
- **GOTCHA 7**: On bigtorig, `scrapling install` must have been run once to download Chromium. The script should catch `RuntimeError` on first fetch and print a helpful message if Chromium is missing.

- **Response parsing approach**:
  - Use `page.css('a::attr(href)').getall()` to extract ad links from listing page
  - Filter links with the same logic as JS: keep `/a-` pattern, reject `/s-user/` and `/s-my-gumtree/`
  - On individual ad pages: use `page.css('[data-q="ad-description"]::text').get()` for description
  - For phone: check `page.css('a[href^="tel:"]::attr(href)').get()` first (most reliable), then `page.css('[data-phone]::attr(data-phone)').get()`, then regex on `page.body.decode('utf-8', errors='ignore')`
  - For title: `page.css('h1::text').get()`
  - For location: `page.css('[data-q="ad-location"]::text').get()`
  - For price: `page.css('[data-q="ad-price"]::text').get()`

- **VALIDATE**:
```bash
cd /opt/projects/cartrack-leadgen
uv run python -m py_compile scripts/gumtree_scrapling.py && echo "syntax OK"
```

### Task 3: CREATE `test_gumtree_scrapling.py`

- **IMPLEMENT**: Minimal test that:
  1. Fetches ONE listing page (first SEARCH_URL)
  2. Prints raw HTML length and a 500-char snippet
  3. Reports whether it looks like a real page (listings present) or a block/shell
  4. If listings found: fetches the first ad link and extracts all fields
  5. Prints a clear PASS/FAIL verdict

- **PURPOSE**: Run this before the full scraper to validate Scrapling bypasses Cloudflare. Costs only ~2 browser page loads.

- **VALIDATE**:
```bash
cd /opt/projects/cartrack-leadgen
uv run test_gumtree_scrapling.py
# Expected: PASS — real listings HTML detected, ad extracted with phone field
# Failure signal: "98 bytes" or "The request is blocked" → Scrapling didn't bypass
```

### Task 4: INSTALL Scrapling on bigtorig

After committing and pushing, run on bigtorig:

```bash
# Install Python deps (uv pip install works without a pyproject.toml in the workspace)
cd ~/.openclaw/workspace  # or wherever b2c_run.py lives
uv pip install "scrapling[fetchers]>=0.4.2"

# Download Chromium binaries (one-time, ~300MB)
uv run scrapling install
```

**VALIDATE on bigtorig**:
```bash
uv run python -c "from scrapling.fetchers import StealthyFetcher; print('import OK')"
uv run python -c "import patchright; print('patchright OK')"
```

### Task 5: DEPLOY `scripts/gumtree_scrapling.py` to bigtorig workspace

```bash
# From cartrack-leadgen dev machine:
scp scripts/gumtree_scrapling.py bigtorig:~/.openclaw/workspace/scripts/gumtree_scrapling.py
```

**VALIDATE**:
```bash
ssh bigtorig "uv run python -m py_compile ~/.openclaw/workspace/scripts/gumtree_scrapling.py && echo OK"
```

### Task 6: TEST on bigtorig — single page validation

```bash
ssh bigtorig "cd ~/.openclaw/workspace && uv run python scripts/gumtree_scrapling.py --max 3 2>&1"
```

Expected output:
```
[gumtree] Starting — max 3 ads → .../memory/gumtree-leads-2026-03-17.json
[gumtree] Fetching listing: https://www.gumtree.co.za/s-wanted-ads/car-tracker/...
[gumtree] Found N ad links
[gumtree] ✓ "WANTED: car tracker urgently" | phone: +27821234567 | loc: Johannesburg
[gumtree] Done — 3 ads → .../memory/gumtree-leads-2026-03-17.json
```

**VALIDATE**:
```bash
ssh bigtorig "cat ~/.openclaw/workspace/memory/gumtree-leads-$(date +%Y-%m-%d).json | uv run python -m json.tool | head -40"
# Must show lead objects with url, title, and (ideally) phone field populated
```

### Task 7: UPDATE SKILL.md — reflect new scraper

- **UPDATE** `skills/cogstack-b2c-leadgen/SKILL.md`, Section "Gumtree — Special Handling":
  - Change command from `node scripts/gumtree_scraper.js --max 15` to `uv run python scripts/gumtree_scrapling.py --max 15`
  - Remove `docker pull lwthiker/curl-impersonate:0.6-chrome` requirement note
  - Add note: requires `scrapling[fetchers]` installed and `scrapling install` run once on bigtorig

- **DEPLOY** updated SKILL.md to bigtorig:
```bash
scp skills/cogstack-b2c-leadgen/SKILL.md bigtorig:~/.openclaw/workspace/skills/cogstack-b2c-leadgen/SKILL.md
```

---

## TESTING STRATEGY

### No formal test suite exists in this project

This project has no pytest setup. Validation is done via:
1. `uv run python -m py_compile <file>` — syntax check
2. Manual execution with `--max 3` and inspecting JSON output
3. End-to-end: run scraper → verify `gumtree-leads-YYYY-MM-DD.json` is written with expected schema

### Edge Cases to Handle

| Case | Handling |
|---|---|
| Cloudflare challenge not solved (timeout) | Catch `RuntimeError`, print `[gumtree] BLOCKED — Scrapling could not solve challenge`, exit with code 1 and `{"ok": false, "error": "..."}` to stdout |
| Listing page returns no ad links | Print `[gumtree] Found 0 ad links on {url}` and continue to next search URL |
| Ad page missing phone number | Set `phone: null` — don't skip the ad (title + intent_signal still valuable) |
| Ad page is a block page | Check for `BLOCK_SIGNALS` strings in `page.body`; skip with warning |
| Output directory doesn't exist | Use `Path(out_path).parent.mkdir(parents=True, exist_ok=True)` |
| `scrapling install` not run | Wrap first `StealthySession` creation in try/except, print install instructions if Chromium missing |
| Network error mid-scrape | `retries=3` in StealthySession handles transient failures automatically |
| `max_ads` reached before all URLs processed | Break out of outer loop (mirrors JS scraper behaviour) |

---

## VALIDATION COMMANDS

### Level 1: Syntax

```bash
cd /opt/projects/cartrack-leadgen
uv run python -m py_compile scripts/gumtree_scrapling.py && echo "gumtree_scrapling.py OK"
uv run python -m py_compile test_gumtree_scrapling.py && echo "test_gumtree_scrapling.py OK"
```

### Level 2: Import check (requires scrapling installed)

```bash
cd /opt/projects/cartrack-leadgen
uv run python -c "from scrapling.fetchers import StealthySession; print('imports OK')"
```

### Level 3: Single-page test (validates Cloudflare bypass)

```bash
cd /opt/projects/cartrack-leadgen
uv run test_gumtree_scrapling.py
# PASS = "real listings HTML detected"
# FAIL = "98 bytes" or "blocked" in output
```

### Level 4: Full scrape validation (on bigtorig)

```bash
# Run with --max 3 for quick test
ssh bigtorig "cd ~/.openclaw/workspace && uv run python scripts/gumtree_scrapling.py --max 3 2>&1"

# Validate output file
ssh bigtorig "uv run python -c \"
import json; data = json.load(open('$(date +%Y-%m-%d)'.join(['/root/.openclaw/workspace/memory/gumtree-leads-', '.json'])))
assert isinstance(data, list), 'not a list'
if data:
    keys = set(data[0].keys())
    required = {'title','description','phone','location','price','adid','url','scraped_at'}
    assert required.issubset(keys), f'missing keys: {required - keys}'
    print(f'OK: {len(data)} ads, schema valid, phones: {sum(1 for a in data if a[\"phone\"])}')
\""
```

### Level 5: End-to-end pipeline check

After a successful full scrape on bigtorig:
```bash
# b2c_run.py should pick up the gumtree output automatically
ssh bigtorig "cd ~/.openclaw/workspace && uv run python scripts/b2c_run.py 2>&1 | tail -5"
# Look for: "Gumtree leads merged: N"
# Check Notion B2C Leads DB for entries with intent_source: Gumtree
```

---

## ACCEPTANCE CRITERIA

- [ ] `scripts/gumtree_scrapling.py` exists and passes syntax check
- [ ] `StealthySession` with `solve_cloudflare=True` + `network_idle=True` successfully fetches Gumtree listing pages (not a 98-byte JS shell)
- [ ] At least 1 ad extracted with `phone` field populated per run
- [ ] Output JSON matches `{ title, description, phone, location, price, adid, url, scraped_at }` schema exactly
- [ ] `--max N` and `--out /path` CLI flags work correctly
- [ ] Block detection: script exits cleanly with `{"ok": false}` to stdout if Cloudflare is not bypassed
- [ ] `pyproject.toml` updated with `scrapling[fetchers]` dependency
- [ ] SKILL.md updated with new command
- [ ] Deployed to bigtorig and runs successfully end-to-end

---

## NOTES

### Fallback if Scrapling also fails

If `StealthyFetcher` cannot bypass Gumtree's bot gate (possible if bigtorig's datacenter IP is flagged beyond Cloudflare Turnstile), the escalation path is:

1. **Add a residential proxy** to StealthySession via `proxy='http://user:pass@residential-proxy:port'` — datacenter IPs are higher-risk than residential IPs for Cloudflare. A cheap residential proxy service (~$5–15/month) may unblock this without ScraperAPI.
2. **ScraperAPI** (5,000 free credits trial) — managed rotating residential proxies with JS rendering. Replace StealthySession with a `httpx.get(f"http://api.scraperapi.com?api_key={KEY}&url={TARGET}&render=true")` call. Same extraction logic applies.

### Why StealthySession over StealthyFetcher.fetch()

`StealthySession` keeps the Chromium browser open across multiple pages. This means:
- Cloudflare challenge is solved once per session (not once per page)
- Cookies, localStorage, and fingerprint state persist across the listing page + all ad pages
- Significantly faster than opening/closing a browser for each page

### Scrapling Docker image

If running in a fresh Docker container on bigtorig: `pyd4vinci/scrapling:latest` includes all browsers and deps. May be simpler than running `scrapling install` in a fresh environment.

### Claire's Lead Delivery API (Production Endpoint)

Claire has provided a direct API endpoint to receive **production-ready leads** from the B2C pipeline. This is the downstream destination after QA approval — leads go here instead of (or in addition to) Notion handoff to the call centre.

| Field | Value |
|---|---|
| Campaign Name | `B2C - 9PointPlanWA` |
| Lead Campaign UID | `af7b2cbb-29a4-446b-b4fd-0199a060d9ad` |
| Instance UID | `793c83c2-f829-464c-ad82-a157cf85bf34` |
| API Token | stored in `.env` as `CLAIRE_LEAD_API_TOKEN` — **do not commit** |

**Store the token in `.env`:**
```bash
CLAIRE_LEAD_API_TOKEN=<token from Claire — do not commit>
CLAIRE_CAMPAIGN_UID=af7b2cbb-29a4-446b-b4fd-0199a060d9ad
CLAIRE_INSTANCE_UID=793c83c2-f829-464c-ad82-a157cf85bf34
```

**Integration note:** The API endpoint and payload format are not yet documented here — confirm with Claire the exact POST URL, request schema, and required lead fields before implementing the delivery step. This is a **Phase 3 task** (after Gumtree scraping is validated end-to-end). The current pipeline stores leads in Notion for QA; this API becomes the handoff after QA approval.

**Next step:** Ask Claire for the API base URL and request/response schema so the delivery integration can be planned.

### Output path note

In this repo, the default output path is `scripts/../memory/gumtree-leads-YYYY-MM-DD.json` (i.e., `memory/` directory at repo root). On bigtorig's workspace, `b2c_run.py` expects `memory/gumtree-leads-YYYY-MM-DD.json` relative to `~/.openclaw/workspace/`. When deploying, make sure the script is run from `~/.openclaw/workspace/` so the relative path resolves correctly, or pass `--out ~/.openclaw/workspace/memory/gumtree-leads-YYYY-MM-DD.json` explicitly.

---

**Confidence Score: 7/10**

The main uncertainty is whether bigtorig's datacenter IP is flagged by Cloudflare at the IP reputation level (beyond Turnstile). Scrapling solves the fingerprinting problem definitively; IP reputation is outside its scope. If the datacenter IP is clean, success is very likely. If flagged, a residential proxy addition brings confidence to 9/10.
