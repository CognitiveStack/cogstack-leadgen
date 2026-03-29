# Product Requirements Document
# Cogstack Lead Generation Pipeline

**Version:** 1.1
**Date:** 2026-03-17
**Status:** Active Development — Phase 2 (B2C pipeline live; WhatsApp enrichment in aging)
**Project Directory:** `/opt/projects/cartrack-leadgen`

---

## 1. Executive Summary

Cogstack Lead Generation is an AI-powered lead discovery and qualification pipeline built for a South African vehicle tracking company (Cartrack reseller). It serves **two parallel pipelines**: B2B (fleet operators) and B2C (individual consumers).

**B2B:** An autonomous scraping agent (Bigtorig AI Runtime / OpenClaw on bigtorig) discovers candidate fleet companies from public SA data sources (CIPC, eTenders, Yellow Pages, LinkedIn, SAPS Crime Stats, Road Freight Association). Each candidate is scored and surfaced in a Notion kanban for human QA before handoff to the call centre.

**B2C:** Bigtorig AI Runtime discovers individual South Africans with verifiable purchase intent (Hellopeter competitor reviews, MyBroadband forums, Reddit, OLX, Gumtree). Intent signals are scored and enriched via LLM (gpt-4o-mini via OpenRouter), then submitted to a separate Notion B2C Leads DB.

**Current status:** Gumtree scraping is now live via Scrapling Fetcher (TLS fingerprint bypass, 50x faster than StealthySession). A WhatsApp name lookup service (Baileys on bigtorig) resolves phone numbers to real names before leads hit Notion. WhatsApp Business account (Phone 3) is in a 2-week aging period; temporary lookups use Phone 1 instance. Target production date: ~2026-04-03.

**MVP Goal:** Deliver 10+ qualified, human-approved leads per month across both pipelines to the client's call centre, with a structured data record including prospect summary, intent signal, and a call script opener.

---

## 2. Mission

**Mission Statement:** To replace manual prospecting with an intelligent, continuously-running pipeline that surfaces the right companies and individuals at the right time — so the client's sales team spends time selling, not searching.

### Core Principles

1. **Human-in-the-loop first** — AI scores and enriches, humans approve. No lead reaches the call centre without QA sign-off.
2. **Data quality over volume** — 10 excellent leads beats 100 mediocre ones. The scoring model and QA step exist to enforce this.
3. **Transparency** — Every lead carries a traceable enrichment record: source, score breakdown, summary rationale. QA reviewers can see why a lead was surfaced.
4. **Incremental automation** — Phase A is manual QA with AI enrichment; Phase B adds auto-approval thresholds; Phase C adds full enrichment AI. Each phase builds on a validated foundation.
5. **Low operational overhead** — The pipeline runs on existing Hostinger infrastructure (n8n, Notion) without requiring dedicated backend servers or custom frontends.

---

## 3. Target Users

### 3.1 Primary Personas

#### Claire — QA Reviewer (Internal)
- **Role:** Reviews AI-surfaced leads in Notion, approves or rejects
- **Technical comfort:** Low-to-medium; comfortable with Notion UI, not with code
- **Needs:** Clear, scannable lead cards; a reason why each lead was surfaced; an obvious approve/reject action; a consistent queue view sorted by score
- **Pain points:** Wading through irrelevant prospects; missing context on why a company was included; no clear next-step after approval

#### Paul — Call Centre Manager (Client)
- **Role:** Receives approved leads and dispatches to sales agents
- **Technical comfort:** Low; Notion viewer only
- **Needs:** A clean handoff view showing only approved leads ready to contact; company name, phone, sector, and a call script opener
- **Pain points:** Receiving unqualified leads that waste agent time; lack of context for cold calls

#### Charles — Pipeline Engineer (Internal)
- **Role:** Maintains the pipeline, monitors batches, tunes the scoring model
- **Technical comfort:** High; works with Python, n8n, Notion API, Tailscale
- **Needs:** Visibility into batch runs (counts, errors, duplicates); ability to adjust scoring weights; clear separation between infrastructure and scraping logic
- **Pain points:** Opaque failure modes in n8n; no persistent error log; no feedback loop from rejected leads to scoring model

#### OpenClaw — Autonomous Scraping Agent (External System)
- **Role:** Discovers candidate companies from SA public data sources and POSTs batches to the n8n webhook
- **Technical comfort:** N/A (automated system running Claude Haiku 4.5 on Raspberry Pi 4 via Tailscale)
- **Needs:** A stable, authenticated webhook endpoint; a documented JSON schema for lead payloads; clear deduplication so it can re-submit without creating duplicates

---

## 4. MVP Scope

### Core Functionality

