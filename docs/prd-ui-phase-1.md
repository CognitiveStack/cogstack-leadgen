# CogStack Leadgen — UI Phase 1 PRD



**Status:** Draft v2.0 — 2026-05-01

**Owner:** Charles Vosloo

**Primary user:** Claire Shuttleworth (call centre manager / business partner)

**Secondary user:** Charles (operator / developer)

**Deployment target:** `leads.bigtorig.com`

**Repo:** `github.com/CognitiveStack/cogstack-leadgen`

**Branch:** `feat/ui-phase-1`



> **About this PRD.** This is the second iteration. The original PRD (now archived

> at `docs/prd-ui-phase-1-v1.md`) framed Phase 1 as a read-only dashboard for QA-ing

> scraped B2C consumer leads. Mid-implementation it became clear the real workflow

> is throughput-focused operations on small-business prospects, with WhatsApp outreach

> as the primary qualification mechanism. PRD-v2 reflects that reality.



---



## 1. Vision



The UI is an **operations console** for the prospect-to-lead pipeline that already

exists across Notion, Baileys (WhatsApp), and Charles's existing scripts. The UI

does not replace any of those — it provides a focused, Claire-friendly surface

where the daily decisions and actions of the workflow happen.



### What this UI is



- A place where Claire (and Charles) can **see** the state of the pipeline at a glance

- A place where they can **take actions** — send WhatsApp outreach batches, look up

  numbers, mark prospects as sent to Cartrack, ingest new lists

- A **methodology-forcing tool** — every button, every filter, every page is a

  small commitment to "this is how the workflow runs," replacing the ad-hoc

  claude-code-in-tmux orchestration with a deterministic surface



### What this UI is NOT



- Not a Notion replacement (Notion stays as the data store and Charles's

  power-user surface)

- Not a complete CRM (specific use cases, not generic functionality)

- Not multi-tenant (single-client, Cartrack-specific assumptions live in config)

- Not a scraper (scraping continues to run on desktop-wsl on existing schedule)



### Core nomenclature



The UI introduces and standardizes on this distinction:



| Term | Meaning |

|---|---|

| **Prospect** | Any contact in the database identified as potential — someone whose phone or name we have, who *might* want vehicle tracking |

| **Lead** | A prospect who has affirmatively responded ("YES" via WhatsApp outreach) — ready to be sent to the Cartrack call centre |

| **Batch** | A group of prospects ingested or processed together (an Excel upload, a scraping run, a WhatsApp send batch) |

