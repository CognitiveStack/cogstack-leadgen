# Feature: Migrate Hugo B2C Lead Generation to bigtorig

The following plan should be complete, but validate each step before proceeding to the next.

## Feature Description

Move Hugo's B2C lead generation pipeline from Pi4 (ARM64) to bigtorig (x86_64) so that the Gumtree scraper (curl-impersonate) can run natively. bigtorig already has OpenClaw, antfarm, and the `lwthiker/curl-impersonate:0.6-chrome` Docker image installed. The gateway is currently crashing due to a single invalid config key — one command fixes it.

## User Story

As Charles,
I want Hugo's B2C lead generation running on bigtorig,
So that the Gumtree scraper works natively (x86_64), yielding phone-verified leads without ARM64 workarounds.

## Problem Statement

- `gumtree_scraper.js` uses `lwthiker/curl-impersonate:0.6-chrome` (x86_64 only)
- Pi4 is ARM64 — the Docker image fails with `exec format error`
- bigtorig is x86_64, already has the image, already has OpenClaw + antfarm
- bigtorig's `openclaw-gateway.service` crashes on every start due to one bad config key

## Solution Statement

1. Fix the config crash (one command: `openclaw doctor --fix`)
2. Copy Hugo's B2C workspace (scripts, skills, memory, state) from Pi4 to bigtorig
3. Set the required env vars on bigtorig (`~/.env`)
4. Run a full B2C test including Gumtree scraper
5. Update HEARTBEAT.md on bigtorig to schedule 3x/week runs
6. Update SKILL.md to reflect bigtorig as the primary host

## Feature Metadata

**Feature Type**: Enhancement (infrastructure migration)
**Estimated Complexity**: Low — mostly copying files + one config fix
**Primary Systems Affected**: bigtorig OpenClaw gateway, Hugo's B2C workspace
**Dependencies**: `lwthiker/curl-impersonate:0.6-chrome` (already pulled on bigtorig)

---

## CONTEXT REFERENCES

### Must Read Before Implementing

| File | Location | Why |
|------|----------|-----|
| `skills/cogstack-b2c-leadgen/SKILL.md` | This repo | Current skill v1.5 — source of truth |
| `scripts/gumtree_scraper.js` | This repo | Gumtree scraper using curl-impersonate |
| `~/.openclaw/openclaw.json` | bigtorig | Has the bad `agentmail` key causing crash |
| `~/.openclaw/workspace/scripts/b2c_run.py` | Pi4 | 730-line runner to copy to bigtorig |
| `~/.env` | Pi4 | Source of all required env vars |
| `~/.openclaw/workspace/memory/b2c-state.json` | Pi4 | Submitted URL dedup state to migrate |

### New Files to Create on bigtorig

| Path | Purpose |
|------|---------|
| `~/.openclaw/workspace/scripts/b2c_run.py` | Copy from Pi4 |
| `~/.openclaw/workspace/scripts/gumtree_scraper.js` | Copy from Pi4 workspace |
| `~/.openclaw/workspace/skills/cogstack-b2c-leadgen/SKILL.md` | Copy from Pi4 |
| `~/.openclaw/workspace/memory/b2c-state.json` | Copy from Pi4 (preserves dedup) |
| `~/.env` | Set env vars (webhook URLs, tokens, OpenRouter key) |

### Known Facts About bigtorig Environment

- OS: x86_64 Linux (Ubuntu/Debian)
- Node: v22.22.0 via nvm (`~/.nvm/versions/node/v22.22.0/bin/`)
- OpenClaw binary: `~/.nvm/versions/node/v22.22.0/bin/openclaw`
- Antfarm binary: `~/.nvm/versions/node/v22.22.0/bin/antfarm`
- Docker: available, `lwthiker/curl-impersonate:0.6-chrome` already pulled
- Workspace root: `~/.openclaw/workspace/` (exists, has SOUL.md, HEARTBEAT.md etc.)
- Gateway service: `openclaw-gateway.service` (user systemd, crashing)
- Antfarm service: `openclaw-antfarm.service` or similar (check with `systemctl --user list-units | grep openclaw`)
- HEARTBEAT.md: exists but empty (no tasks yet)

### Crash Root Cause (CONFIRMED)

```
Invalid config at ~/.openclaw/openclaw.json:
- skills.entries.agentmail: Unrecognized key: "AGENTMAIL_API_KEY"
```

Fix: `openclaw doctor --fix`

---

## IMPLEMENTATION PLAN

### Task 1: FIX openclaw-gateway config crash

**Run on bigtorig:**
```bash
openclaw doctor --fix
systemctl --user restart openclaw-gateway.service
sleep 5
systemctl --user status openclaw-gateway.service
```

**Expected:** `Active: active (running)` — no more exit-code failure.

**VALIDATE:**
```bash
systemctl --user is-active openclaw-gateway.service
# Expected output: active
```

---

### Task 2: VERIFY antfarm service on bigtorig

Check if the antfarm agent service exists and is running:

```bash
systemctl --user list-units | grep openclaw
systemctl --user status openclaw-antfarm.service 2>/dev/null || echo "antfarm service not found"
```