| Feature | Status |
|---------|--------|
| ✅ Notion 3-database schema (Leads, Batches, Sources) | Complete |
| ✅ n8n webhook ingestion endpoint (v2) | Complete |
| ✅ Payload validation in Code node | Complete |
| ✅ Company name deduplication | Complete |
| ✅ Batch record creation (Batches DB) | Complete |
| ✅ Lead record creation (Leads DB, 28 fields) | Complete |
| ✅ Composite scoring formula (passed in payload) | Complete |
| ✅ QA status workflow (Pending → Approved/Rejected → Call Centre) | Complete |
| ✅ Notion QA Queue view (sorted by Composite Score) | Complete |
| ✅ Notion Pipeline Kanban view (grouped by Status) | Complete |
| ✅ Test harness (test_webhook.py with 3 sample leads) | Complete |
| ✅ Source reference database (6 SA data sources seeded) | Complete |
| ✅ B2C pipeline (Hellopeter, MyBroadband, Reddit, OLX) | Live — Phase 2 |
| ✅ B2C Notion databases (Leads, Batches) | Live |
| ✅ B2C LLM enrichment (gpt-4o-mini via OpenRouter) | Live — first run 6 leads |
| ✅ Gumtree B2C scraper (Scrapling Fetcher) | Live — buyer-intent search, 50x faster than StealthySession |
| ✅ Gumtree → B2C bridge (LLM classify + enrich) | Live (`scripts/gumtree_to_b2c.py`) |
| ✅ Hellopeter competitor churn scraper | Live (`scripts/hellopeter_scraper.py`) — Netstar + Tracker Connect |
| ✅ WhatsApp name lookup service (Baileys v6.7) | Built + verified on bigtorig (2026-03-20) |
| ⏳ WhatsApp Business account aging (Phone 3) | In progress — target ~2026-04-03 |
| ❌ OpenClaw scraping logic — B2B (bigtorig) | In progress |
| ❌ Phase B auto-approval (score ≥ 7) | Deferred |
| ❌ Phase B auto-rejection (score < 4) | Deferred |
| ❌ WhatsApp qualification outreach (Phase B) | Deferred — after name lookup production |
| ❌ Telegram/WhatsApp notifications on QA approval | Deferred |
| ❌ Fuzzy company name deduplication | Deferred |

### Technical

| Feature | Status |
|---------|--------|
| ✅ Python 3.13+ project with uv package manager | Complete |
| ✅ Environment variable management (.env + python-dotenv) | Complete |
| ✅ Notion API v2022-06-28 integration | Complete |
| ✅ n8n Code node (JavaScript, direct Notion REST calls) | Complete |
| ✅ Bearer token authentication on webhook | Complete |
| ❌ Notion formula properties (Composite Score, Quality Gate) | Manual Notion UI step |
| ❌ Notion rollup properties (Leads Generated, QA Approved) | Manual Notion UI step |
| ❌ Persistent error logging beyond Notion "Errors" field | Deferred |
| ❌ Webhook retry logic / exponential backoff | Deferred |
| ❌ Postgres dedup index | Deferred |

### Integration

| Feature | Status |
|---------|--------|
| ✅ n8n ↔ Notion API integration | Complete |
| ✅ OpenClaw → n8n webhook protocol (JSON schema documented) | Complete |
| ✅ Tailscale VPN tunnel (Pi4 ↔ Hostinger) | Infrastructure only |
| ❌ Notion → call centre CRM handoff | Deferred |
| ❌ Rejected lead feedback → OpenClaw scoring model | Deferred |

### Deployment

| Feature | Status |
|---------|--------|
| ✅ n8n running on bigtorig (n8n.bigtorig.com) | Complete |
| ✅ B2B webhook active (lead-ingestion-v2) | Complete |
| ✅ B2C webhook active (b2c-lead-ingestion) | Complete |
| ✅ Notion workspace live (B2B + B2C databases) | Complete |
| ✅ Bigtorig AI Runtime / OpenClaw running on bigtorig (x86_64) | Complete — gateway fixed 2026-03-15 |
| ✅ B2C first run completed (6 leads, 1 duplicate) | Complete |
| ❌ B2B OpenClaw production scraping configured | Pending |
| ❌ Claire/Paul invited to Notion workspace | Pending |
| ❌ Gumtree via ScraperAPI | Pending — cost decision required |

---

## 5. User Stories

### QA Reviewer (Claire)

**US-01:** As Claire, I want to see a prioritised queue of leads in Notion sorted by composite score, so that I review the most promising prospects first.
> Example: Leads scored 8.5+ appear at the top of the "QA Queue" view; I never have to manually sort.

**US-02:** As Claire, I want each lead card to include a prospect summary, fleet assessment, and call script opener, so that I can make an approval decision without additional research.
> Example: "Durban Transport Co — manages a 45-truck long-haul fleet with no tracking system currently. High theft risk based on SAPS data for the route corridor. Opener: 'I understand your operation runs cargo between Durban and Johannesburg — have you looked at GPS-based theft recovery for your fleet?'"

**US-03:** As Claire, I want to change a lead's status with a single click in Notion, so that approvals and rejections are fast and low-friction.
> Example: Change dropdown from "Pending QA" to "QA Approved" — no form to fill, no email to send.

**US-04:** As Claire, I want to add a QA note when rejecting a lead, so that the team can understand why a lead didn't pass and improve the scoring model.
> Example: "Company is a sole trader, not a fleet operator — remove 'Yellow Pages transport' as a source category."

### Call Centre Manager (Paul)

