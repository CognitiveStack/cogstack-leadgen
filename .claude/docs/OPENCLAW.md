# OpenClaw & Hugo — Role in Cogstack Lead Generation

## What Is OpenClaw?

OpenClaw is an autonomous AI agent runtime. Think of it as a headless, always-on Claude that can receive messages, use tools, run scheduled tasks (heartbeats), and operate 24/7 without a human sitting at a keyboard. It was recently acquired by OpenAI but remains open source.

It runs on the **Raspberry Pi 4** on Charles's home LAN, accessible over Tailscale VPN at `pi4.tailfd6deb.ts.net`. The gateway listens on `127.0.0.1:18789` (loopback only) and is exposed securely via Tailscale Serve (HTTPS, automatic cert).

**Repository:** `CognitiveStack/pi4` (private) — infrastructure and setup docs
**Agent workspace:** `CognitiveStack/hugo` (private) — Hugo's identity, memory, skills, and config

---

## Who Is Hugo?

Hugo is the OpenClaw agent instance. He is the *personality layer* on top of the OpenClaw runtime.

```
OpenClaw runtime  ←→  Hugo agent workspace (~/.openclaw/workspace/)
     (engine)               (soul, rules, memory, tools)
```

| Property | Value |
|----------|-------|
| Name | Hugo 😎 |
| Phone | +27639842638 (MTN SIM, dedicated) |
| Email | hugo@cogstack.co.za |
| Channel | WhatsApp (primary), responds only to Charles (+27836177469) |
| Vibe | Casual, sharp, no-nonsense. Skips filler. Has opinions. |
| Phase | Phase 2 — HTTP + Browser enabled |

Hugo wakes up fresh each session. His continuity comes from markdown files in his workspace:
- `SOUL.md` — who he is
- `USER.md` — who he's helping (Charles)
- `memory/YYYY-MM-DD.md` — daily logs
- `MEMORY.md` — curated long-term memory (main session only, never in group chats)

---

## Hugo's Role in Lead Generation

### The Vision

Hugo is the **autonomous scraping brain** for `cogstack-leadgen`. His job is to discover South African individuals and companies that are high-probability vehicle tracking prospects, enrich them with AI-generated analysis, and POST them as structured lead batches to the n8n webhook.

This is an unconventional approach: instead of writing traditional scraping scripts, the AI *is* the scraper. Hugo reasons about pages, extracts structured data, evaluates prospects, and decides what to send — all autonomously.

### Current State (as of 2026-03-14)

Hugo is in **Phase 2 (HTTP + Browser enabled)**. The B2C skill is live and has completed its first successful run (6 leads created, 1 duplicate skipped).

**Available tools (confirmed):** `read, write, edit, exec, process, web_search, web_fetch, browser, canvas, nodes, cron, message, gateway, agents_list, sessions_list, sessions_history, sessions_send, subagents, session_status, image, memory_search, memory_get, pdf, whatsapp_login, tts`

**HTTP allowlist:**
- `https://n8n.bigtorig.com/webhook/lead-ingestion-v2` — B2B pipeline
- `https://n8n.bigtorig.com/webhook/b2c-lead-ingestion` — B2C pipeline
- `http://localhost:8080` — SearXNG (unreliable — see Known Issues)

**Both B2B and B2C pipelines are live and validated.** Hugo has posted real batches to both webhooks.

### Actual Data Flow (B2C, current)

```
Hugo (OpenClaw on Pi4)
    │
    │  1. web_search tool (Brave API) — discovery queries per source
    │  2. web_fetch — fetch individual post/review/ad pages
    │  3. LLM extraction subagent (openrouter/openai/gpt-4o-mini)
    │     extracts fields + scores (intent_strength, urgency_score)
    │  4. URL filter — reject news articles, category pages (see SKILL.md)
    │  5. Composite Score filter — discard if score < 6
    │  6. POST batch to n8n webhook
    │  7. Log response + WhatsApp report to Charles
    ▼
n8n Webhook (https://n8n.bigtorig.com/webhook/b2c-lead-ingestion)
    │  Authorization: Bearer <B2C_WEBHOOK_TOKEN>
    ▼
Notion B2C Leads DB → QA Review (Claire) → B2C Call Centre
```

---

## Known Issues & Workarounds