If antfarm service is not running, start it:
```bash
systemctl --user start openclaw-antfarm.service
```

**VALIDATE:**
```bash
curl -s https://bigtorig.tailfd6deb.ts.net/ | head -5
# Expected: n8n or OpenClaw HTML response (dashboard accessible)
```

---

### Task 3: COPY B2C workspace from Pi4 to bigtorig

Run these from bigtorig (Pi4 is reachable via Tailscale):

```bash
# Create required directories
mkdir -p ~/.openclaw/workspace/scripts
mkdir -p ~/.openclaw/workspace/memory
mkdir -p ~/.openclaw/workspace/skills/cogstack-b2c-leadgen

# Copy scripts
scp pi4:~/.openclaw/workspace/scripts/b2c_run.py ~/.openclaw/workspace/scripts/
scp pi4:~/.openclaw/workspace/scripts/gumtree_scraper.js ~/.openclaw/workspace/scripts/

# Copy skill
scp pi4:~/.openclaw/workspace/skills/cogstack-b2c-leadgen/SKILL.md \
    ~/.openclaw/workspace/skills/cogstack-b2c-leadgen/

# Copy dedup state (preserves already-submitted URLs)
scp pi4:~/.openclaw/workspace/memory/b2c-state.json ~/.openclaw/workspace/memory/
scp pi4:~/.openclaw/workspace/memory/b2c-seed-urls.json ~/.openclaw/workspace/memory/ 2>/dev/null || true
```

**VALIDATE:**
```bash
ls ~/.openclaw/workspace/scripts/
# Expected: b2c_run.py  gumtree_scraper.js
python3 -m py_compile ~/.openclaw/workspace/scripts/b2c_run.py && echo "syntax OK"
node --check ~/.openclaw/workspace/scripts/gumtree_scraper.js && echo "syntax OK"
```

---

### Task 4: SET env vars on bigtorig (~/.env)

Append the required B2C vars to `~/.env` on bigtorig. Get token values from Pi4:

```bash
# On bigtorig — check what's already set
grep 'B2C\|OPENROUTER\|WEBHOOK' ~/.env 2>/dev/null || echo "not set"
```

