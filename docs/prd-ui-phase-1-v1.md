# CogStack Leadgen — UI Redesign PRD

**Status:** Draft v0.1 — 2026-04-29
**Owner:** Charles Vosloo
**Primary user:** Claire Shuttleworth (call centre manager, non-technical)
**Deployment target:** `leads.bigtorig.com` (Caddy + Cloudflare)
**Repo:** `github.com/CognitiveStack/cogstack-leadgen`

---

## 1. Vision

Transform the `cogstack-leadgen` repo from a CLI/scripts experiment into a **lightweight, Claire-facing web portal** that surfaces the lead generation pipeline as a usable product.

The portal is a **view and action surface over Notion**, not a parallel datastore. Notion remains the source of truth for all lead data.

### Core insight driving the design

The leadgen pipeline is still experimental — we have not yet converged on the optimal flow. **The UI's job in Phase 1 is to help us discover what works, not to ship a final workflow.** Every design decision should optimise for *learning velocity* over feature completeness.

### Non-goals (Phase 1)

- Multi-tenant architecture (Cartrack-specific assumptions live in config, but the UI is single-client)
- Full CRM replacement (Notion stays as the data store)
- Outbound automation (Phase B WhatsApp send stays scripted for now)
- AI chat layer (deferred to Phase 3)
- Replacing n8n (n8n still receives webhooks and runs ingestion workflows)

---

## 2. Phase 1 Scope — Read-Only Dashboard

Single goal: **Claire can log in and see what's in the pipeline without asking Charles.**

### In scope

- Auth: simple Caddy basic auth
- Lead table view (filterable by status, source, competitor, province)
- Pipeline funnel visualisation (counts at each stage)
- Source breakdown (HelloPeter / Gumtree / Exa / manual)
- Recent batches view (latest spreadsheets ingested, with stats)
- WhatsApp lookup status (read-only — show what Phase A has resolved)
- "Pending QA" highlight — what needs Claire's attention next

### Explicitly NOT in scope (Phase 2+)

- Approving / rejecting leads (Phase 2)
- Spreadsheet ingest UI (Phase 2)
- Triggering WhatsApp send (Phase 2)
- Chat with the agent (Phase 3)

### Why read-only first

- Two weeks of dogfooding tells us what Claire actually clicks vs. what we assumed
- Zero risk of destructive bugs against production Notion data
- Lets us iterate fast on layout / information architecture without state-management rabbit holes
- Forces honest product discovery: if Claire never opens it, the redesign was wrong before we built actions

---

## 3. Stack

| Layer | Choice | Rationale |
|---|---|---|
| Backend | FastAPI | Preferred Python framework |
| Frontend | HTMX + Jinja2 templates | Single repo, server-rendered, no build step |
| Styling | Tailwind CSS via CDN | No build pipeline; swap to compiled later if needed |
| Python deps | `uv` exclusively | Project preference — never pip |
| Data store | Notion API (read-only client in Phase 1) | Source of truth |
| Cache | In-memory (Phase 1), Redis (later if needed) | Notion API rate limits; cache lead lists ~30s |
| Reverse proxy | Caddy on bigtorig | Existing — TLS via Cloudflare |
| Container | Docker Compose | Existing pattern on bigtorig |
| Auth | Caddy basic auth | Phase 1 — magic links in Phase 2 |
| Tests | pytest + httpx | Standard |

### What we're NOT using

- No React / Next.js / Vue (revisit only if HTMX hits a wall)
- No separate auth service (start simple)
- No Postgres yet (Notion is the DB)
- No build step on the frontend

---

## 4. Architecture

```
                   Cloudflare DNS
                         │
                         ▼
              leads.bigtorig.com
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  bigtorig (Hostinger Ubuntu)                                │
│                                                             │
│  /opt/infra/local-ai-packaged/        ← existing, light     │
│    ├─ Caddyfile         (add 1 site block for leads.*)      │
│    ├─ docker-compose.yml                                    │
│    └─ services: caddy, n8n (5678), baileys (3456), …        │
│         └─ docker network: <discovered during Prime>        │
│                                                             │
│  /opt/services/cogstack-leadgen/      ← NEW                 │
│    ├─ docker-compose.yml  (joins ↑ network as `external`)   │
│    └─ apps/ui  →  FastAPI + HTMX container                  │
│                     ├─ Jinja templates                      │
│                     ├─ HTMX endpoints                       │
│                     ├─ Notion API client                    │
│                     └─ Baileys client (read-only)           │
└─────────────────────────────────────────────────────────────┘
                         │
                         │  Notion API (HTTPS)
                         ▼
              ┌──────────────────────┐
              │  Notion CRM          │
              │  CogStack workspace  │
              │  - B2C Leads DB      │
              │  - B2C Batches DB    │
              │  - B2B Leads DB      │
              │  - Sources DB        │
              └──────────────────────┘
```

