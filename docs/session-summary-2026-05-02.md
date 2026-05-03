# Session Summary — 2026-05-01 → 2026-05-02



**Goal**: Ship Phase 1 of the cogstack-leadgen UI — read & write operations console for B2C/B2B/Claire-Prospects vehicle tracking lead generation, replacing manual Notion + script workflow.



**Outcome**: Steps 1–4 of 8 shipped (typed schema, dashboard, prospects table + phone search, action buttons), deployed live at `https://leads.bigtorig.com` behind Caddy basic_auth (claire + charles users) with Cloudflare proxy. Half of Phase 1 reachable to stakeholders.



**Branch**: `feat/ui-phase-1` at `495fc87`. Not yet merged to `main`.



---



## What shipped



### Step 1 — Schema introspection (commit `e6f9c3b`)



- `scripts/introspect_notion.py` extended to introspect 5 Notion DBs (B2C Leads, B2B Leads, Claire-Prospects, Sources, Batches)

- Generates `apps/ui/src/cogstack_ui/notion/schema.py` with typed Pydantic models for each, including `Literal[...]` for select/status fields

- 5 typed contracts replacing string-keyed dict access throughout the UI



### Step 2 — FastAPI scaffold + dashboard (commit `3a85ba5`)



- `apps/ui/` directory structure with FastAPI app, Jinja2 templates, HTMX, Tailwind CDN

- Multi-stage Dockerfile, non-root user (uid 10001) for hardening

- `docker-compose.yml` joins existing `caddy-shared` external network (Pattern A)

- Async Notion client (`notion/client.py`) with proper context manager + error handling

- Live counts dashboard: B2C 206, B2B 16, Claire 84, Batches 120, Sources 6 (verified end-to-end)



### Step 3 — Prospects unified table + phone dedupe (commit `ff14b3a`)



- `utils/phone.py` — `normalise_phone()` copied from `scripts/whatsapp_outreach.py` (algorithm identical)

- `notion/queries.py` — `ProspectRow` / `ProspectDetail` dataclasses, per-DB shape config (`_DB_CONFIGS`), `list_prospects()` (parallel 3-DB merge sort), `find_by_phone()` (normalize + dual-form expansion + 6 parallel queries + dedupe)

- `routes/prospects.py` — `GET /prospects` (list + `?q=` phone search) and `GET /prospects/{id}` (detail view)

- Templates: search input with three empty states (parse error / no match / generic), DB badges (B2C blue, B2B green, Claire purple), property grid



### Step 4 — Action buttons (commit `495fc87`)



- `baileys/client.py` — async `BaileysClient` with `lookup()` (always real) and `send()` (honors `DRY_RUN`)