**US-05:** As Paul, I want to see only QA-approved leads in my Notion view with a call script opener, so that my agents can start calls immediately with relevant context.
> Example: Filtered view showing Status = "Sent to Call Centre", with Company Name, Phone, Sector, and Call Script Opener columns visible.

### Pipeline Engineer (Charles)

**US-06:** As Charles, I want to see a batch summary record for each ingestion run including lead count, duplicates skipped, and errors, so that I can monitor pipeline health without reading logs.
> Example: Batches DB record: `batch_20260219_001 | 12 leads received | 9 created | 2 duplicates | 1 error | Status: Completed with errors`

**US-07:** As Charles, I want the n8n Code node to return a structured JSON response, so that OpenClaw can confirm which leads were accepted and retry failed ones.
> Example: `{ "batch_id": "...", "status": "completed", "leads_created": 9, "duplicates": 2, "errors": 1, "error_details": [...] }`

### Technical User Stories

**US-08:** As OpenClaw, I want the webhook to accept idempotent re-submissions by deduplicating on company name, so that network retries don't create duplicate lead records.
> Example: Posting the same company name twice in separate batches results in one lead record, and the second submission is logged as a duplicate in the batch record.

---

## 6. Core Architecture & Patterns

### Architecture Overview

```
Bigtorig AI Runtime / OpenClaw (bigtorig x86_64 VPS, Tailscale)
    │                           ↑
    │                    Pi4 (ARM64) — Hugo agent, WhatsApp channel only
    │
    │  POST /webhook/lead-ingestion-v2  (B2B)
    │  POST /webhook/b2c-lead-ingestion (B2C)
    │  Authorization: Bearer <token>
    │  Content-Type: application/json
    │  Body: { batch_id, [segment: "B2C"], leads[] }
    ▼
n8n (bigtorig, n8n.bigtorig.com)
    │  Webhook Trigger Node
    │  ↓
    │  Code Node (n8n_code_node.js)
    │    - Validates payload structure
    │    - Deduplicates by company name (Notion query)
    │    - Creates Batches DB record
    │    - Creates Leads DB records (one per lead)
    │    - Updates Batches DB with final counts
    │    - Returns structured JSON response
    ▼
Notion API (api.notion.com, v2022-06-28)
    │
    ├── Leads DB (30b89024-cd3d-8123-94f7-ee27b966bc0d)
    │     28 fields including: Company Name, Sector, Fleet Size,
    │     Composite Score, QA Status, Prospect Summary,
    │     Fleet Assessment, Call Script Opener, Source
    │
    ├── Batches DB (30b89024-cd3d-8198-bb49-ec8e3e9fe40e)
    │     Batch ID, Run Date, Status, Leads Received,
    │     Leads Created, Duplicates, Errors, Error Log
    │
    ├── Sources DB (30b89024-cd3d-81b1-ab3a-c900965b5d64)
    │     Name, Type, URL, Coverage, Reliability, Last Scraped, Notes
    │
    ├── B2C Leads DB — consumer schema (phone, email, intent signal, dispute tracking)
    └── B2C Batches DB — one record per B2C ingestion run
    ▼
Notion UI (QA Review)
    │
    ├── QA Queue View — Status = "Pending QA", sorted by Composite Score DESC
    ├── Pipeline Kanban — grouped by Status
    ├── Approved View — Status = "QA Approved" or "Sent to Call Centre"
    └── All Leads View — full database
    ▼
Call Centre (Paul's team)
    └── Works from "Sent to Call Centre" leads in Notion
```

### Directory Structure

```
cogstack-leadgen/
├── .config/
│   └── PRD.md                          # This document
├── .claude/
│   ├── commands/                       # Claude Code skill commands
│   └── docs/
│       ├── SETUP_GUIDE.md              # Step-by-step Notion setup
│       └── SESSION_SUMMARY-feb18.md    # Previous session notes
├── main.py                             # Entry point (placeholder — to be implemented)
├── create_notion_databases.py          # One-time Notion schema setup
├── test_webhook.py                     # End-to-end pipeline test
├── n8n_code_node.js                    # Active n8n Code node (paste into workflow)
├── n8n_lead_ingestion_workflow.json    # v1 workflow export (deprecated)
├── notion_config.json                  # Database IDs (committed for reference)
├── pyproject.toml                      # Python project config (uv)
├── uv.lock                             # Dependency lockfile
├── .python-version                     # Python 3.13
└── .env                                # Secrets (not committed)
```

### Key Design Patterns

- **Code-node-as-backend:** All ingestion logic lives in a single n8n JavaScript Code node rather than a Python service, avoiding the need to run and maintain a separate API server. n8n's `$http.request()` is used directly against the Notion API.
- **Payload-carries-enrichment:** OpenClaw computes scores and generates enrichment text (prospect summary, fleet assessment, call script) before posting. The n8n Code node is a thin persistence layer, not a processing layer. This keeps the Code node simple and puts intelligence close to the data source.
- **Dedup-on-write:** Before creating a lead record, the Code node queries Notion for existing records with the same company name. This prevents duplicates without requiring a separate dedup service or database.
- **Batch-as-audit-trail:** Every ingestion run creates a Batches DB record that tracks counts and errors. This provides operational visibility without external logging infrastructure.
- **Status-machine QA:** Lead status follows a defined state machine enforced by Notion's select property. Invalid transitions are prevented by the UI.

