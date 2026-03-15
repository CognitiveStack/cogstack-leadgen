# OpenClaw & Hugo — Role in Cogstack Lead Generation

## What Is OpenClaw?

OpenClaw is an autonomous AI agent runtime — a headless, always-on AI that can receive messages, use tools, run scheduled tasks (heartbeats), and operate 24/7 without a human at a keyboard. It was recently acquired by OpenAI but remains open source.

**Two OpenClaw instances run in the Cogstack infrastructure:**

| Instance | Host | URL | Purpose |
|----------|------|-----|---------|
| **Primary** | bigtorig (x86_64 VPS) | `https://bigtorig.tailfd6deb.ts.net/` | B2C lead gen scripts, Gumtree scraper |
| **Secondary** | Pi4 (ARM64, home LAN) | `https://pi4.tailfd6deb.ts.net/` | Hugo's WhatsApp channel (+27639842638) |

Both gateways listen on port `18789` and are exposed via Tailscale Serve (HTTPS).

**Repositories:**
- `CognitiveStack/pi4` (private) — Pi4 infrastructure and setup
- `CognitiveStack/hugo` (private) — Hugo's identity, memory, skills, config

---

## Who Is Hugo?

Hugo is the OpenClaw agent personality running across both instances.

| Property | Value |
|----------|-------|
| Name | Hugo |
| Phone | +27639842638 (MTN SIM on Pi4 — WhatsApp primary channel) |
| Email | hugo@cogstack.co.za |
| Channel | WhatsApp (primary), responds only to Charles (+27836177469) |
| Vibe | Casual, sharp, no-nonsense. Skips filler. Has opinions. |
| Phase | Phase 2 — HTTP + Browser + bigtorig migration complete |

Hugo wakes up fresh each session. Continuity comes from markdown files in `~/.openclaw/workspace/`:
- `SOUL.md` — who he is
- `USER.md` — who he's helping (Charles)
- `memory/YYYY-MM-DD.md` — daily logs
- `MEMORY.md` — curated long-term memory

---

## Infrastructure State (as of 2026-03-15)

### bigtorig OpenClaw (Primary for lead gen)

| Item | Value |
|------|-------|
| OS | Ubuntu x86_64 |
| Node | v22.22.0 (nvm) |
| Gateway service | `openclaw-gateway.service` — active |
| Antfarm service | `openclaw-antfarm.service` — active |
| Gateway port | `0.0.0.0:18789` |
| Tailscale Serve | `https://bigtorig.tailfd6deb.ts.net/` → `http://localhost:18789` |
| UI status | Working (allowedOrigins fix applied 2026-03-15) |
| Docker | Available — `lwthiker/curl-impersonate:0.6-chrome` pulled |
| B2C workspace | `~/.openclaw/workspace/scripts/` + `skills/` + `memory/` populated |

**Gateway fix applied:** Removed invalid `skills.entries.agentmail.AGENTMAIL_API_KEY` key from `openclaw.json` that caused crash-loop. Also added `https://bigtorig.tailfd6deb.ts.net` to `gateway.controlUi.allowedOrigins`.

### Pi4 OpenClaw (Secondary — WhatsApp only)