| **Source** | Where a prospect originated (HelloPeter, Gumtree, Claire's submission, etc.) |

| **Outreach** | The WhatsApp message sent to qualify a prospect into a lead |



> The UI uses `Prospect` consistently in its display labels, even though Notion

> currently has DBs named `B2B Leads`, `B2C Leads`, `Claire-Prospects`. Renaming

> the Notion DBs is deferred to Phase 1.1 housekeeping; the UI translates internally.



---



## 2. Phase 1 Scope



### Five capabilities Phase 1 ships



1. **Unified prospect view** across all 3 prospect DBs (B2B, B2C, Claire-Prospects)

2. **Phone dedupe search** — answer "is this number already in the pipeline?" instantly

3. **WhatsApp lookup button** — query Baileys for the WhatsApp display name of a number

4. **WhatsApp outreach button** — send templated outreach messages, bulk (max 40)

5. **Guided ingest** — Excel/XML/CSV upload, preview, push to Notion via existing n8n



Plus three supporting features:



6. **Status updates** — mark prospect as "Sent to Cartrack", change Response Status

7. **Help / instructions section** — workflow guide, glossary, Notion crash course

8. **Counts dashboard** — leads in / outreach sent / sent-to-Cartrack throughput



### Explicitly NOT in Phase 1



- ❌ Editing the WhatsApp outreach message template in-UI (display + link to source only)

- ❌ Documentation-helper agent (deferred to Phase 2)

- ❌ Notion-MCP query agent (deferred to Phase 2)

- ❌ Workflow-orchestration agent (deferred to Phase 3)

- ❌ Buy-list ingestion (Phase 3 — but the ingest workflow is the foundation)

- ❌ HelloPeter inbound replies channel (Phase 2 / separate project)

- ❌ Renaming Notion DBs to match prospect/lead nomenclature (Phase 1.1 housekeeping)

- ❌ Mobile-optimized UI (works on mobile, but desktop-first design)

- ❌ B2C source comparison analytics (the v1 dashboard's headline)

- ❌ Multi-client / multi-tenant features



### Why these choices



The five core capabilities each map to **existing functionality** that Charles has been

running manually via claude-code or scripts:



| Capability | Existing implementation being wrapped |

|---|---|

| Unified view | Notion API queries Charles already runs |

| Phone dedupe | Notion property filter Charles uses ad-hoc |

| WhatsApp lookup | `/lookup` endpoint on Baileys (`/opt/projects/whatsapp-lookup/`) |

| WhatsApp outreach | `scripts/whatsapp_outreach.py` (already in repo) |

| Guided ingest | n8n webhook + manual Excel/XML conversion currently done by Charles |



**Phase 1 invents nothing.** It packages five existing-but-scattered capabilities

into a single Claire-friendly surface. This is the cheapest, lowest-risk Phase 1

that delivers real workflow value.



---



## 3. Stack



| Layer | Choice | Rationale |

|---|---|---|

| Backend | FastAPI | Project preference, async-native |

| Frontend | HTMX + Jinja2 templates | Single repo, server-rendered, no build step |

| Styling | Tailwind CSS via CDN | No build pipeline; swap to compiled later if needed |

| Python deps | `uv` exclusively | Project preference — never pip |

| Notion access | `httpx` async client | Standard for FastAPI, already in pyproject from Step 1 |

| WhatsApp ops | `httpx` calls to existing Baileys service (port 3456) | Existing service, no changes needed |

| Tests | pytest + httpx AsyncClient | Standard |

| Reverse proxy | Caddy (existing on bigtorig) | Adds one site block to existing Caddyfile |

| Container | Docker Compose, joins `caddy-shared` external network | Pattern A — repo-owned compose |

| Auth | Caddy basic auth | Phase 1 — magic links in Phase 2 |



### What we're NOT using



- ❌ React / Next.js / Vue (revisit only if HTMX hits a wall)

- ❌ Tailwind build pipeline (CDN sufficient for Phase 1)

- ❌ Postgres for the UI's own state (Notion is the DB; in-memory cache for short-lived state)

- ❌ Redis (in-memory cache is enough for Phase 1; Redis revisit if/when needed)

- ❌ A separate auth service (Caddy handles auth)



---



## 4. Architecture



### High-level diagram



```

                   Cloudflare DNS

                         │

                         ▼

              leads.bigtorig.com

                         │

                         ▼

┌─────────────────────────────────────────────────────────────────┐

│  bigtorig                                                       │

│                                                                 │

│  /opt/infra/local-ai-packaged/                                  │

│    └─ Caddyfile  ← add 1 site block for leads.*                 │

│                                                                 │

│  Network: caddy-shared (external, joined by both)               │

│    ├─ caddy                                                     │

│    └─ cogstack-ui  ← NEW                                        │

│                                                                 │

│  /opt/services/cogstack-leadgen/   ← repo cloned here           │

│    ├─ docker-compose.yml  (joins caddy-shared as external)      │

│    └─ apps/ui/  →  FastAPI + HTMX container                     │

│         ├─ Reads:  Notion API (read-only token)                 │

│         ├─ Writes: Notion API (write token, scoped)             │

│         ├─ Calls:  Baileys (port 3456 — lookup + send)          │

│         └─ Triggers: n8n webhook (existing ingest pipeline)     │

│                                                                 │

│  Existing services (untouched):                                 │

│    ├─ n8n         (webhooks, Notion writes)                     │

│    ├─ baileys     (port 3456 — WhatsApp Phone 3)                │

│    └─ ...          (other services on caddy-shared)             │

└─────────────────────────────────────────────────────────────────┘

                         │

                         ▼ Notion API (HTTPS)

              ┌──────────────────────┐

              │  Notion CRM          │

              │  (5 DBs introspected)│

              └──────────────────────┘

```



### Pattern A — repo-owned compose, joins external network



The new UI service's `docker-compose.yml` lives in the leadgen repo and joins

`caddy-shared` as an `external: true` reference. The only change to

`/opt/infra/local-ai-packaged/Caddyfile` is one new site block:



```

leads.bigtorig.com {

    encode zstd gzip

    basic_auth {

        claire <bcrypt-hash-set-by-charles>

    }

    reverse_proxy cogstack-ui:8000

}

```



The UI container exposes port 8000 only on the docker network (no host binding),

matching how `n8n`, `flowise`, etc. are exposed.



### Two Notion integrations — credential separation



The UI uses **two** Notion integrations with different capability sets:



1. **`cogstack-leadgen-readonly`** (already exists from Step 1)

   - Capabilities: Read content only

   - Used for: dashboard counts, search, list views — the bulk of the UI

   - Env var: `NOTION_READONLY_TOKEN`



2. **`cogstack-leadgen-write`** (new — Charles to create)

   - Capabilities: Read content, Update content, Insert content

   - Used for: status updates, prospect creation from ingest, response logging

   - Env var: `NOTION_WRITE_TOKEN`



The codebase NEVER reads `NOTION_API_KEY` (the existing scraper key with full

workspace access). Defense-in-depth at the integration capability level: the

read paths can't accidentally write, the write paths only have the capabilities

they need.



Both integrations need to be shared with the same 5 DBs.



### Service interactions



| What the UI does | How |

|---|---|

| Read prospect lists | Notion API GET via `NOTION_READONLY_TOKEN` |

| Search by phone | Notion API filter via `NOTION_READONLY_TOKEN` |

| Lookup WhatsApp name | HTTP POST to `http://baileys:3456/lookup` |

| Send WhatsApp message (single) | HTTP POST to `http://baileys:3456/send` |

| Send WhatsApp batch | Sequential calls to `/send` with jitter (mirrors existing script) |

| Update prospect status | Notion API PATCH via `NOTION_WRITE_TOKEN` |

| Ingest spreadsheet | Parse → preview → POST to existing n8n webhook |



n8n stays the central writer for ingestion. The UI doesn't bypass n8n; it

provides a friendlier front door to the same webhook the manual claude-code

flow has been using.



---



## 5. Repo Layout



### Paths



| Context | Path |

|---|---|

| Dev (desktop-wsl) | `~/cogstack-leadgen/` |

| Deploy (bigtorig) | `/opt/services/cogstack-leadgen/` |

| Caddyfile (bigtorig) | `/opt/infra/local-ai-packaged/Caddyfile` — gets one new site block |

| Docker network | `caddy-shared` (external reference) |



### Tree (additions to existing repo)



```

cogstack-leadgen/

├── apps/                         # NEW

│   └── ui/                       # the operations console

│       ├── pyproject.toml

│       ├── src/cogstack_ui/

│       │   ├── __init__.py

│       │   ├── main.py           # FastAPI app

│       │   ├── config.py         # env-driven config

│       │   ├── notion/

│       │   │   ├── client.py     # async Notion wrapper

│       │   │   ├── schema.py     # generated by introspect_notion.py

│       │   │   ├── queries.py    # typed query helpers

│       │   │   └── writes.py     # write-path helpers (uses NOTION_WRITE_TOKEN)

│       │   ├── baileys/

│       │   │   └── client.py     # WhatsApp lookup + send wrappers

│       │   ├── routes/

│       │   │   ├── dashboard.py

│       │   │   ├── prospects.py

│       │   │   ├── outreach.py   # WhatsApp send endpoints

│       │   │   ├── ingest.py

│       │   │   ├── help.py

│       │   │   └── partials.py   # HTMX fragment endpoints

│       │   └── templates/

│       │       ├── base.html

│       │       ├── dashboard.html

│       │       ├── prospects/

│       │       ├── ingest/

│       │       ├── help/

│       │       └── partials/

│       ├── tests/

│       ├── Dockerfile

│       └── README.md

├── docs/help/                    # NEW — rendered at /help

│   ├── overview.md

│   ├── workflow-walkthrough.md

│   ├── glossary.md

│   ├── notion-crash-course.md

│   └── faq.md

├── deploy/                       # NEW

│   └── Caddyfile.leads-block     # snippet for human review, NOT auto-applied

├── docker-compose.yml            # NEW — joins caddy-shared

├── scripts/                      # existing, untouched

│   ├── introspect_notion.py      # extended to include Claire-Prospects

│   ├── whatsapp_outreach.py

│   └── ...

└── docs/

    ├── prd-ui-phase-1.md         # this file

    ├── prd-ui-phase-1-v1.md      # archived

    └── ...

```



The existing scrapers, `whatsapp_outreach.py`, n8n workflow files, and root-level

scripts remain untouched.



---



## 6. Notion Source of Truth



### Five databases introspected



| DB | Notion ID | Purpose |

|---|---|---|

| B2C Leads | `32089024-cd3d-812e-a6c6-d8e21d9126b3` | B2C consumer prospects (scraped) |

| B2C Batches | `32089024-cd3d-81a7-8691-ca999aa1494f` | B2C ingestion batches |

| B2B Leads | `30b89024-cd3d-810a-bb28-e46825320802` | B2B prospects (scraped or submitted) |

| Claire-Prospects | `34189024-cd3d-8108-bd69-ce41ebfa2eb2` | Claire-submitted small-business prospects |

| Sources | `30b89024-cd3d-81b1-ab3a-c900965b5d64` | Source tracking |



The 3 prospect DBs (B2C, B2B, Claire-Prospects) have the same logical shape and

will display in the unified `/prospects` view.



### Schema introspection



The existing `scripts/introspect_notion.py` (committed in Step 1) is the

authoritative tool for generating typed Pydantic models from these DBs. Step 1

follow-up: add Claire-Prospects to its `DATABASES` dict.



The output `apps/ui/src/cogstack_ui/notion/schema.py` is the **typed contract**

all UI code imports from. Re-run the script whenever Notion property definitions

change.



### Why we don't read `notion_config.json`



`notion_config.json` is a legacy config file used by older scripts. We've

discovered it had stale data (the Sources DB ID was wrong; fixed now). New code

should NOT read from it. The introspection script's `DATABASES` dict +

generated `schema.py` is the canonical source of DB identifiers in the new UI.



---



## 7. Pages



### `/` — Dashboard



The opening view. Counts at a glance:



- Prospects in pipeline (today / this week / total)

- Outreach messages sent (today / this week / total)

- Replies received (YES / NO / MAYBE / Pending — today / this week)

- Leads ready to send to Cartrack (count)

- Sent to Cartrack (today / this week / total)

- Recent batches (last 5 ingest events)



Single page, all counts. No charts. Numbers + sparklines if useful.



### `/prospects` — Unified prospect table



The headline page. Renders prospects from B2C, B2B, and Claire-Prospects DBs in

one table.



Columns (default visible):

- Name

- Business (if applicable)

- Phone

- Source (DB-of-origin shown as a tag)

- Outreach Sent? (Y/N + date)

- Response Status (Pending / YES / NO / MAYBE / No Reply)

- Sent to Cartrack? (Y/N + date)

- Date Added



Filters:

- DB of origin (B2C / B2B / Claire-Prospects / All)

- Outreach status (sent / not sent / pending response)

- Response status

- Sent-to-Cartrack status

- Source (HelloPeter / Gumtree / Manual / etc.)

- Date range



**Search bar at the top: phone-number search.** Type any phone format → instant

dedupe answer. Headline feature.



Click a row → `/prospects/{id}`.



### `/prospects/{id}` — Prospect detail



Read view of all properties for a single prospect, plus action buttons:



**Action buttons:**

- **WhatsApp Lookup** — query Baileys, show resolved name + WA-existence flag

- **Send WhatsApp Outreach** — send single outreach message (template + this prospect's data)

- **Mark Sent to Cartrack** — toggle the status field

- **Edit Status** — dropdown to change Response Status



Bottom of page: link "Open in Notion" → opens the Notion deep link.



### `/outreach` — WhatsApp outreach hub



Two parts:



**Part 1: Bulk send**

- Select prospects (checkbox in `/prospects` table feeds this)

- Show preview: "About to send to N prospects" (default max 40, configurable)

- Show the message template that will be used (read-only display)

- Click "Send Batch" → progress indicator → results summary (sent / failed / skipped)



**Part 2: Template management (Phase 1 = read-only display)**

- Show current template

- Show source file path (`scripts/whatsapp_outreach.py`)

- Note: "To edit the template, modify the source file and redeploy. Inline

  editing is a Phase 2 feature."



### `/ingest` — Spreadsheet upload



The "kill the email-Charles loop" feature.



Steps the user goes through:

1. **Choose target DB** — Claire-Prospects / B2B / B2C

2. **Drag-drop file** — Excel (.xlsx), CSV, or XML

3. **Format guidance shown inline** — required columns listed before upload

4. **Preview** — system parses the file, shows N rows mapped to Notion fields

5. **Validation errors highlighted** — wrong columns, bad phone numbers, duplicates against existing DB

6. **Click "Submit to Notion"** → POST to existing n8n webhook → confirmation

7. **Result summary** — N created, N skipped (with reasons)



Behind the scenes: this calls the *existing* n8n webhook

(`https://n8n.bigtorig.com/webhook/lead-ingestion-v2` or its B2C cousin). The

UI is a friendlier surface; n8n still does the writing.



### `/batches` — Ingest history



Last 30 days of ingest batches:

- Date, source, target DB, N records, success/failure

- Click → see the records in that batch



### `/sources` — Source effectiveness



For each source (HelloPeter, Gumtree, Manual, Exa, etc.):

- Total prospects from this source

- Outreach sent rate

- Response rate (YES / NO / MAYBE)

- Conversion rate to leads

- Conversion rate to "sent to Cartrack"



The question this page answers: **which sources are worth investing in?**



### `/help` — Workflow guide and documentation



Renders Markdown files from `docs/help/`. Sections:

- **Overview** — what this UI is for, who uses it

- **Workflow walkthrough** — "how to send a WhatsApp batch", "how to ingest Claire's spreadsheet", etc.

- **Glossary** — prospect, lead, batch, etc.

- **Notion crash course** — what the 5 DBs are, when to look at each

- **FAQ** — common questions



Edits happen by modifying `docs/help/*.md` files in the repo. The UI hot-reads

them on each page load (no rebuild needed).



This section is the **single source of truth** for documentation. Existing

docs (`claire-onboarding.md`, `whatsapp-outreach-process.md`, etc.) eventually

migrate here.



---



## 8. Acceptance Criteria — Phase 1



We declare Phase 1 done when:



- [ ] All 5 DBs introspected; `schema.py` generated and committed

- [ ] Two Notion integrations (read-only + write) created and shared with 5 DBs

- [ ] FastAPI + HTMX scaffold builds, runs locally, passes a smoke test

- [ ] Docker Compose joins `caddy-shared` external network successfully

- [ ] Caddyfile site block added; `leads.bigtorig.com` resolves via Cloudflare

- [ ] Caddy basic auth working; Claire's credentials delivered out of band (Bitwarden share)

- [ ] All 7 pages render with live data:

  - [ ] `/` dashboard with real counts

  - [ ] `/prospects` unified table with filters + phone search

  - [ ] `/prospects/{id}` detail view with action buttons

  - [ ] `/outreach` bulk send works (uses existing `whatsapp_outreach.py` logic)

  - [ ] `/ingest` Excel/XML upload works for Claire-Prospects

  - [ ] `/batches` shows recent ingest history

  - [ ] `/sources` shows source effectiveness counts

  - [ ] `/help` renders `docs/help/*.md` files

- [ ] Phone dedupe search returns results in < 2s

- [ ] Bulk WhatsApp send respects the 40-message default max

- [ ] No code path reads `NOTION_API_KEY`; only `NOTION_READONLY_TOKEN` and `NOTION_WRITE_TOKEN`

- [ ] Existing scrapers / `whatsapp_outreach.py` / n8n workflows untouched

- [ ] Charles + Claire have used it for **2 weeks** and recorded:

  - Which pages they actually opened

  - Which actions they took most

  - What they wished they could do (Phase 2 backlog)

  - Whether the email-Charles ingest loop has stopped



---



## 9. Workflow



Continue on `feat/ui-phase-1` branch. The work proceeds in steps:



### Step 1 (mostly done) — Schema introspection



- ✅ `scripts/introspect_notion.py` committed (with `NOTION_READONLY_TOKEN` enforcement, Pydantic output)

- ⏳ Follow-up commit: add `claire_prospects` (`34189024-cd3d-8108-bd69-ce41ebfa2eb2`) to `DATABASES` dict

- ⏳ Run script, generate `apps/ui/src/cogstack_ui/notion/schema.py` (5 DB models)

- ⏳ Commit generated schema



### Step 2 — FastAPI scaffold + dashboard



- Set up `apps/ui/` directory structure

- Configure pyproject.toml

- Wire up FastAPI app, base template, Tailwind CDN

- Build `/` dashboard with live counts

- Build Docker Compose, join `caddy-shared`

- Add Caddyfile snippet to `deploy/`



### Step 3 — Prospects page (the headline)



- `/prospects` unified table

- Filters

- Phone dedupe search

- `/prospects/{id}` detail view (without action buttons yet)



### Step 4 — Action buttons



- WhatsApp lookup button

- Single outreach button

- Mark sent to Cartrack

- Edit status



### Step 5 — Bulk outreach



- `/outreach` page

- Multi-select in `/prospects` feeds the bulk send

- Template display

- Progress indicator

- Result summary



### Step 6 — Ingest



- `/ingest` page

- Excel/XML/CSV parsing

- Preview before submit

- Validation

- POST to n8n webhook

- Result summary



### Step 7 — Supporting pages



- `/batches` history

- `/sources` effectiveness

- `/help` rendered from `docs/help/*.md`



### Step 8 — Deploy + dogfood



- Push to bigtorig

- Caddyfile updated

- DNS confirmed

- Auth credentials shared with Claire

- 2-week dogfood



Each step = one logical commit (or small group of related commits). Each step

gets reviewed before moving on.



---



## 10. Open Questions / Followups



### To resolve during implementation



1. **Caddy basic_auth bcrypt hash** — generated via `caddy hash-password`, placeholder in repo

2. **n8n webhook URLs** — confirm both B2C and B2B/Claire-Prospects webhooks exist; if not, create

3. **Bulk outreach max size** — Phase 1 default 40, configurable in env. Validate against Phone 3 rate limits during dogfood

4. **Mobile usage** — desktop-first, but make sure pages are at least readable on phone



### Out of scope but flagged



5. **`notion_config.json` deprecation** — file is now correct (Sources ID fixed) but is legacy infra debt. New UI doesn't read it. Long-term: migrate remaining scripts off it. Phase 2/3 housekeeping.



6. **Notion DB rename** — `B2B Leads` → `B2B Prospects`, `B2C Leads` → `B2C Prospects` to match UI nomenclature. Defer to Phase 1.1 housekeeping after UI ships.



7. **Documentation migration** — existing docs (`claire-onboarding.md`, `whatsapp-outreach-process.md`, `prd-leadgen-original.md`, etc.) eventually migrate into `docs/help/` as the single source of truth. Phase 1 takes a first pass; full migration organic.



8. **Phase 2 candidates** (not committed):

   - Documentation-helper agent (light Anthropic API integration)

   - Notion-MCP query agent

   - WhatsApp template editor in-UI

   - Magic-link auth replacing basic auth

   - Conversational outreach (`whatsapp_responses.py` integration)

   - HelloPeter inbound replies channel



9. **Phase 3 candidates** (long-term):

   - Buy-list integration (TransUnion / Experian SA) — uses ingest workflow

   - Workflow-orchestration agent

   - Multi-tenant — UI for multiple client companies



---



## 11. Out of Scope (explicit)



To keep Phase 1 bounded:



- ❌ Anything on desktop-wsl (scrapers continue to run there unchanged)

- ❌ n8n workflow changes

- ❌ Baileys service code changes (UI calls existing endpoints)

- ❌ Multi-client / multi-tenant features

- ❌ Mobile-native app

- ❌ Email notifications

- ❌ Slack / Teams integration

- ❌ Renaming Notion DBs (Phase 1.1)

- ❌ B2C source comparison analytics (the v1 dashboard's headline)

- ❌ Approve/reject UI flows (status changes only)

- ❌ Pagination beyond simple offset/limit (Phase 2 if data volume requires)



---



*End of PRD v2.0*