---

## 7. Tools / Features

### 7.1 n8n Webhook Ingestion (n8n_code_node.js)

**Purpose:** Accept lead batches from OpenClaw, validate, deduplicate, and persist to Notion.

**Operations:**
1. Validate payload — check for `batch_id`, `leads` array, required lead fields
2. Create Batches DB record with status "Processing"
3. For each lead: query Notion for existing company name → skip if found, create if new
4. Update Batches DB record with final counts (created, duplicates, errors)
5. Return JSON response with full summary

**Key fields created in Leads DB per lead:**

| Field | Type | Description |
|-------|------|-------------|
| Company Name | Title | Primary identifier |
| Sector | Select | Industry category |
| Fleet Size Category | Select | Small / Medium / Large |
| Estimated Fleet Size | Number | Numeric estimate |
| Province | Select | SA province |
| Company Type | Select | Pty Ltd, CC, Gov, etc. |
| Website | URL | Company website if found |
| Phone | Phone | Contact number |
| Email | Email | Contact email |
| Physical Address | Rich Text | Street address |
| CIPC Number | Rich Text | Company registration number |
| Fleet Likelihood | Number | 0–10 AI score |
| Tracking Need Score | Number | 0–10 AI score |
| Fleet Size Bonus | Number | 0, 1, or 2 |
| Composite Score | Number | Weighted formula result |
| QA Status | Select | Pending QA (initial) |
| Source | Relation | Link to Sources DB |
| Prospect Summary | Rich Text | AI-generated overview |
| Fleet Assessment | Rich Text | AI fleet analysis |
| Tracking Need Reasoning | Rich Text | Why tracking is relevant |
| Call Script Opener | Rich Text | Suggested cold call opening |
| Date Added | Date | Ingestion timestamp |
| Batch | Relation | Link to Batches DB |

### 7.2 Notion QA Workspace

**Purpose:** Human review interface for Claire to approve/reject leads.

**Views:**
- **QA Queue** — Filter: Status = "Pending QA"; Sort: Composite Score DESC; default view for reviewers
- **Pipeline Kanban** — Group by Status; all leads visible across workflow stages
- **Approved — Ready to Send** — Filter: Status = "QA Approved"; for handoff to Paul
- **Call Centre Active** — Filter: Status = "Sent to Call Centre"

**QA Actions:**
- Change QA Status dropdown
- Add QA Review Date (date field)
- Add QA Notes (free text)
- Add Rejection Reason (select: Not a Fleet Operator / Duplicate / Insufficient Data / Wrong Region / Other)

### 7.3 Composite Scoring Model

**Formula:**
```
Composite Score = (Fleet Likelihood × 0.4) + (Tracking Need Score × 0.4) + (Fleet Size Bonus × 0.2)
```

**Scale:**
- Fleet Likelihood: 0–10 (AI assessment of probability company operates a vehicle fleet)
- Tracking Need Score: 0–10 (AI assessment of urgency/relevance of tracking solution)
- Fleet Size Bonus: 0 (small, 1–5 vehicles), 1 (medium, 6–20), 2 (large, 20+)

**Interpretation:**
- Score ≥ 7 → High priority (Phase B: auto-approve)
- Score 4–6.9 → Medium priority (manual QA)
- Score < 4 → Low priority (Phase B: auto-reject)

**Current state:** Scores are computed by OpenClaw and passed in the payload. The Code node stores them as-is. A Notion formula property for `Composite Score` must be added manually in the Notion UI (API limitation for formula properties).

### 7.4 Test Harness (test_webhook.py)

**Purpose:** Validate end-to-end pipeline without requiring OpenClaw.

**Behaviour:**
- Generates 3 realistic SA company lead records with computed composite scores
- POSTs to webhook URL with Bearer token from environment variables
- Prints HTTP response status and body
- Expected result: 3 lead records appear in Notion Leads DB with Status = "Pending QA"

**Usage:**
```bash
export WEBHOOK_URL="https://n8n.bigtorig.com/webhook/lead-ingestion-v2"
export WEBHOOK_TOKEN="<token>"
uv run test_webhook.py
```

### 7.5 Notion Database Setup (create_notion_databases.py)

**Purpose:** One-time script to create the 3-database Notion schema.

**Behaviour:**
- Creates Leads DB with 28 property schema
- Creates Batches DB with 10 property schema
- Creates Sources DB with 8 property schema
- Seeds Sources DB with 6 SA data sources
- Writes database IDs to `notion_config.json`
- Prints setup summary

---

## 8. Technology Stack

### Core Technologies