### SearXNG — Mostly Broken (2026-03-14)

SearXNG runs at `http://localhost:8080` (Docker on Pi4) but is effectively unusable for lead gen:

| Engine | Status |
|--------|--------|
| Brave | Suspended: too many requests (rate-limited) |
| DuckDuckGo | Suspended: CAPTCHA |
| Startpage | Suspended: CAPTCHA |
| Yandex | Suspended: CAPTCHA |

**Workaround:** Hugo now uses the `web_search` tool (Brave API directly) for discovery instead of SearXNG. This bypasses the engine suspension entirely. SearXNG is left running but not used.

### Gumtree — Blocked by Bot Protection

Gumtree blocks both headless Chromium (browser tool) and direct HTTP requests. The block is **PerimeterX / Cloudflare Bot Management** — it fingerprints TLS handshake, request timing, and browser entropy, not just the User-Agent string.

Hugo's browser tool cannot set the network-level User-Agent header (only in-page JS spoofing, which doesn't help at the edge).

**Current status:** Gumtree is **Phase 3 stretch goal**. Options when we return to it:
- Playwright + `playwright-stealth` plugin (install via npm on Pi4)
- Residential proxy (most reliable, adds cost)
- Manual seed: Charles periodically pastes Gumtree URLs into chat for Hugo to process

**Why Gumtree matters:** It's the only Phase 2-accessible source where phone numbers appear directly on the page. All other sources (Hellopeter, MyBroadband, Reddit, OLX) yield usernames/handles at best.

### Hellopeter — Query Pattern Needs Work

Brave search for Hellopeter tends to return the Cartrack company page, not individual review URLs. Need query patterns that force review-level URLs (e.g. include the review ID pattern in the query).

---

## Model Strategy for Lead Generation

Hugo's model strategy is budget-conscious. Key rule: **never use Claude for routine work, never use direct Anthropic API** (all Claude access goes via OpenRouter).

| Task | Model | Route |
|------|-------|-------|
| Daily WhatsApp chat / heartbeats | DeepSeek v3 | OpenRouter |
| Routine subagent tasks | DeepSeek v3 | OpenRouter |
| Local fallback (OpenRouter down) | qwen2.5:14b via Ollama (desktop) | Local |
| **B2C enrichment subagent** | **gpt-4o-mini** | **OpenRouter** |
| Premium manual tasks | Claude Sonnet 4.6 | OpenRouter |

**Why gpt-4o-mini for enrichment:** Cheapest capable model for structured JSON extraction (~$0.15/$0.60 per M tokens). Excellent at following exact output schemas. No Anthropic credit dependency — routes through OpenRouter.

### Subagent Pattern

```
Hugo main session (DeepSeek v3)
    │
    ├─► web_search for each source query
    │
    ├─► web_fetch each candidate URL
    │
    └─► Subagent (openrouter/openai/gpt-4o-mini)
            ├── Reads page text
            ├── Extracts: name, phone, email, province, city, vehicle
            ├── Writes intent_signal (verbatim quote)
            ├── Scores intent_strength + urgency_score (0-10)
            ├── Writes call_script_opener
            └── Returns structured JSON (_meta.llm_used: true)
    │
    └─► Hugo POSTs enriched batch to n8n webhook
```

---

## B2C Skill

The B2C lead generation skill is live and version-controlled in this repo.

| Location | Path |
|----------|------|
| Source of truth | `skills/cogstack-b2c-leadgen/SKILL.md` (this repo) |
| Deployed to Pi4 | `~/.openclaw/workspace/skills/cogstack-b2c-leadgen/SKILL.md` |
| Runner script | `~/.openclaw/workspace/scripts/b2c_run.py` |
| Run logs | `~/.openclaw/workspace/memory/b2c-run-YYYY-MM-DD.json` |
| State tracking | `~/.openclaw/workspace/memory/b2c-state.json` |

**Current skill version:** 1.2

**Trigger:** WhatsApp `"Hugo, B2C leads"` or HEARTBEAT.md schedule (2-3x/week)

**URL qualification rules (per source):**

| Source | Accept | Reject |
|--------|--------|--------|
| MyBroadband | `/forum/threads/…` | `/news/…`, category pages |
| Reddit | `/r/southafrica/comments/…` | subreddit root, news links |
| Hellopeter | `/[company]/reviews/[id]` | company root, search results |
| OLX | specific wanted ad URL | `/ads/…` listing pages |