Pattern A: the repo owns its compose file. The new service joins the existing local-ai-packaged docker network via an `external: true` reference, so Caddy can resolve and route to it without managing the container itself. The only edit to `/opt/infra/local-ai-packaged/` is one new site block in the Caddyfile.

Phase 1 has no path back to desktop-wsl. The UI reads Notion only. Scrapes continue to run on desktop-wsl on their existing schedule and write to Notion via n8n. The UI sees the results.

---

## 5. Repo Layout (proposed)

### Paths

| Context | Path |
|---|---|
| Dev (desktop-wsl) | `~/cogstack-leadgen/` |
| Deploy (bigtorig) | `/opt/services/cogstack-leadgen/` |
| Caddyfile (bigtorig) | `/opt/infra/local-ai-packaged/Caddyfile` — gets one new site block, otherwise untouched |
| Docker network | Joined as `external` reference to the local-ai-packaged network (name discovered in Prime phase) |

Same compose file runs in both dev and prod; differences are env-driven via `.env`.

### Tree

```
cogstack-leadgen/
├── apps/
│   ├── ui/                       # NEW — the portal
│   │   ├── pyproject.toml        # uv-managed
│   │   ├── src/cogstack_ui/
│   │   │   ├── __init__.py
│   │   │   ├── main.py           # FastAPI app
│   │   │   ├── config.py         # env-driven (NOTION_TOKEN, BAILEYS_URL, etc.)
│   │   │   ├── notion/
│   │   │   │   ├── client.py     # async Notion wrapper
│   │   │   │   ├── schema.py     # introspected DB schema
│   │   │   │   └── queries.py    # typed query helpers
│   │   │   ├── routes/
│   │   │   │   ├── dashboard.py
│   │   │   │   ├── leads.py
│   │   │   │   ├── batches.py
│   │   │   │   └── partials.py   # HTMX fragment endpoints
│   │   │   └── templates/
│   │   │       ├── base.html
│   │   │       ├── dashboard.html
│   │   │       ├── leads/
│   │   │       └── partials/
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── README.md
│   └── (future: api/, agent/, etc.)
├── scrapers/                     # existing scraper scripts (keep)
├── pipelines/                    # existing orchestration (keep)
├── docker-compose.yml            # adds ui service
├── PRD.md                        # pointer to active PRDs
├── docs/
│   ├── prd-ui-phase-1.md      # this file
│   └── prd-leadgen-original.md
└── README.md
```

The existing scraper / pipeline code stays untouched in Phase 1.

---

## 6. Notion Source of Truth

The UI reads from these databases:

| DB | Notion ID |
|---|---|
| B2C Leads | `32089024cd3d812ea6c6d8e21d9126b3` |
| B2C Batches | `32089024cd3d81a78691ca999aa1494f` |
| B2B Leads | `30b89024cd3d810abb28e46825320802` |
| Sources | `30b89024cd3d81b1ab3ac900965b5d64` |

### First implementation task: schema introspection

Before writing any UI, write a small script `scripts/introspect_notion.py` that:

1. Connects to each DB above
2. Dumps the property schema (name, type, options for selects)
3. Writes the result to `apps/ui/src/cogstack_ui/notion/schema.py` as typed Python (Pydantic models)
4. Commits this — the schema becomes part of the repo

This gives us a typed contract with Notion that can be regenerated when Claire adds new properties. It also doubles as living documentation of the CRM shape.

---

## 7. Pages — Phase 1

### `/` Dashboard

- Funnel: Pending QA → QA Approved → Sent to Call Centre → Contacted → Converted
- Counts and conversion percentages between stages
- Sparkline: leads ingested per day, last 30 days
- "What needs your attention" panel: count of Pending QA, oldest age in days

### `/leads`

- Paginated table of B2C leads
- Filters: status, source, competitor, province, date range
- Search by name / phone / city
- Click row → `/leads/{notion_page_id}` detail view (read-only)

### `/leads/{id}`

- All Notion properties displayed
- Linked batch (if any)
- WhatsApp resolved name (if Phase A has run)
- Notion deep link ("Open in Notion")

### `/batches`

- List of recent ingestion batches
- Per batch: date, source, count, success / failure, link to leads in batch