| Component | Technology | Version | Reason |
|-----------|-----------|---------|--------|
| Language | Python | 3.13+ | Modern async support, type hints, uv compatibility |
| Package manager | uv | Latest | Fast, lockfile-based, PEP 517 compliant |
| Workflow engine | n8n | Self-hosted | Visual workflow editor, webhook support, Code node for custom JS |
| Database | Notion | API v2022-06-28 | Client-facing UI, no custom frontend needed, collaborative QA |
| HTTP client | httpx | ≥0.28.1 | Async-capable, modern API, used in test_webhook.py |
| Environment config | python-dotenv | ≥1.2.1 | Standard .env loading |
| VPN | Tailscale | — | Secure Pi4 ↔ Hostinger connectivity |
| Reverse proxy | Caddy | — | Shared infra; handles TLS for n8n.bigtorig.com |

### Third-Party Integrations

| Service | Purpose | Auth Method |
|---------|---------|-------------|
| Notion API | Lead/Batch/Source persistence, QA UI | Bearer token (`ntn_...`) |
| n8n webhook | Ingestion endpoint | Bearer token in Authorization header |
| OpenClaw (Anthropic Claude Haiku 4.5) | Web scraping + enrichment agent | Internal (Tailscale) |
| CIPC | Company registration lookup | Public web / scrape |
| eTenders | Government tender data | Public web / scrape |
| Yellow Pages SA | Business directory | Public web / scrape |
| LinkedIn | Company profiles | Scrape (rate-limited) |
| SAPS Crime Stats | Risk assessment | Public data |
| Road Freight Association | Fleet operator registry | Public web |

### Future Dependencies (Phase C+)

- Anthropic Claude API (direct) — for enrichment outside OpenClaw
- Playwright or Selenium — for JS-rendered data sources
- PostgreSQL — for high-volume dedup index
- Celery + Redis — for async batch processing queue

---

## 9. Security & Configuration

### Authentication

| Boundary | Method | Notes |
|----------|--------|-------|
| OpenClaw → n8n webhook | Bearer token in `Authorization` header | Token stored in OpenClaw env; matched in n8n workflow credentials |
| n8n → Notion API | Bearer token (`NOTION_API_KEY`) | Hardcoded in n8n Code node constants; should be moved to n8n credentials store |
| Notion workspace | Notion account login | Claire and Paul added as workspace members |
| Hostinger n8n | Caddy reverse proxy | TLS via Let's Encrypt; no additional auth layer |
| Pi4 ↔ Hostinger | Tailscale VPN | Mutual auth, encrypted tunnel |

### Environment Variables

```bash
# Required for local Python scripts
NOTION_API_KEY=ntn_your_integration_token
NOTION_PAGE_ID=your_parent_page_id

# Generated by create_notion_databases.py (also in notion_config.json)
LEADS_DB_ID=30b89024-cd3d-8123-94f7-ee27b966bc0d
SOURCES_DB_ID=30b89024-cd3d-81b1-ab3a-c900965b5d64
BATCHES_DB_ID=30b89024-cd3d-8198-bb49-ec8e3e9fe40e

# Required for test_webhook.py
WEBHOOK_URL=https://n8n.bigtorig.com/webhook/lead-ingestion-v2
WEBHOOK_TOKEN=your_bearer_token
```

### Security Scope

**In scope:**
- Bearer token authentication on the webhook endpoint
- Environment variable management (no secrets committed to git)
- Tailscale VPN for internal service communication
- Notion workspace access control (roles: Editor for Claire, Commenter for Paul)

**Out of scope:**
- Rate limiting on the webhook (handled by n8n)
- DDoS protection (handled by Caddy/Hostinger)
- Data encryption at rest (handled by Notion)
- GDPR compliance for SA company data (public data sources only)

### Deployment Notes

- n8n runs in Docker on Hostinger behind Caddy (`caddy-shared` network)
- No new containers needed for this project — uses existing `local-ai-packaged` stack
- `notion_config.json` is committed to git (contains only public database IDs, no secrets)
- `.env` is gitignored; copy `.env.example` for new environments

---

## 10. API Specification

### Webhook: POST /webhook/lead-ingestion-v2

**URL:** `https://n8n.bigtorig.com/webhook/lead-ingestion-v2`
**Method:** POST
**Authentication:** `Authorization: Bearer <WEBHOOK_TOKEN>`
**Content-Type:** `application/json`

#### Request Body

```json
{
  "batch_id": "batch_20260219_001",
  "source": "Yellow Pages",
  "leads": [
    {
      "company_name": "Durban Transport Co (Pty) Ltd",
      "sector": "Transport & Logistics",
      "fleet_size_category": "Large",
      "estimated_fleet_size": 45,
      "province": "KwaZulu-Natal",
      "company_type": "Pty Ltd",
      "website": "https://durbantransport.co.za",
      "phone": "+27 31 555 0123",
      "email": "info@durbantransport.co.za",
      "physical_address": "12 Marine Drive, Durban, 4001",
      "cipc_number": "2015/123456/07",
      "fleet_likelihood": 9.2,
      "tracking_need_score": 8.5,
      "fleet_size_bonus": 2,
      "composite_score": 8.74,
      "prospect_summary": "Long-haul trucking company operating 45 vehicles...",
      "fleet_assessment": "High-value fleet with significant theft exposure...",
      "tracking_need_reasoning": "SAPS data shows elevated cargo theft on N2...",
      "call_script_opener": "Hi, I understand you run long-haul cargo between Durban and JHB..."
    }
  ]
}
```

