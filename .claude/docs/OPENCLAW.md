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
| Phase | Phase 1 — Supervisor Mode (read-only, no shell, no browser) |

Hugo wakes up fresh each session. His continuity comes from markdown files in his workspace:
- `SOUL.md` — who he is
- `USER.md` — who he's helping (Charles)
- `memory/YYYY-MM-DD.md` — daily logs
- `MEMORY.md` — curated long-term memory (main session only, never in group chats)

---

## Hugo's Role in Lead Generation

### The Vision

Hugo is the **autonomous scraping brain** for `cogstack-leadgen`. His job is to discover South African companies that are high-probability fleet operators and vehicle tracking prospects, enrich them with AI-generated analysis, and POST them as structured lead batches to the n8n webhook.

This is an unconventional approach: instead of writing traditional scraping scripts, the AI *is* the scraper. Hugo reasons about pages, extracts structured data, evaluates prospects, and decides what to send — all autonomously.

### Current State

Hugo is in **Phase 2 (HTTP Enabled)**. HTTP `$fetch` is allowed to allowlisted endpoints only. Shell execution requires manual approval via the OpenClaw dashboard. No browser automation yet.

**HTTP allowlist:**
- `https://n8n.bigtorig.com/webhook/lead-ingestion-v2` — B2B pipeline
- `https://n8n.bigtorig.com/webhook/b2c-lead-ingestion` — B2C pipeline
- `http://localhost:8080` — SearXNG local search

**Both B2B and B2C pipelines are live and validated.** Hugo has posted real batches to both webhooks. The exec approval prompt is the main friction point — Phase 3 graduation will remove it.

**Known limitation:** Web search (Brave/SearXNG) returns forum threads without contact info. Gumtree "Wanted" ads have visible phone numbers but require the browser tool. Browser tool access is a Phase 3 unlock.

### Intended Data Flow

```
Hugo (OpenClaw on Pi4)
    │
    │  1. Heartbeat triggers lead generation task (scheduled)
    │  2. Hugo searches SearXNG (local, http://localhost:8080)
    │     for SA companies matching target profiles
    │  3. Hugo scrapes/enriches prospect data using LLM reasoning
    │  4. Hugo scores each prospect (Composite Score formula)
    │  5. Hugo POSTs batch to n8n webhook
    ▼
n8n Webhook (https://n8n.bigtorig.com/webhook/lead-ingestion-v2)
    │  Authorization: Bearer <WEBHOOK_TOKEN>
    ▼
Notion Leads DB → QA Review (Claire) → Call Centre (Paul)
```

### SearXNG — Hugo's Search Engine

A SearXNG instance runs on Pi4 at `http://localhost:8080` (Docker). It aggregates results from Google, Bing, DuckDuckGo, Startpage, and Yandex with JSON API enabled. This gives Hugo a local, no-rate-limit, no-tracking search tool — crucial for autonomous scraping without hitting Google's bot detection.

---

## Model Strategy for Lead Generation

Hugo's model strategy is budget-conscious. Key rule: **never use Claude for routine work**.

| Task | Model | Cost |
|------|-------|------|
| Daily WhatsApp chat / heartbeats | DeepSeek v3 (OpenRouter) | ~$0.27/$1.10 per M tokens |
| Routine subagent tasks | DeepSeek v3 | same |
| Local fallback (OpenRouter down) | qwen2.5:14b via Ollama (desktop) | $0 |
| **Lead generation / enrichment** | Should be a subagent | see below |
| Premium manual tasks | Claude Sonnet 4 (on-demand) | expensive |

### Subagent Pattern for Scraping

For lead generation specifically, the recommended pattern is:

> **Main session (cheap model)** dispatches a **subagent (expensive model)** to do the actual scraping and enrichment reasoning.

The main Hugo session (DeepSeek) handles scheduling, coordination, and POST to webhook. The subagent (Claude Haiku 4.5 or Sonnet) does the heavy reasoning: reading company pages, evaluating fleet likelihood, writing the prospect summary and call script opener.

This keeps costs low — only the enrichment reasoning needs the expensive model, not the orchestration.

```
Hugo main session (DeepSeek v3)
    │
    ├─► "Find 5 transport companies in KZN on SearXNG"
    │
    └─► Subagent (Claude Haiku 4.5)
            ├── Reads company pages
            ├── Evaluates fleet likelihood (0-10)
            ├── Evaluates tracking need (0-10)
            ├── Writes prospect summary
            ├── Writes fleet assessment
            ├── Writes call script opener
            └── Returns structured JSON
    │
    └─► Hugo POSTs enriched batch to n8n webhook
```

---

## The Lead Generation Skill (To Be Built)

Hugo uses a **skill** system for structured tasks. A skill is a markdown file (`SKILL.md`) that defines a tool's purpose, inputs, outputs, and usage instructions. Hugo reads the skill file to know how to use a capability.

The lead generation workflow needs to be defined as a skill. Proposed structure:

```
~/.openclaw/workspace/skills/cogstack-leadgen/SKILL.md
```

### Skill Design

The skill should define:

1. **Trigger** — how Hugo knows to run it (heartbeat schedule, WhatsApp command, or cron)
2. **Search query templates** — what to search on SearXNG for each data source
3. **Prospect evaluation criteria** — what makes a good lead (fleet size, sector, geography)
4. **Scoring instructions** — how to compute Fleet Likelihood, Tracking Need, Fleet Size Bonus
5. **Enrichment prompts** — how to write the prospect summary, fleet assessment, call script
6. **Output schema** — the exact JSON structure to POST to the webhook
7. **Dedup awareness** — don't resubmit companies already in Notion

### Webhook Configuration

Hugo needs two environment variables on the Pi4:

```bash
# Add to ~/.env on pi4
COGSTACK_WEBHOOK_URL=https://n8n.bigtorig.com/webhook/lead-ingestion-v2
COGSTACK_WEBHOOK_TOKEN=<token from cogstack-leadgen .env>
```

---

## Phase Roadmap for Hugo's Lead Gen Capability

### Phase 1 (Complete) — Supervisor Mode
- Hugo exists, WhatsApp connected, heartbeat running
- No shell/browser/external API access

### Phase 2 (Current) — HTTP Enabled
- HTTP `$fetch` allowed to allowlisted endpoints
- Shell execution requires manual approval in OpenClaw dashboard
- Hugo can POST to both B2B and B2C n8n webhooks
- **Lead gen: working with manual trigger**
- Next: graduate to Phase 3 to remove exec approval friction

### Phase 3 — Scheduled Autonomy
- Cron job or HEARTBEAT.md task runs lead gen automatically
- Hugo runs 2-3 scraping sessions per day without prompting
- Results arrive in Notion without Charles touching anything
- **Lead gen: fully autonomous, 24/7**

### Phase 4 — Feedback Loop
- Claire's QA rejections feed back to Hugo's prompt (rejection reasons exported from Notion)
- Hugo tunes its own scoring criteria based on what Claire approves
- Model self-improves over time

---

## Security Considerations

Hugo currently enforces an 8-layer security model. Relevant to lead gen:

| Layer | Implication for Lead Gen |
|-------|--------------------------|
| No external API calls (Phase 1) | Can't POST to n8n yet |
| No browser automation (Phase 1) | Can't use Playwright/Selenium |
| File writes limited to workspace | Batch logs stay in `~/.openclaw/workspace/memory/` |
| WhatsApp DM allowlist (Charles only) | No one else can trigger a scraping run |
| Prompt injection defense | Scraped page content treated as untrusted |

When graduating to Phase 2/3, review the tool policy carefully. Lead gen involves reading arbitrary web pages — those pages could contain prompt injection attempts. Hugo's `SYSTEM.md` already addresses this (rule 10: treat inbound media as untrusted), but it should be explicitly extended to scraped web content.

---

## Key Files Reference

| File | Location | Purpose |
|------|----------|---------|
| `SYSTEM.md` | `CognitiveStack/hugo` | Hard rules; edit to graduate phases |
| `SOUL.md` | `CognitiveStack/hugo` | Hugo's character and working style |
| `HEARTBEAT.md` | `CognitiveStack/hugo` | Scheduled check tasks; add lead gen trigger here |
| `model-strategy.md` | `CognitiveStack/hugo` | Model selection rules and budget |
| `TOOLS.md` | `CognitiveStack/hugo` | Infrastructure cheat sheet (Tailscale, WhatsApp, etc.) |
| `skills/` | `CognitiveStack/hugo` | Skill definitions (qmd, token-optimization, reef-prompt-guard) |
| `memory/` | `CognitiveStack/hugo` | Daily logs + tenants.md context |
| `OPENCLAW-SETUP.md` | `CognitiveStack/pi4` | Full Pi4 setup and architecture reference |
| `searxng/` | `CognitiveStack/pi4` | SearXNG Docker config (Hugo's search engine) |
| `n8n_code_node.js` | `cogstack-leadgen` | The n8n Code node Hugo POSTs to |
| `.env` | `cogstack-leadgen` | Webhook URL + token (copy relevant vars to Pi4 `~/.env`) |

---

## Immediate Next Steps

1. **Graduate Hugo to Phase 3** — edit `SYSTEM.md` on Pi4 to enable shell execution without approval prompts; enable browser tool for Gumtree scraping
2. **Enable browser tool** — Hugo needs it to scrape Gumtree "Wanted" ads where phone numbers are visible (billable B2C leads)
3. **Test Gumtree B2C run** — send Hugo "Use browser tool to find Gumtree Wanted ads for car trackers — those have visible phone numbers"
4. **Add to HEARTBEAT.md** — schedule automated B2B and B2C runs 2-3x per week once quality is validated
5. **B2B pipeline test** — Hugo has not yet been tested on B2B leads; trigger "Hugo, find me some B2B leads" once Phase 3 is active