**Dedup:** keyed on `intent_source_url` — webhook auto-skips duplicates.

**Environment variables on Pi4 (`~/.env`):**
```bash
B2C_WEBHOOK_URL=https://n8n.bigtorig.com/webhook/b2c-lead-ingestion
B2C_WEBHOOK_TOKEN=1951a0fc...  # same token as B2B
B2C_DATE_AFTER=2026-02-14      # 30-day rolling window
COGSTACK_WEBHOOK_URL=https://n8n.bigtorig.com/webhook/lead-ingestion-v2
COGSTACK_WEBHOOK_TOKEN=1951a0fc...
```

**Deploy command** (from this repo, pre-approved in `.claude/settings.local.json`):
```bash
cp skills/cogstack-b2c-leadgen/SKILL.md /tmp/b2c_skill.md
scp /tmp/b2c_skill.md pi4:/tmp/b2c_skill.md
ssh pi4 "cp /tmp/b2c_skill.md ~/.openclaw/workspace/skills/cogstack-b2c-leadgen/SKILL.md"
```

---

## Security

Hugo has an 8-layer security model. Relevant to lead gen:

| Layer | Current behaviour |
|-------|------------------|
| Shell execution | Requires manual approval via OpenClaw dashboard (exec approve button) |
| Browser tool | Available — Chromium headless. Gumtree/PerimeterX sites still block it |
| File writes | Limited to `~/.openclaw/workspace/` |
| WhatsApp allowlist | Charles only can trigger scraping runs |
| Prompt injection defence | Scraped page content wrapped in `EXTERNAL_UNTRUSTED_CONTENT` block — Hugo correctly ignores instructions in scraped content |

The `EXTERNAL_UNTRUSTED_CONTENT` wrapper is working as intended — Hugo's security notice on scraped content is correct behaviour, not a bug.

---

## Phase Roadmap

### Phase 1 (Complete) — Supervisor Mode
- Hugo exists, WhatsApp connected, heartbeat running
- No shell/browser/external API access

### Phase 2 (Current) — HTTP + Browser enabled
- `web_search` (Brave API) for discovery — working
- `web_fetch` for page content — working
- `browser` tool available — Chromium headless (Gumtree blocked)
- LLM enrichment subagent (gpt-4o-mini via OpenRouter) — working
- B2C skill live, first run successful (6 leads, 1 duplicate skipped)
- Exec approval still required for shell commands (main friction point)

### Phase 3 — Scheduled Autonomy + Gumtree
- Remove exec approval requirement (graduate SYSTEM.md)
- Add B2C run to HEARTBEAT.md schedule (2-3x/week)
- Tackle Gumtree blocking: Playwright stealth or residential proxy
- Expected uplift: 2-5 phone-verified leads per run

### Phase 4 — Feedback Loop
- Claire's QA rejections feed back to Hugo's scoring criteria
- Hugo tunes itself based on what Claire approves/rejects

---

## Key Files Reference

| File | Location | Purpose |
|------|----------|---------|
| `SYSTEM.md` | `CognitiveStack/hugo` | Hard rules; edit to graduate phases |
| `SOUL.md` | `CognitiveStack/hugo` | Hugo's character and working style |
| `HEARTBEAT.md` | `CognitiveStack/hugo` | Scheduled tasks; add B2C lead gen trigger here |
| `model-strategy.md` | `CognitiveStack/hugo` | Model selection rules and budget |
| `TOOLS.md` | gateway workspace | Infrastructure cheat sheet + API discovery |
| `skills/cogstack-b2c-leadgen/SKILL.md` | this repo + Pi4 | B2C lead gen playbook (source of truth here) |
| `scripts/b2c_run.py` | Pi4 workspace | B2C runner script (LLM enrichment pass active) |
| `memory/b2c-run-*.json` | Pi4 workspace | Per-run logs |
| `memory/b2c-state.json` | Pi4 workspace | Run state / submitted URL tracking |
| `n8n_b2c_code_node.js` | this repo | n8n Code node Hugo POSTs to |
| `.env` (Pi4) | `~/.env` on Pi4 | Webhook URLs + tokens + date window |