#### Response Body (Success)

```json
{
  "batch_id": "batch_20260219_001",
  "status": "completed",
  "leads_received": 1,
  "leads_created": 1,
  "duplicates_skipped": 0,
  "errors": 0,
  "error_details": [],
  "notion_batch_id": "abc123-notion-page-id"
}
```

#### Response Body (Partial Success)

```json
{
  "batch_id": "batch_20260219_002",
  "status": "completed_with_errors",
  "leads_received": 3,
  "leads_created": 2,
  "duplicates_skipped": 1,
  "errors": 1,
  "error_details": [
    {
      "company_name": "Failed Company Ltd",
      "error": "Notion API returned 400: invalid property type for 'Fleet Size'"
    }
  ],
  "notion_batch_id": "def456-notion-page-id"
}
```

#### Error Responses

| Status | Meaning |
|--------|---------|
| 400 | Missing required fields (batch_id or leads array) |
| 401 | Invalid or missing Bearer token |
| 500 | Unhandled exception in Code node |

---

## 11. Success Criteria

### MVP Success Definition

The MVP is successful when: 10 qualified leads per month are consistently delivered to Paul's call centre view in Notion, each with a complete prospect profile, and the QA turnaround time for Claire is under 2 hours per week.

### Functional Requirements

| Requirement | Status |
|------------|--------|
| ✅ Webhook accepts and validates lead batch payloads | Complete |
| ✅ Duplicate leads are detected and skipped (company name match) | Complete |
| ✅ Each ingestion run creates a traceable Batches DB record | Complete |
| ✅ Leads appear in Notion with Status = "Pending QA" within 30 seconds of batch POST | Complete |
| ✅ QA Queue view shows leads sorted by Composite Score descending | Complete |
| ✅ Claire can approve/reject a lead with a single dropdown change | Complete |
| ✅ Approved leads are visible to Paul in a filtered call centre view | Complete |
| ✅ Test harness can validate end-to-end pipeline without OpenClaw | Complete |
| ❌ OpenClaw posts real leads from SA data sources | Pending (external) |
| ❌ Rollup properties show lead/approval counts in Batches and Sources DBs | Pending (manual Notion step) |
| ❌ Composite Score formula property computed in Notion | Pending (manual Notion step) |

### Quality Indicators

- **Lead quality:** < 20% rejection rate from QA after scoring model tuning
- **Pipeline reliability:** < 2 failed batches per month
- **Duplication rate:** < 5% of leads are duplicates of existing records
- **QA throughput:** Claire can review 10 leads in < 2 hours per week
- **Call conversion:** Target > 5% of approved leads result in a sale (tracked by client)

### User Experience Goals

- Claire opens Notion and immediately sees a prioritised queue — no searching, no filtering required
- Paul's view shows only leads ready to contact — no QA noise visible
- Charles can diagnose a pipeline failure from the Batches DB record alone without reading n8n logs

---

## 12. Implementation Phases

### Phase A — Human QA Foundation (Current)

**Goal:** Validate the scoring model and QA workflow with real leads before automating.

**Deliverables:**
- ✅ Notion 3-database schema with 28-field lead record
- ✅ n8n v2 Code node with validation, dedup, and Notion persistence
- ✅ Composite scoring formula (manual payload field)
- ✅ QA status state machine in Notion
- ✅ QA Queue and Pipeline Kanban views
- ✅ Test harness (test_webhook.py)
- ⬜ Paste n8n_code_node.js into live n8n workflow and activate
- ⬜ Invite Claire and Paul to Notion workspace
- ⬜ Add Notion formula and rollup properties manually (SETUP_GUIDE.md)
- ⬜ Configure OpenClaw with production webhook URL and token
- ⬜ First real batch received and reviewed by Claire

**Validation:** 3 test leads created via test_webhook.py appear in Notion; Claire reviews and approves/rejects at least one; approved lead visible in Paul's view.

**Estimated remaining effort:** 1–2 days (mostly configuration and Notion manual steps)

---

### Phase B — Automated Threshold Decisions

**Goal:** Reduce Claire's QA burden by auto-approving high-confidence leads and auto-rejecting low-confidence ones.

**Deliverables:**
- ⬜ Add auto-approval logic to n8n Code node: if `composite_score >= 7`, set Status = "QA Approved" directly
- ⬜ Add auto-rejection logic: if `composite_score < 4`, set Status = "QA Rejected" with Rejection Reason = "Score below threshold"
- ⬜ Add QA Queue filter to show only mid-range leads (score 4–6.9) for Claire
- ⬜ Add Notion notification (email or Slack) when a batch creates > 5 auto-approved leads
- ⬜ Add batch-level auto-approval count to Batches DB

**Validation:** Post a test batch with leads at scores 3.5, 5.5, and 8.0. Verify: score 3.5 auto-rejected, score 8.0 auto-approved, score 5.5 routed to Claire's queue.