| Item | Value |
|------|-------|
| OS | Raspberry Pi OS ARM64 |
| Gateway service | `openclaw-gateway.service` — active |
| Antfarm service | `openclaw-antfarm.service` — active (Hugo's WhatsApp session) |
| Tailscale Serve | `https://pi4.tailfd6deb.ts.net/` |
| Role | WhatsApp channel only — B2C scripts stay on bigtorig |

---

## B2C Lead Generation — Current Data Flow

```
Charles triggers via WhatsApp ("Hugo, B2C leads")
    │
    ▼
Hugo antfarm session (Pi4 or bigtorig)
    │
    ├─1. web_search (Brave API) — 7 queries across 4 sources
    │    Hellopeter: /cartrack/reviews, /netstar/reviews,
    │                /ctrack-sa/reviews, /mix-telematics-africa/reviews
    │    MyBroadband: /forum/threads/ only
    │    Reddit: /r/southafrica/comments/ only
    │    OLX: specific wanted ad URLs
    │
    ├─2. URL filter — reject news articles, category pages, non-individual posts
    │
    ├─3. web_fetch — fetch each qualifying page
    │
    ├─4. LLM enrichment subagent (openrouter/openai/gpt-4o-mini)
    │    Extracts: name, phone, email, province, city, vehicle
    │    Scores: intent_strength (0-10), urgency_score (0-10)
    │    Writes: intent_signal, call_script_opener
    │    Returns: structured JSON (_meta.llm_used: true)
    │
    ├─5. Composite Score filter — discard if (intent×0.6 + urgency×0.4) < 6
    │
    ├─6. POST batch to n8n webhook
    │    POST https://n8n.bigtorig.com/webhook/b2c-lead-ingestion
    │    Authorization: Bearer <B2C_WEBHOOK_TOKEN>
    │
    └─7. WhatsApp report to Charles
         "B2C run done: X leads created, Y duplicates skipped"
    ▼
Notion B2C Leads DB → QA Review (Claire) → B2C Call Centre
```

---

## Known Issues & Workarounds

### SearXNG — Suspended (do not use for lead gen)

SearXNG runs at `http://localhost:8080` on Pi4 (Docker) but all engines are CAPTCHA'd/rate-limited as of 2026-03-14. **Not used.** Discovery goes via `web_search` tool (Brave API) directly.

### Gumtree — JS-rendered listings, all free bypass methods exhausted

Gumtree serves a JavaScript shell — actual listings load via XHR after page load. Tested and failed:

| Method | Result |
|--------|--------|
| curl-impersonate (x86_64, bigtorig) | Fetches 98-byte redirect shell, 0 ad links |
| Playwright + stealth (bigtorig) | Page loads but listings don't render (JS-gated) |
| Direct HTTP with real UA | Same shell, no listings |

**Root cause:** Listings are loaded dynamically via AJAX. No Gumtree API calls were intercepted during Playwright session — content is likely CDN-edge rendered with bot challenge gate.

**Status:** Deferred. Requires paid scraping API (ScraperAPI $49/month or Zyte) to get real listings with phone numbers. This is the only source where SA consumer phone numbers appear directly on the page.

### Hellopeter — 4 company slugs confirmed working

These query patterns reliably return individual review URLs via Brave `web_search`:
- `site:hellopeter.com/cartrack/reviews cartrack`
- `site:hellopeter.com/netstar/reviews netstar`
- `site:hellopeter.com/ctrack-sa/reviews ctrack`
- `site:hellopeter.com/mix-telematics-africa/reviews matrix`

---

## Model Strategy

Key rule: **never use direct Anthropic API** — all model calls route via OpenRouter.

| Task | Model | Route |
|------|-------|-------|
| Hugo main session / orchestration | DeepSeek v3 | OpenRouter |
| B2C enrichment subagent | gpt-4o-mini | OpenRouter |
| Local fallback | qwen2.5:14b (Ollama, desktop) | Local |
| Premium on-demand | Claude Sonnet 4.6 | OpenRouter |

---

## B2C Skill

| Item | Value |
|------|-------|
| Source of truth | `skills/cogstack-b2c-leadgen/SKILL.md` (this repo) |
| Deployed — bigtorig | `~/.openclaw/workspace/skills/cogstack-b2c-leadgen/SKILL.md` |
| Deployed — Pi4 | `~/.openclaw/workspace/skills/cogstack-b2c-leadgen/SKILL.md` |
| Runner script | `~/.openclaw/workspace/scripts/b2c_run.py` (730 lines) |
| Gumtree scraper | `~/.openclaw/workspace/scripts/gumtree_scraper.js` (deferred) |
| Run logs | `~/.openclaw/workspace/memory/b2c-run-YYYY-MM-DD.json` |
| State / dedup | `~/.openclaw/workspace/memory/b2c-state.json` |
| Current version | 2.0 |

**Deploy command (from this repo):**
```bash
cp skills/cogstack-b2c-leadgen/SKILL.md /tmp/b2c_skill.md
scp /tmp/b2c_skill.md pi4:/tmp/b2c_skill.md
scp /tmp/b2c_skill.md bigtorig:~/.openclaw/workspace/skills/cogstack-b2c-leadgen/SKILL.md
ssh pi4 "cp /tmp/b2c_skill.md ~/.openclaw/workspace/skills/cogstack-b2c-leadgen/SKILL.md"
```

**Environment variables (both hosts, `~/.env`):**
```bash
B2C_WEBHOOK_URL=https://n8n.bigtorig.com/webhook/b2c-lead-ingestion
B2C_WEBHOOK_TOKEN=1951a0fc...
B2C_DATE_AFTER=2026-02-14
OPENROUTER_API_KEY=sk-or-v1-...
COGSTACK_WEBHOOK_URL=https://n8n.bigtorig.com/webhook/lead-ingestion-v2
COGSTACK_WEBHOOK_TOKEN=1951a0fc...
```

---

## Security

| Layer | Behaviour |
|-------|-----------|
| Shell execution | Requires manual approval via OpenClaw dashboard (exec approve button) |
| Browser tool | Available on both hosts — headless Chromium |
| File writes | Limited to `~/.openclaw/workspace/` |
| WhatsApp allowlist | Charles only (+27836177469) |
| Prompt injection | Scraped content wrapped in `EXTERNAL_UNTRUSTED_CONTENT` — correct behaviour, not a bug |
| controlUi.allowedOrigins | `https://bigtorig.tailfd6deb.ts.net` added to bigtorig `openclaw.json` |

---

## Phase Roadmap

### Phase 1 (Complete) — Supervisor Mode
Hugo exists, WhatsApp connected, heartbeat running. No external access.

### Phase 2 (Current) — HTTP + Browser + bigtorig
- `web_search` (Brave API) discovery — working
- LLM enrichment (gpt-4o-mini via OpenRouter) — working, `_meta.llm_used: true` confirmed
- B2C skill v2.0 live on both hosts
- First successful run: 6 leads created, 1 duplicate skipped
- bigtorig gateway fixed, UI accessible, B2C workspace deployed
- Exec approval still required for shell commands

### Phase 3 — Scheduled Autonomy
- Add B2C run to HEARTBEAT.md on bigtorig (Mon/Wed/Fri 09:00 SAST)
- Remove exec approval friction
- Gumtree via ScraperAPI (paid) — 2-5 phone-verified leads per run

### Phase 4 — Feedback Loop
- Claire's QA rejections feed back into Hugo's scoring
- Auto-approve ≥ 7 composite score, auto-reject < 4

---

## Key Files Reference

| File | Location | Purpose |
|------|----------|---------|
| `SYSTEM.md` | `CognitiveStack/hugo` | Hard rules; edit to graduate phases |
| `SOUL.md` | `CognitiveStack/hugo` | Hugo's character |
| `HEARTBEAT.md` | bigtorig `~/.openclaw/workspace/` | Scheduled tasks — add B2C here |
| `skills/cogstack-b2c-leadgen/SKILL.md` | this repo (source of truth) | B2C lead gen playbook |
| `scripts/b2c_run.py` | bigtorig + Pi4 workspace | B2C runner (LLM enrichment active) |
| `scripts/gumtree_scraper.js` | bigtorig + Pi4 workspace | Gumtree scraper (deferred — needs ScraperAPI) |
| `n8n_b2c_code_node.js` | this repo | n8n webhook Code node |
| `memory/b2c-state.json` | bigtorig + Pi4 workspace | Submitted URL dedup state |
| `.agents/plans/migrate-b2c-to-bigtorig.md` | this repo | Migration plan (completed) |