### `/sources`

- HelloPeter / Gumtree / Exa / manual
- Volume per source over time
- Conversion rate per source — *the question this UI exists to answer*

---

## 8. Acceptance Criteria — Phase 1

We declare Phase 1 done when:

- [ ] Claire can log in at `leads.bigtorig.com` with credentials sent to her
- [ ] Dashboard loads in under 2s on a cold cache
- [ ] All 5 pages above render with live Notion data
- [ ] No write operations to Notion exist anywhere in the codebase (enforced by using a read-only Notion integration token)
- [ ] Repo cloned to `/opt/services/cogstack-leadgen/` on bigtorig
- [ ] `docker-compose.yml` joins the local-ai-packaged external network and exposes only the internal port (no published ports — Caddy reaches it via the docker network)
- [ ] Caddyfile at `/opt/infra/local-ai-packaged/Caddyfile` updated with `leads.bigtorig.com` block + basic auth
- [ ] Cloudflare DNS for `leads.bigtorig.com` resolves
- [ ] `README.md` documents how to run locally and deploy
- [ ] Charles and Claire have used it for **2 weeks** and recorded:
  - Which pages they actually opened
  - Which filters they actually used
  - What they wished they could do (this becomes Phase 2 backlog)

---

## 9. Phase 2 Preview (do not build yet)

Driven by what dogfooding reveals. Likely candidates:

- Spreadsheet drag-drop ingest (eliminates the "Claire emails Charles" loop)
- Approve / reject / status-change actions
- "Trigger WhatsApp outreach" button (requires Phase B `/send` endpoint on Baileys)
- Notion write paths
- Magic-link auth (replaces basic auth)

## 10. Phase 3 Preview

- Chat layer: fresh Anthropic API integration, scoped to leadgen domain
- Tools: `query_leads`, `ingest_spreadsheet`, `send_whatsapp`, `scrape_hellopeter`, `enrich_with_exa`
- Chat history feeds Phase 4 menu items — the "chat history is product roadmap" loop

---

## 11. Workflow

This PRD is designed to be consumed by `/piv`:

```bash
cd ~/cogstack-leadgen
# in Zed agent panel:
/piv UI redesign Phase 1 — read-only dashboard per docs/prd-ui-phase-1.md
```

The `/piv` command will:

1. **Prime** — read this PRD + introspect existing repo
2. **Implement** — scaffold `apps/ui/`, build pages, add Docker Compose service
3. **Validate** — tests, lint, type-check, deploy to bigtorig staging

Once the scaffold lands, use `/implement` for individual pages and features. One PR per page (`/leads`, `/batches`, etc.) keeps reviews tight. Conventional commits throughout.

---

## 12. Open Questions / Assumptions

To resolve before / during the `/piv` Prime phase:

1. **local-ai-packaged docker network name** — discover by inspecting `/opt/infra/local-ai-packaged/docker-compose.yml` on bigtorig. Will be referenced as `external: true` in the new repo's compose file. *(Prime phase, first task.)*
2. **Notion read-only token** — does a read-only integration exist, or does one need to be created in Notion settings? *(Action: create one before starting.)*
3. **Claire's auth credentials** — basic auth username/password generated and delivered out of band (Bitwarden share?) to `claire@4dtherapy.co.za`?
4. **Existing `apps/` directory** — does the repo already have one, or is this a new top-level dir? *(Check during Prime — current `git log` suggests no, but verify.)*
5. **B2B leads** — Phase 1 includes the B2B Leads DB ID, but does the UI need a B2B view, or is Phase 1 strictly B2C?
6. **Mobile usage** — does Claire access this on phone or desktop primarily? Affects how aggressively we mobile-optimise.
7. **Deployment ergonomics** — do we want a `staging.leads.bigtorig.com` for trying changes before Claire sees them, or is the dogfooding tight enough that prod-only is fine?
8. **Caddy basic auth credentials** — bcrypt hash generated via `caddy hash-password` and stored where? Suggestion: keep the hash inline in the Caddyfile, store the plaintext only in Bitwarden.

---

## 13. Out of Scope (explicit)

To keep the list short and the work bounded, the following are NOT touched by Phase 1:

- Anything on desktop-wsl
- n8n workflow changes
- Baileys `/send` endpoint (Phase 2 dependency, separate work)
- Multi-tenant / multi-client portal architecture
- Mobile app
- Email notifications
- Slack / Teams integration
- B2B leads UI (DB exists, but no view in Phase 1 unless answer to Q4 above is "yes")

---

*End of PRD v0.1*