**Prerequisite:** Phase A validated with > 50 real leads and < 20% QA rejection rate on auto-approved candidates.

---

### Phase C — AI Enrichment In-Pipeline

**Goal:** Move enrichment computation (prospect summary, fleet assessment, call script) into the pipeline, reducing OpenClaw's payload responsibility.

**Deliverables:**
- ⬜ Add Anthropic Claude API call to n8n Code node (or separate Enrichment node) using raw company data
- ⬜ Define enrichment prompt template for fleet operator assessment
- ⬜ Add structured output parsing for prospect summary, fleet assessment, tracking need, call script
- ⬜ Add `enrichment_status` field to Leads DB (Pending / Complete / Failed)
- ⬜ OpenClaw posts minimal payload (company name, registration, sector, size, source) without enrichment
- ⬜ Enrich asynchronously after lead creation (n8n sub-workflow or scheduled node)

**Validation:** Post a minimal payload (no enrichment text). Verify: lead created with `enrichment_status = Pending`; after enrichment runs, lead updated with all 4 enrichment fields populated.

---

### Phase D — Analytics & Feedback Loop

**Goal:** Close the loop between QA decisions and scoring model improvement.

**Deliverables:**
- ⬜ Monthly summary dashboard in Notion (leads by source, approval rate by source, score distribution)
- ⬜ Rejected lead export: weekly CSV of rejected leads with rejection reasons → feeds back to OpenClaw scoring calibration
- ⬜ Source reliability score: auto-update Sources DB with approval rate per source
- ⬜ Notification to Charles when source approval rate drops below 30%
- ⬜ Call outcome tracking: Paul marks leads as Contacted / Converted / Not Interested; conversion rate visible per source

**Validation:** After 3 months of operation, approval rate per source is visible in Sources DB; at least one source has been tuned or removed based on low approval rate.

---

## 13. Future Considerations

### Post-MVP Enhancements

- **Fuzzy deduplication:** Replace exact company name match with fuzzy matching (Levenshtein distance or phonetic) to catch variations like "Durban Transport Co" vs "Durban Transport Company (Pty) Ltd"
- **CIPC number deduplication:** Primary key dedup on CIPC registration number, which is immutable and unique — more reliable than company name
- **Domain-based deduplication:** Extract apex domain from website URL as a secondary dedup key
- **Postgres dedup index:** For high-volume operation (1000+ leads/month), replace Notion query-per-lead dedup with a lightweight Postgres table keyed on company name hash and CIPC number

### Integration Opportunities