- `notion/writes.py` — `update_status()` (B2C/B2B Status PATCH), `mark_submitted_to_pipeline()` (Claire checkbox PATCH), `create_claire_prospect()` (POST mirroring script's `notion_create_record`)

- `whatsapp/templates.py` — `MESSAGE_TEMPLATE` + `build_message()` copy of script's logic (no editing in Phase 1 UI)

- `whatsapp/state.py` — `asyncio.Lock`-guarded read/write of `outreach-state.json` (shared with script for cross-surface idempotency)

- `routes/outreach.py` — 5 POST endpoints for the 3 action workflows (lookup, send-confirm + send, cartrack-confirm + cartrack)

- 5 HTMX partial templates for response rendering

- `templates/prospects/detail.html` — Actions card with three button rows, disabled states for already-sent / no-phone / already-marked



### Deployment (post-commit, manual)



- `https://leads.bigtorig.com` live with Caddy basic_auth

- Two named users: `claire` and `charles` with separate bcrypt-hashed passwords

- Cloudflare orange cloud (DDoS + caching) in front of bigtorig

- `COGSTACK_DRY_RUN=true` (default) — WhatsApp sends log only, Notion writes proceed



---



## Architectural decisions worth remembering



### PRD-v2 supersedes v1

- v1 was a read-only B2C dashboard

- v2 reframed as throughput-focused operations console covering all three DBs

- Key insight: real workflow is small-business prospects with WhatsApp outreach as the primary qualifier



### Two Notion integrations, not one

- `cogstack-leadgen-readonly` — read content only — `NOTION_READONLY_TOKEN`

- `cogstack-leadgen-write` — read + update + insert — `NOTION_WRITE_TOKEN`

- Codebase NEVER uses `NOTION_API_KEY` directly

- Token capability scope enforces blast radius: Steps 1-3 only ever use readonly; Step 4 introduces write paths



### Single repo, dual deployment contexts

- Desktop-WSL runs scrapers, manual orchestration, b2c_run.py

- Bigtorig runs the UI in Docker

- Both clones share the same git remote

- This is intentional, not duplication — different machines do different things



### State.json is source of truth for "was this phone sent to"

- `outreach-state.json` (shared between script and UI via volume mount) records every send

- Notion writes are best-effort — if Notion fails after Baileys succeeds, idempotency still holds via state file

- Atomicity ordering: normalize → idempotency check → Baileys send → state append → Notion write

- Reasoning: a duplicate WhatsApp send to a real human cannot be undone; a missing Notion record can be re-created



### DRY_RUN is the default

- `COGSTACK_DRY_RUN=true` unless explicitly set to `false`

- Skips Baileys `/send` (logs message + returns mock success)

- Notion writes proceed (reversible by Charles)

- State file appends with `dry_run: true` flag for audit

- Production flip is deliberate one-line `.env` change + container restart



### Container hardening

- Non-root user `appuser` (uid 10001) inside container

- Read-only mounts where possible (Caddyfile, skills directories)

- Volume mount for `logs/` requires host-side chown to uid 10001 on first deploy

- Multi-stage Dockerfile, slim runtime image



### Pattern A docker-compose (single repo, external network)

- Repo owns its `docker-compose.yml`

- Joins `caddy-shared` as `external: true`

- Container `expose: 8000` (no host port binding — only Caddy reaches it)

- Caddyfile reverse-proxies to `cogstack-ui:8000` by service name on shared network



### PRD convention

- All PRDs live at `docs/prd-*.md` (kebab-case, never in `.claude/`)

- Active PRD: `docs/prd-ui-phase-1.md` (v2)

- Archived: `docs/prd-ui-phase-1-v1.md`



---



## Bugs caught during gate work (would have shipped to production)



### From Step 4's Gate G smoke testing



1. **Missing `name` hidden field on cartrack-confirm form** — `detail.html`'s cartrack form was missing `<input name="name">`, but the endpoint required it. FastAPI returned 422 validation error. Caught only because the test actually clicked the button. Code review by reading would not have caught this.



2. **Notion `Status` property is type `select`, not `status`** — `writes.py` was sending `{"status": {"name": "..."}}` because `schema.py`'s `Literal[...]` doesn't distinguish between Notion's `select` and `status` property types (both produce identical Pydantic annotations via `introspect_notion.py`). Notion returned 400 "Status is expected to be select." Verified live via `GET /databases/{id}`, fixed payload to `{"select": {...}}`. Both B2C and B2B confirmed `select`.



3. **`logs/` directory uid mismatch** — Host-mounted `logs/` was owned by `charles` (uid 1000); container `appuser` is uid 10001 → `PermissionError` on first state file write. Fix: `sudo chown -R 10001:10001 /opt/services/cogstack-leadgen/logs/`. Document as first-deploy step.



### From deployment



4. **`docker exec caddy caddy reload` doesn't pick up nvim-edited Caddyfile** — `nvim`'s atomic save (write to temp + rename) changes the inode. Bind mounts in Docker are inode-based. Container was reading stale config even after reload. Fix: `docker restart caddy` (forces re-resolution of the bind mount). For future Caddyfile edits, prefer restart over reload.



---



## Known limitations / Phase 2+ deferrals



### Functional gaps in Phase 1



- **Filters on `/prospects`** (DB-of-origin, status, date range, source, outreach-status) — deferred to Phase 1.5; phone search is the headline access pattern

- **True pagination** — `/prospects` cap is 50 per DB (150 total displayed); cursor-based pagination is Phase 2

- **404 vs 502 distinction** at `/prospects/{id}` — currently any Notion error returns 502; could distinguish "page not found in Notion" → 404 (small refinement)

- **Bulk send** — Step 5

- **Drag-drop ingest** — Step 6

- **Help docs** — Step 7



### Workflow gaps



- **"Mark Sent to Cartrack" is Notion-only** — actual handoff to Cartrack's call centre (Paul) remains manual out-of-band. Phase 1 acceptable. Document in Help section (Step 7) so Claire doesn't think the button transmits.

- **Audit attribution** — Notion writes appear as "cogstack-leadgen-write integration," not the human clicker. Phase 2: capture authenticated user from Caddy basic_auth header.

- **`motivation` and `email` not surfaced in UI** — `create_claire_prospect()` accepts these but UI hardcodes empty/None. Phase 2 enhancement.

- **Notion creation failure visible to user** — currently logged only; could surface via dedicated audit panel

- **"Already marked" cartrack state lacks date** — vs. "Already sent YYYY-MM-DD" for WhatsApp. Phase 2: read `last_edited_time` or dedicated timestamp field.



### Tooling gaps



- **`introspect_notion.py` cannot distinguish Notion's `select` vs `status` property types** — produces identical `Literal[...]` annotations. Future enhancement: capture and surface the raw Notion property type as a comment in `schema.py`. Discovered via Step 4 Gate G bug.



---



## Lessons worth keeping



### About the gating pattern

- 7 gates per step plus COMMIT was the right grain

- Each gate explicitly named "STOP" and "show me the code in full" before agent could proceed

- This caught three production-blocking bugs that code-review-by-reading would have missed

- The discipline cost ~15-20 min extra per step. The bugs would have cost much more.



### About docker bind mounts

- Inode-based, not path-based

- Atomic file writers (nvim, sed, vim) break the mount silently

- After editing any container's mounted file, prefer `docker restart` over reload commands



### About Notion API property types

- `Literal[...]` from introspection captures the value space but not the property type

- `select` and `status` look identical in schemas but require different write payloads

- Verify property type with `GET /databases/{id}` before any write path

- B2C and B2B `Status` field: `select` (despite the name suggesting `status`)

- Claire-Prospects `Submitted to Pipeline`: `checkbox`

- Claire-Prospects `Response Status`: `select`



### About atomicity in send paths

- For any action that sends real messages: state file is source of truth, downstream writes are best-effort

- Order: normalize → idempotency → send → state append → downstream writes (best-effort)

- Reasoning: undo-ability of failure modes (duplicate WhatsApp = bad; missing Notion record = recoverable)



### About DRY_RUN safety

- Default to safe-on, explicit opt-in to production

- Surfaces in UI ("Dry-run mode — message will be logged, not delivered.") so user knows

- State file flag (`dry_run: true`) preserves audit context



---



## What's deployable right now



Anyone with the URL + correct credentials at `https://leads.bigtorig.com` can:



- See the dashboard with live counts (Step 2)

- Browse all 306 prospects across 3 DBs (Step 3)

- Search by phone with normalize + dedupe (Step 3)

- Click into any prospect, see all properties (Step 3)

- Look up WhatsApp display name when Baileys reachable (Step 4)

- Initiate a single WhatsApp send with confirmation panel + dry-run safety (Step 4)

- Mark a prospect "Sent to Call Centre" / "Submitted to Pipeline" with real Notion write (Step 4)



What they cannot yet do (Steps 5-7):

- Bulk send to multiple prospects from `/prospects` table (Step 5)

- Drag-drop ingest from Excel/XML (Step 6)

- Browse help docs (Step 7)



---



## Pre-flight before Step 5 (next session)



### Open questions for Step 5 design

- Bulk send UI: multi-select via checkboxes on `/prospects` table, or a dedicated `/outreach` page with batch composer?

- Default batch size: 40? (PRD §7) — what's the throughput sweet spot Claire actually reaches for?

- Confirmation flow: per-prospect confirm in batch, or single "send all 40" confirm?

- Inter-message jitter: the script does 3-5s; the UI should honor the same to avoid Baileys flagging



### Things to verify before Step 5

- Baileys `/send` endpoint behavior under burst load — does it queue or reject if 40 calls arrive within 1s?

- Outreach state file performance with 40+ entries appended in quick succession

- HTMX UX for "send batch" — does the user see per-prospect progress, or just a final summary?



### Things to dogfood before Step 5

- Send the URL + credentials to Claire, get her first reactions on Steps 2-4

- Walk through "what would I want to do next" with Claire to inform Step 5 design

- Note any UI friction (typography, button placement, mobile responsiveness)



---



## Commit log for the period



```

495fc87  feat: Step 4 — action buttons (WhatsApp lookup, send, mark sent to Cartrack)

ff14b3a  feat: Step 3 — /prospects unified table + phone dedupe search

3a85ba5  feat: Step 2 — FastAPI scaffold + dashboard with live counts

e6f9c3b  feat: add ClaireProspects DB and generate initial schema snapshot

72ba006  docs: clarify repo structure relationship in PRD-v2

1639dc7  docs: PRD-v2 — Phase 1 operations console

44a20c5  fix: correct stale sources_database_id in notion_config.json

567278b  docs: update PRD pointer — v1 superseded, v2 in progress

d2b3d1c  docs: archive v1 PRD and implementation plan ahead of PRD-v2

d7e7dc8  feat: add Notion schema introspection script

```



10 commits across two days. All on `feat/ui-phase-1`. Branch is ahead of `main` by all 10 commits (PR not yet opened — Phase 1 will land on main as a single feature branch when Steps 5-8 complete).