Add missing vars (get actual values from Pi4's `~/.env`):
```bash
cat >> ~/.env << 'EOF'
B2C_WEBHOOK_URL=https://n8n.bigtorig.com/webhook/b2c-lead-ingestion
B2C_WEBHOOK_TOKEN=<from pi4 ~/.env>
B2C_DATE_AFTER=2026-02-14
OPENROUTER_API_KEY=<from pi4 ~/.env>
EOF
```

**VALIDATE:**
```bash
grep 'B2C_WEBHOOK_URL\|B2C_WEBHOOK_TOKEN\|OPENROUTER_API_KEY' ~/.env
# All three must be present and non-empty
```

---

### Task 5: INSTALL npm dependencies on bigtorig

The `gumtree_scraper.js` requires `playwright-extra` and `puppeteer-extra-plugin-stealth` (even though we now use curl-impersonate, the imports may still reference them as fallback). Install in the workspace:

```bash
cd ~/.openclaw/workspace
npm install playwright-extra puppeteer-extra-plugin-stealth 2>/dev/null || true
```

If `package.json` doesn't exist yet:
```bash
cd ~/.openclaw/workspace
echo '{"name":"hugo-workspace","version":"1.0.0"}' > package.json
npm install playwright-extra puppeteer-extra-plugin-stealth
```

**VALIDATE:**
```bash
node -e "require('playwright-extra'); console.log('OK')" && echo "deps OK"
```

---

### Task 6: TEST Gumtree scraper on bigtorig (the whole point)

```bash
cd ~/.openclaw/workspace
node scripts/gumtree_scraper.js --max 3 2>&1
```

**Expected output:**
```
[gumtree] Starting — max 3 ads → .../memory/gumtree-leads-YYYY-MM-DD.json
[gumtree] Fetching listing: https://www.gumtree.co.za/s-wanted-ads/car-tracker/...
[gumtree] Found N ad links
[gumtree] ✓ "<ad title>" | phone: <number or none> | loc: <location>
[gumtree] Done — N ads → ...
```

**VALIDATE:**
```bash
cat ~/.openclaw/workspace/memory/gumtree-leads-$(date +%Y-%m-%d).json | python3 -m json.tool | head -30
# Should show lead objects with title, url, scraped_at fields
```

---

### Task 7: TEST full B2C run on bigtorig

```bash
cd ~/.openclaw/workspace
python3 scripts/b2c_run.py 2>&1
```

**Expected response from webhook:**
```json
{ "status": "success", "leads_created": N, "duplicates_skipped": M }
```

**VALIDATE:**
```bash
cat ~/.openclaw/workspace/memory/b2c-run-$(date +%Y-%m-%d).json | python3 -m json.tool | grep -E 'leads_created|duplicates_skipped|batch_id'
```

---

### Task 8: UPDATE HEARTBEAT.md on bigtorig

Add the B2C run schedule (Mon/Wed/Fri 09:00 SAST = 07:00 UTC):

```markdown
## Scheduled Tasks

### B2C Lead Generation (Mon/Wed/Fri)
- Run: `cd ~/.openclaw/workspace && node scripts/gumtree_scraper.js --max 15 && python3 scripts/b2c_run.py`
- Schedule: Mon/Wed/Fri 07:00 UTC (09:00 SAST)
- Report: WhatsApp Charles with leads_created + duplicates_skipped + batch_id
```

**VALIDATE:**
```bash
grep 'b2c_run' ~/.openclaw/workspace/HEARTBEAT.md && echo "schedule added"
```

---

### Task 9: UPDATE SKILL.md to reflect bigtorig as primary host

Deploy updated SKILL.md from this repo to bigtorig:

```bash
# From cartrack-leadgen dev machine:
scp skills/cogstack-b2c-leadgen/SKILL.md bigtorig:~/.openclaw/workspace/skills/cogstack-b2c-leadgen/SKILL.md
```

Also update the skill header:
- Change `**Agent:** Hugo (OpenClaw on Pi4)` → `**Agent:** Hugo (OpenClaw on bigtorig)`
- Change `**Version:** 1.5` → `**Version:** 2.0`

---

### Task 10: COMMIT and update docs

```bash
git add skills/cogstack-b2c-leadgen/SKILL.md .agents/plans/migrate-b2c-to-bigtorig.md
git commit -m "feat: migrate B2C lead gen to bigtorig — Gumtree scraper now native x86_64"
```

Update `.claude/docs/OPENCLAW.md`:
- Change primary host from Pi4 to bigtorig for B2C pipeline
- Note Pi4 remains active for WhatsApp/Hugo chat (MTN SIM)
- Document that Gumtree scraper requires bigtorig (x86_64)

---

## VALIDATION COMMANDS

### Level 1 — Gateway healthy
```bash
systemctl --user is-active openclaw-gateway.service   # → active
curl -s https://bigtorig.tailfd6deb.ts.net/ | head -3  # → HTML response
```

### Level 2 — Scripts present and valid
```bash
python3 -m py_compile ~/.openclaw/workspace/scripts/b2c_run.py && echo "b2c_run.py OK"
node --check ~/.openclaw/workspace/scripts/gumtree_scraper.js && echo "gumtree_scraper.js OK"
```

### Level 3 — Gumtree scraper returns real ads
```bash
cd ~/.openclaw/workspace && node scripts/gumtree_scraper.js --max 3 2>&1 | grep -E '✓|Done|BLOCKED'
# Must see ✓ lines, not BLOCKED
```

### Level 4 — Full B2C run succeeds
```bash
cd ~/.openclaw/workspace && python3 scripts/b2c_run.py 2>&1 | tail -10
# Must see: leads_created > 0 OR duplicates_skipped > 0 (not SKIPPED_POST_NO_LEADS)
```

### Level 5 — Notion confirms new leads
Check Notion B2C Leads DB for entries with `Pending QA` status and `intent_source: Gumtree` — these are the phone-verified leads.

---

## ACCEPTANCE CRITERIA

- [ ] `openclaw-gateway.service` is `active (running)` on bigtorig
- [ ] `https://bigtorig.tailfd6deb.ts.net/` is accessible
- [ ] `gumtree_scraper.js` returns ≥ 1 real Gumtree ad with `phone` field populated
- [ ] Full B2C run (gumtree + web_search + enrich + POST) succeeds on bigtorig
- [ ] At least 1 lead with a phone number appears in Notion B2C Leads DB
- [ ] HEARTBEAT.md on bigtorig has B2C run scheduled Mon/Wed/Fri
- [ ] SKILL.md v2.0 deployed to bigtorig workspace

---

## NOTES

**Pi4 stays active** — Hugo's WhatsApp (+27639842638 MTN SIM) is tied to Pi4. Keep `openclaw-antfarm.service` running on Pi4 for WhatsApp. B2C lead gen moves to bigtorig; chat/heartbeat stays on Pi4. Optionally, set up WhatsApp on bigtorig as a secondary channel later.

**Gumtree scraper architecture decision:** `gumtree_scraper.js` runs first, writes `memory/gumtree-leads-YYYY-MM-DD.json`, then `b2c_run.py` reads + merges those leads with web_search results before enrichment and POST. The `b2c_run.py` needs a small patch to read from the Gumtree output file — this is Task 7's first blocker if not already implemented.

**bigtorig has no `~/.openclaw/workspace/scripts/` dir** — it must be created (Task 3).

**SearXNG is NOT on bigtorig** — `b2c_run.py` falls back to seed file mode when SearXNG is unavailable, which is correct. Discovery on bigtorig = `web_search` tool (Brave API) via Hugo's antfarm session.

**Confidence Score: 8/10** — The only unknowns are whether the antfarm agent on bigtorig has `web_search` and `OPENROUTER_API_KEY` configured, and whether `b2c_run.py` already has Gumtree output integration. Both are quick to verify and fix.