- **WhatsApp notification:** When a batch is processed, send Claire a WhatsApp message via Twilio or WhatsApp Business API: "5 new leads ready for review — 2 high priority"
- **CRM handoff:** When Paul moves a lead to "Contacted", trigger a CRM record creation (HubSpot, Pipedrive) via n8n webhook or native integration
- **Google Maps API:** Auto-populate physical address coordinates for geographic filtering (e.g., leads within 50km of client's service centre)
- **CIPC API (if available):** Direct company registration lookup to auto-populate company type, registration date, and directors

### Advanced Features (Phase D+)

- **Lead scoring model versioning:** Track which scoring model version produced each lead; compare approval rates across model versions
- **Auto-enrichment from LinkedIn:** Use LinkedIn API (or scraper) to pull employee count, industry, and recent company news for high-scoring leads
- **Competitor signal detection:** Flag leads that have mentions of competitor tracking providers in their public web presence — may indicate dissatisfaction / switching intent
- **Call outcome ML:** Train a simple classifier on call outcomes to predict which lead attributes correlate with conversions; feed back into scoring weights

---

## 14. Risks & Mitigations

### Risk 1: Data Source Access Degradation / Bot Blocking
**Description:** Public data sources add bot detection, breaking scrapers. **This risk has already materialised for Gumtree** — the only B2C source with phone numbers directly on listings.
**Likelihood:** High (ongoing maintenance burden)

**Gumtree — RESOLVED (2026-03-18):**

Gumtree scraping now works via Scrapling Fetcher (`scripts/gumtree_scrapling.py`) using curl_cffi with browser TLS fingerprints. No Chromium needed. ~1s per page. Bridge script (`scripts/gumtree_to_b2c.py`) filters seller ads via LLM classification (gpt-4o-mini) and enriches buyer-intent leads before POSTing to B2C webhook.

**Remaining enrichment gap:** Gumtree ads often show phone numbers but rarely names. WhatsApp name lookup service (Baileys on bigtorig) resolves phone → real name. Service built and verified 2026-03-20; WhatsApp Business account aging until ~2026-04-03.

**Mitigation (general):**
- Monitor Batches DB for batches with 0 leads from a specific source
- Design scrapers as modular source adapters; one broken source doesn't stop the pipeline
- Maintain a fallback list of alternative data sources (eTenders and RFA are more stable than LinkedIn)
- Track `Last Scraped` and `Reliability` in Sources DB; alert when reliability drops

**Mitigation (Gumtree specifically):**
- Short-term: increase volume from working sources (more Hellopeter queries, OLX categories)
- Medium-term: evaluate ScraperAPI trial ($49/month) — confirm it bypasses Gumtree's bot gate before committing
- Alternative: Facebook Marketplace Wanted ads (similar intent signal, phone sometimes visible) — requires Facebook auth

### Risk 2: Scoring Model Produces Low-Quality Leads
**Description:** OpenClaw's composite scoring incorrectly surfaces non-fleet companies as high-priority leads, wasting Claire's QA time and reducing client trust.
**Likelihood:** Medium (scoring is based on AI inference, not ground truth)
**Mitigation:**
- Phase A exists specifically to validate scoring with human judgement before Phase B automation
- Track QA rejection rate per source and per score band; tune weights based on data
- Add a QA Notes field for qualitative feedback that feeds back to OpenClaw prompt engineering
- Do not implement Phase B auto-approval until rejection rate < 20% for score ≥ 7 leads

### Risk 3: n8n Code Node Fails Silently
**Description:** A Notion API error or malformed payload causes partial batch failure; some leads not created; error not surfaced to Charles.
**Likelihood:** Medium
**Mitigation:**
- Code node updates Batches DB with `error_details` array for each failed lead
- Webhook response body always includes `errors` count and `error_details`
- OpenClaw should alert on `errors > 0` in the webhook response
- Phase B: add n8n error workflow that sends an email/Slack alert to Charles on unhandled exceptions

### Risk 4: OpenClaw Reliability
**Description:** Raspberry Pi 4 running OpenClaw is a single point of failure; power cuts, hardware failure, or Tailscale connectivity issues stop lead generation entirely.
**Likelihood:** Low-Medium (home/small office environment)
**Mitigation:**
- Monitor batch frequency from Batches DB; alert if no batch received in 48 hours
- Document OpenClaw restart procedure; ensure it auto-starts on Pi reboot
- Consider migrating OpenClaw to Hostinger VPS in Phase C to eliminate dependency on Pi hardware
- Tailscale provides resilient reconnection; short outages self-heal

### Risk 5: Notion API Rate Limits
**Description:** At scale (100+ leads/batch), the current per-lead Notion API call pattern (1 query + 1 create per lead) may hit Notion's rate limits (3 requests/second for free integrations).
**Likelihood:** Low for current volume (10 leads/month target)
**Mitigation:**
- Current volume is far below rate limits; not an immediate concern
- For Phase C+ (if volume grows): batch Notion creates using the Notion API bulk endpoints (if/when available) or add 300ms delay between calls
- Alternatively, use a lightweight Postgres table for dedup and batch-create Notion records at end of run

---

## 15. Appendix

### A. Related Documents

| Document | Path | Purpose |
|----------|------|---------|
| CLAUDE.md | `cogstack-leadgen/CLAUDE.md` | Project guidance for Claude Code |
| Setup Guide | `.claude/docs/SETUP_GUIDE.md` | Step-by-step Notion workspace creation |
| Session Summary | `.claude/docs/SESSION_SUMMARY-feb18.md` | Feb 18 session notes and immediate next steps |
| Workflow Guide | `.claude/docs/CLAUDE_CODE_WORKFLOW.md` | Claude Code workflow for this project |

### B. Notion Workspace

- **Workspace URL:** https://www.notion.so/AI-Lead-Pipeline-30b89024cd3d8063b25dd7bb0393815f
- **Leads DB ID:** `30b89024-cd3d-8123-94f7-ee27b966bc0d`
- **Batches DB ID:** `30b89024-cd3d-8198-bb49-ec8e3e9fe40e`
- **Sources DB ID:** `30b89024-cd3d-81b1-ab3a-c900965b5d64`

### C. Infrastructure

| Service | URL | Notes |
|---------|-----|-------|
| n8n | https://n8n.bigtorig.com | bigtorig VPS, Docker, behind Caddy |
| B2B Webhook | https://n8n.bigtorig.com/webhook/lead-ingestion-v2 | Active |
| B2C Webhook | https://n8n.bigtorig.com/webhook/b2c-lead-ingestion | Active |
| Notion API | https://api.notion.com/v1 | v2022-06-28 |
| Bigtorig AI Runtime / OpenClaw | bigtorig x86_64 VPS (Tailscale) | B2C lead gen scripts |
| Hugo / OpenClaw | Pi4 ARM64 (Tailscale) | WhatsApp channel only (+27639842638) |

### D. Immediate Next Steps (As of 2026-02-19)

1. Open n8n at n8n.bigtorig.com → lead-ingestion-v2 workflow
2. Open Code node → paste contents of `n8n_code_node.js`
3. Update `NOTION_API_KEY` constant in the Code node
4. Save and activate the workflow
5. Run: `export WEBHOOK_URL=... && export WEBHOOK_TOKEN=... && uv run test_webhook.py`
6. Verify 3 leads appear in Notion Leads DB with Status = "Pending QA"
7. Follow SETUP_GUIDE.md to add formula and rollup properties in Notion UI
8. Invite Claire (Editor) and Paul (Commenter) to Notion workspace
9. Configure OpenClaw with production webhook URL and bearer token
10. Monitor first real batch via Batches DB view
