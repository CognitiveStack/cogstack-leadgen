# Feature: B2C Lead Generation Pipeline

The following plan should be complete, but validate documentation and codebase patterns before implementing.

Pay special attention to naming of existing utils, types, and Notion property names. The B2C schema must be consistent with B2B conventions while being structurally separate.

---

## Feature Description

Add a B2C (business-to-consumer) lead generation pipeline running alongside the existing B2B pipeline. B2C leads target individual South African consumers who have expressed genuine, verifiable interest in personal vehicle tracking. The pipeline ingests leads from a new n8n webhook endpoint, deduplicates by intent signal URL (not company name), persists to a dedicated Notion B2C Leads database, and routes through the same QA reviewer (Claire) before handoff to the B2C call centre.

The pipeline also tracks contractual billing obligations: a `Date Delivered` field and a `Rejection Deadline` (5 business days after delivery) so disputes can be managed within the agreed window.

---

## User Story

As Charles (pipeline engineer),
I want Hugo to scrape B2C interest signals from public sources (Hellopeter, Gumtree, Facebook groups, etc.) and deliver qualified individual consumer leads to a dedicated Notion database via a new webhook,
So that the B2C call centre has a steady pipeline of warm prospects who have already expressed interest in vehicle tracking.

As Claire (QA reviewer),
I want to review B2C consumer leads in a dedicated Notion view with the person's contact details, their exact intent signal, and an urgency score,
So that I can quickly approve high-quality leads and reject poor ones before they reach the call centre.

As Paul (B2C call centre manager),
I want to see only QA-approved B2C leads with a call script opener tailored to why the person expressed interest,
So that my agents can open every call with direct, relevant context.

---

## Problem Statement

The existing pipeline is B2B only — it finds fleet operator companies. The client's B2C call centre targets individual consumers wanting personal vehicle tracking. These require different data sources, a different schema (person not company), different deduplication logic (intent signal URL, not company name), and a contractual billing/dispute tracking mechanism not needed in B2B.

---

## Solution Statement

Create a parallel B2C pipeline with:
1. A new n8n webhook endpoint `/webhook/b2c-lead-ingestion` with its own Code node (`n8n_b2c_code_node.js`)
2. A new Notion B2C Leads database with a consumer-oriented schema
3. A new Notion B2C Batches database (separate audit trail from B2B)
4. Dedup logic keyed on `intent_source_url` — same post = same lead; new post from same person = new lead
5. Dispute tracking fields: `Date Delivered`, `Rejection Deadline` (manual formula), `Dispute Status`
6. A new setup script (`create_b2c_database.py`) and test script (`test_b2c_webhook.py`) mirroring existing B2B patterns
7. New B2C-specific data sources seeded into the shared Sources DB

---

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: Medium
**Primary Systems Affected**: Notion (new DB), n8n (new workflow + Code node), Sources DB (new entries), `notion_config.json`, `.env`, `CLAUDE.md`
**Dependencies**: No new Python packages required (httpx + python-dotenv already installed)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `create_notion_databases.py` (entire file) — Mirror this exactly for `create_b2c_database.py`. Pattern: `create_database()`, `create_leads_database()`, `seed_sources()`, `print_manual_steps()`, `print_database_ids()`, httpx.Client usage
- `n8n_code_node.js` (lines 1–181) — Mirror structure for `n8n_b2c_code_node.js`. Pattern: `notionRequest()` helper, Step 1 (batch), Step 2 (per-lead loop with dedup), Step 3 (batch update), return format
- `test_webhook.py` (entire file) — Mirror for `test_b2c_webhook.py`. Pattern: `get_sample_payload()`, `main()`, httpx.post with Bearer auth, score preview print
- `notion_config.json` — Must be updated with B2C DB IDs after running setup script
- `.env` — Must be updated with `B2C_LEADS_DB_ID`, `B2C_BATCHES_DB_ID`, `B2C_WEBHOOK_URL`
- `CLAUDE.md` — Must update Architecture section and Key Files table

### New Files to Create

- `n8n_b2c_code_node.js` — JavaScript Code node for the n8n B2C workflow; paste into n8n UI
- `create_b2c_database.py` — One-time script to create B2C Leads DB + B2C Batches DB; seed B2C sources
- `test_b2c_webhook.py` — Sends 3 realistic B2C test leads; validates end-to-end B2C pipeline

### New Directories to Create

- `.agents/plans/` — Already created; stores this plan

### Relevant Documentation — READ BEFORE IMPLEMENTING

- Notion API Create Database: https://developers.notion.com/reference/create-a-database
  - Section: Property schema definitions — needed to define `phone_number`, `email`, `url` property types
  - Why: B2C schema uses `phone_number` and `email` Notion property types not used in B2B schema
- Notion API Query Database: https://developers.notion.com/reference/post-database-query
  - Section: Filter by URL property — needed for `intent_source_url` dedup query
  - Why: B2C dedup queries on URL property (not title property like B2B company name dedup)
- Notion API Property Values: https://developers.notion.com/reference/property-value-object
  - Section: `phone_number`, `email` value objects — format differs from rich_text

### Patterns to Follow

**Naming Conventions:**
- Python files: `snake_case.py`
- JS Code node constants: `UPPER_SNAKE_CASE` (see `n8n_code_node.js` lines 6–8)
- Notion property names: `Title Case With Spaces` (see `create_notion_databases.py` throughout)
- Batch ID format: `B2C-BATCH-YYYY-MM-DD-NNN` (mirrors `BATCH-YYYY-MM-DD-TEST` from `test_webhook.py:29`)

**Error Handling Pattern (from `n8n_code_node.js`):**
```javascript
try {
  // operation
} catch (e) {
  errors.push(`Error processing ${lead.full_name}: ${e.message}`);
}
```

**Notion Text Field Truncation (from `n8n_code_node.js:105`):**
```javascript
{ rich_text: [{ text: { content: String(value).substring(0, 2000) } }] }
```

**Python httpx Pattern (from `create_notion_databases.py:55–73`):**
```python
def create_database(client: httpx.Client, title: str, icon: str, properties: dict) -> str:
    payload = { "parent": {...}, "icon": {...}, "title": [...], "properties": properties }
    response = client.post(f"{BASE_URL}/databases", json=payload)
    if response.status_code != 200:
        print(f"❌ Failed: {response.status_code}")
        sys.exit(1)
    return response.json()["id"]
```

**Dedup Pattern (B2B company name, `n8n_code_node.js:70–81`):**
```javascript
const searchData = await notionRequest('POST', `/databases/${LEADS_DB_ID}/query`, {
  filter: { property: 'Company Name', title: { equals: lead.company_name } },
  page_size: 1,
});
if (searchData.results && searchData.results.length > 0) {
  duplicates++; continue;
}
```
B2C equivalent uses `url` filter on `Intent Source URL` property.

**Notion URL Property Filter:**
```javascript
filter: { property: 'Intent Source URL', url: { equals: lead.intent_source_url } }
```

---

## B2C DATA MODEL

### B2C Leads Database Schema

| Property | Notion Type | Notes |
|----------|-------------|-------|
| `Full Name` | `title` | Primary identifier (replaces Company Name) |
| `Phone` | `phone_number` | Required for billable lead |
| `Email` | `email` | Required for billable lead |
| `Province` | `select` | Same 9 SA provinces as B2B |
| `City / Area` | `rich_text` | |
| `Intent Signal` | `rich_text` | Exact quote/description of what they posted/said |
| `Intent Source` | `select` | Hellopeter / Gumtree / Facebook Group / MyBroadband / OLX / Twitter-X / Reddit / Other |
| `Intent Source URL` | `url` | **Dedup key** — link to the actual post |
| `Intent Date` | `date` | When they posted/expressed interest |
| `Vehicle Make / Model` | `rich_text` | Optional — if mentioned in their post |
| `Vehicle Year` | `number` | Optional |
| `Call Script Opener` | `rich_text` | AI-generated opener referencing their specific signal |
| `Data Confidence` | `select` | High / Medium / Low |
| `Sources Used` | `rich_text` | Which sources Hugo used to find/enrich |
| `Intent Strength` | `number` | 0–10: how explicitly did they ask? |
| `Urgency Score` | `number` | 0–10: how urgent/recent is their need? |
| `Status` | `select` | Pending QA → QA Approved → Sent to Call Centre → Contacted → Interested / Converted / Not Interested. Also: QA Rejected, Duplicate |
| `QA Review Date` | `date` | |
| `QA Notes` | `rich_text` | |
| `Rejection Reason` | `select` | Disconnected Number / Duplicate / No Interest Expressed / Invalid Contact / Out of Area / Other |
| `Date Added` | `date` | Ingestion timestamp |
| `Date Delivered` | `date` | When status changed to "Sent to Call Centre" — set manually or by n8n |
| `Dispute Status` | `select` | Pending / Accepted / Rejected by Client / Disputed |
| `Dispute Reason` | `rich_text` | Free text from client if rejected |
| `Batch` | `relation` → B2C Batches DB | |
| `Source` | `relation` → Sources DB (shared) | |

**Manual Notion UI steps after creation (API limitation — cannot create formula/person properties via API):**
- `Rejection Deadline` — Formula: `dateAdd(prop("Date Delivered"), 5, "days")` *(approximate — business days not natively supported; note this in setup output)*
- `B2C Composite Score` — Formula: `prop("Intent Strength") * 0.6 + prop("Urgency Score") * 0.4`
- `QA Reviewed By` — Person property

### B2C Composite Scoring Model

```
B2C Composite Score = (Intent Strength × 0.6) + (Urgency Score × 0.4)
```

- **Intent Strength (0–10):** How explicitly did the person ask for vehicle tracking?
  - 9–10: "Looking to buy a tracker ASAP", posted in tracker comparison group
  - 7–8: "Recommend a good tracker", "had car broken into, need tracker"
  - 5–6: Mentioned tracking in passing, complained about a competitor
  - 3–4: General car security post without specific tracking mention
- **Urgency Score (0–10):** How urgent/recent is the need?
  - 9–10: Post within 24 hours, mentions recent theft/break-in
  - 7–8: Post within 7 days, active threat context
  - 5–6: Post within 30 days, general interest
  - 3–4: Older post, dormant interest

Score ≥ 7 → High priority (Phase B: auto-approve)
Score 4–6.9 → Medium priority (manual QA)
Score < 4 → Low priority (Phase B: auto-reject)

### B2C Batches Database Schema

| Property | Notion Type | Notes |
|----------|-------------|-------|
| `Batch ID` | `title` | e.g. `B2C-BATCH-2026-03-11-001` |
| `Run Date` | `date` | |
| `Status` | `select` | Running / Completed / Partial / Failed |
| `Leads Found` | `number` | Raw count from Hugo |
| `Leads After Dedup` | `number` | After URL dedup |
| `Sources Crawled` | `rich_text` | Which sources Hugo scraped this run |
| `Errors` | `rich_text` | Error log |
| `API Cost (USD)` | `number` | |

### B2C Webhook Payload Schema

```json
{
  "batch_id": "B2C-BATCH-2026-03-11-001",
  "segment": "B2C",
  "leads": [
    {
      "full_name": "John Smith",
      "phone": "+27 82 555 1234",
      "email": "john.smith@gmail.com",
      "province": "Gauteng",
      "city": "Johannesburg",
      "intent_signal": "Posted on Joburg Car Security Facebook group: 'Had my BMW broken into last night near Sandton, looking for a reliable car tracker ASAP'",
      "intent_source": "Facebook Group",
      "intent_source_url": "https://www.facebook.com/groups/12345/posts/67890",
      "intent_date": "2026-03-10",
      "vehicle_make_model": "BMW 3 Series",
      "vehicle_year": 2020,
      "call_script_opener": "Hi John, I saw you mentioned you're looking for a car tracker after your break-in near Sandton. I understand how stressful that is — I'd love to help you protect your BMW quickly. Do you have 5 minutes?",
      "data_confidence": "High",
      "sources_used": "Facebook public group post (Joburg Car Security)",
      "intent_strength": 9,
      "urgency_score": 10
    }
  ]
}
```

### B2C Deduplication Logic

```
For each incoming lead:
  1. Query B2C Leads DB: filter WHERE Intent Source URL = lead.intent_source_url
     → If found: skip (duplicate post), increment duplicates
  2. (No phone/email dedup needed — same person posting again = fresh signal = new lead)
  Create the lead.
```

This is intentionally simpler than the 90-day window concept. The `intent_source_url` uniquely identifies the specific post/signal. If the same person posts again, that's a new signal and qualifies as a new lead. The 90-day contractual rule is the *client's* dedup obligation (they check their own CRM), not Hugo's.

---

## B2C DATA SOURCES

Seed these into the shared Sources DB:

| Source Name | Source Type | URL | POPIA Status | Notes |
|-------------|-------------|-----|--------------|-------|
| Hellopeter — Competitor Reviews | Consumer Review | https://www.hellopeter.com | Compliant | 1–2 star reviews of Cartrack/Matrix/Tracker = churn candidates |
| Gumtree SA — Wanted Ads | Business Directory | https://www.gumtree.co.za | Compliant | "Wanted: vehicle tracker" listings |
| Facebook Public Groups — SA Car Security | Social Media | https://www.facebook.com | Caution Required | Public group posts only. Never collect from private groups or personal profiles. |
| MyBroadband Forums | Social Media | https://mybroadband.co.za/forum | Compliant | Security/motoring sub-forums; tech-savvy users |
| OLX SA — Wanted | Business Directory | https://www.olx.co.za | Compliant | Wanted section for vehicle security |
| Reddit r/southafrica | Social Media | https://www.reddit.com/r/southafrica | Compliant | Public posts about car security, tracking |

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation — Notion Schema

Create the B2C Notion databases and seed sources.

**Tasks:**
- Write `create_b2c_database.py` (mirrors `create_notion_databases.py` structure)
- Creates B2C Leads DB with schema above
- Creates B2C Batches DB
- Seeds 6 B2C sources into the shared Sources DB
- Writes B2C DB IDs to `notion_config.json` (append, don't overwrite)

### Phase 2: Core Implementation — n8n Code Node

Write the B2C ingestion Code node.

**Tasks:**
- Write `n8n_b2c_code_node.js` (mirrors `n8n_code_node.js` structure)
- Replace company-name dedup with intent_source_url dedup
- Map B2C payload fields to Notion properties (phone_number, email, url types)
- Add `segment` validation: reject payloads where `segment != "B2C"`

### Phase 3: Test Harness

Write test script with realistic B2C sample leads.

**Tasks:**
- Write `test_b2c_webhook.py` (mirrors `test_webhook.py`)
- 3 sample leads: Hellopeter churn candidate (high score), Gumtree Wanted ad (medium), Facebook group post (high urgency)
- Score preview: show Intent Strength, Urgency Score, B2C Composite Score

### Phase 4: Configuration Updates

Update config files so the system is documented and complete.

**Tasks:**
- Update `notion_config.json` with B2C DB IDs
- Update `.env` with `B2C_LEADS_DB_ID`, `B2C_BATCHES_DB_ID`, `B2C_WEBHOOK_URL`
- Update `CLAUDE.md` Architecture section and Key Files table
- Update `README.md` with B2C section

---

## STEP-BY-STEP TASKS

### TASK 1: CREATE `create_b2c_database.py`

- **IMPLEMENT**: Mirror `create_notion_databases.py` structure exactly. Functions: `check_config()`, `create_database()` (reuse pattern), `create_b2c_leads_database(client, sources_db_id, batches_db_id)`, `create_b2c_batches_database(client)`, `seed_b2c_sources(client, sources_db_id)`, `print_manual_steps(leads_db_id)`, `print_database_ids(batches_id, leads_id)`, `main()`
- **PATTERN**: `create_notion_databases.py:55–73` for `create_database()` helper — copy verbatim
- **PATTERN**: `create_notion_databases.py:119–141` for batches schema — mirror for B2C Batches
- **GOTCHA**: `phone_number` and `email` Notion property types use empty dicts `{}` as schema, same as `rich_text: {}`. Do NOT use `phone_number: {"format": "..."}` — they have no format option.
- **GOTCHA**: The B2C Leads DB title field is `Full Name` not `Company Name` — this is the Notion title property and the primary identifier for dedup display
- **GOTCHA**: `notion_config.json` already exists — read it, merge B2C IDs in, write back. Do NOT overwrite B2B IDs.
- **GOTCHA**: `sources_db_id` passed to B2C setup is the **existing** Sources DB (shared) — do NOT create a new Sources DB. Read the existing ID from `notion_config.json` or `.env` before running.
- **VALIDATE**: `python3 -m py_compile create_b2c_database.py`

**B2C Leads DB property schema snippet:**
```python
properties = {
    "Full Name": {"title": {}},
    "Phone": {"phone_number": {}},
    "Email": {"email": {}},
    "Province": {"select": {"options": [...same 9 provinces as B2B...]}},
    "City / Area": {"rich_text": {}},
    "Intent Signal": {"rich_text": {}},
    "Intent Source": {
        "select": {
            "options": [
                {"name": "Hellopeter", "color": "red"},
                {"name": "Gumtree", "color": "green"},
                {"name": "Facebook Group", "color": "blue"},
                {"name": "MyBroadband", "color": "orange"},
                {"name": "OLX", "color": "yellow"},
                {"name": "Twitter-X", "color": "gray"},
                {"name": "Reddit", "color": "purple"},
                {"name": "Other", "color": "default"},
            ]
        }
    },
    "Intent Source URL": {"url": {}},
    "Intent Date": {"date": {}},
    "Vehicle Make / Model": {"rich_text": {}},
    "Vehicle Year": {"number": {"format": "number"}},
    "Call Script Opener": {"rich_text": {}},
    "Data Confidence": {"select": {"options": [
        {"name": "High", "color": "green"},
        {"name": "Medium", "color": "yellow"},
        {"name": "Low", "color": "red"},
    ]}},
    "Sources Used": {"rich_text": {}},
    "Intent Strength": {"number": {"format": "number"}},
    "Urgency Score": {"number": {"format": "number"}},
    "Status": {"select": {"options": [
        {"name": "Pending QA", "color": "default"},
        {"name": "QA Approved", "color": "green"},
        {"name": "QA Rejected", "color": "red"},
        {"name": "Sent to Call Centre", "color": "blue"},
        {"name": "Contacted", "color": "purple"},
        {"name": "Interested", "color": "yellow"},
        {"name": "Converted", "color": "green"},
        {"name": "Not Interested", "color": "orange"},
        {"name": "Duplicate", "color": "gray"},
    ]}},
    "QA Review Date": {"date": {}},
    "QA Notes": {"rich_text": {}},
    "Rejection Reason": {"select": {"options": [
        {"name": "Disconnected Number", "color": "red"},
        {"name": "Duplicate", "color": "gray"},
        {"name": "No Interest Expressed", "color": "orange"},
        {"name": "Invalid Contact", "color": "red"},
        {"name": "Out of Area", "color": "purple"},
        {"name": "Other", "color": "default"},
    ]}},
    "Date Added": {"date": {}},
    "Date Delivered": {"date": {}},
    "Dispute Status": {"select": {"options": [
        {"name": "Pending", "color": "yellow"},
        {"name": "Accepted", "color": "green"},
        {"name": "Rejected by Client", "color": "red"},
        {"name": "Disputed", "color": "orange"},
    ]}},
    "Dispute Reason": {"rich_text": {}},
    "Batch": {"relation": {"database_id": batches_db_id, "single_property": {}}},
    "Source": {"relation": {"database_id": sources_db_id, "single_property": {}}},
}
```

**Manual steps to print (add to `print_manual_steps()`):**
1. `B2C Composite Score` — Formula: `prop("Intent Strength") * 0.6 + prop("Urgency Score") * 0.4`
2. `B2C Quality Gate` — Formula: `if(prop("B2C Composite Score") >= 7, "✅ Auto-Approve", if(prop("B2C Composite Score") >= 4, "⚠️ Review", "❌ Auto-Reject"))`
3. `Rejection Deadline` — Formula: `dateAdd(prop("Date Delivered"), 5, "days")` — note: approximation, not true business days
4. `QA Reviewed By` — Person property
5. Views: B2C QA Queue (Status = Pending QA, sorted by B2C Composite Score DESC), B2C Pipeline Kanban (grouped by Status), Dispute Tracker (filter: Date Delivered is not empty, Dispute Status = Pending)

---

### TASK 2: CREATE `n8n_b2c_code_node.js`

- **IMPLEMENT**: Mirror `n8n_code_node.js` structure. Add three new constants: `B2C_LEADS_DB_ID`, `B2C_BATCHES_DB_ID`, `SEGMENT = 'B2C'`
- **PATTERN**: `n8n_code_node.js:1–34` — copy `notionRequest()` helper verbatim (identical pattern)
- **PATTERN**: `n8n_code_node.js:37–41` — payload validation; add check for `body.segment === 'B2C'`
- **GOTCHA**: Dedup uses `url` filter not `title` filter. Notion filter for URL property: `{ property: 'Intent Source URL', url: { equals: lead.intent_source_url } }`. Only deduplicate if `lead.intent_source_url` is provided — if null/undefined, skip dedup check and create anyway.
- **GOTCHA**: `phone_number` Notion property value format: `{ phone_number: lead.phone }` (not `rich_text`)
- **GOTCHA**: `email` Notion property value format: `{ email: lead.email }` (not `rich_text`)
- **GOTCHA**: `Intent Source URL` is a `url` property: `{ url: lead.intent_source_url }`
- **GOTCHA**: `Intent Date` is a date: `{ date: { start: lead.intent_date } }` — validate it's a valid ISO date string before setting
- **VALIDATE**: Paste into n8n Code node → Save → no syntax errors shown in n8n UI

**Key property mapping differences from B2B:**
```javascript
// B2C-specific property mappings (add to properties object)
if (lead.phone) properties['Phone'] = { phone_number: lead.phone };
if (lead.email) properties['Email'] = { email: lead.email };
if (lead.intent_source_url) properties['Intent Source URL'] = { url: lead.intent_source_url };
if (lead.intent_date) properties['Intent Date'] = { date: { start: lead.intent_date } };
if (lead.intent_strength != null) properties['Intent Strength'] = { number: lead.intent_strength };
if (lead.urgency_score != null) properties['Urgency Score'] = { number: lead.urgency_score };
if (lead.vehicle_year != null) properties['Vehicle Year'] = { number: lead.vehicle_year };
```

**Dedup block (replaces B2B title dedup):**
```javascript
// B2C dedup: by intent_source_url only
if (lead.intent_source_url) {
  const searchData = await notionRequest('POST', `/databases/${B2C_LEADS_DB_ID}/query`, {
    filter: {
      property: 'Intent Source URL',
      url: { equals: lead.intent_source_url },
    },
    page_size: 1,
  });
  if (searchData.results && searchData.results.length > 0) {
    duplicates++;
    continue;
  }
}
```

---

### TASK 3: CREATE `test_b2c_webhook.py`

- **IMPLEMENT**: Mirror `test_webhook.py` structure. `get_sample_payload()` returns 3 realistic B2C leads. `main()` prints score preview (Intent Strength, Urgency Score, B2C Composite Score), POSTs to `B2C_WEBHOOK_URL` with Bearer auth.
- **PATTERN**: `test_webhook.py:27–169` — mirror `get_sample_payload()` structure; change company-centric fields to person-centric
- **PATTERN**: `test_webhook.py:192–197` — mirror score preview print block; replace fleet/need with intent_strength/urgency_score
- **GOTCHA**: Environment variable names: `B2C_WEBHOOK_URL` and `B2C_WEBHOOK_TOKEN` (or same token as B2B — confirm in .env)

**3 sample leads to include:**
1. **Thabo Dlamini** (Gauteng) — Hellopeter 1-star review of Cartrack: "Terrible service, looking to switch providers." Phone + email visible. intent_strength=7, urgency_score=6. Source: Hellopeter.
2. **Priya Naidoo** (KwaZulu-Natal) — Gumtree Wanted ad: "Wanted: Car tracker for Toyota Fortuner, recently had attempted hijacking in Umhlanga." intent_strength=9, urgency_score=9. Source: Gumtree.
3. **Werner van der Merwe** (Western Cape) — MyBroadband forum post: "Anyone compared Cartrack vs Netstar recently? Looking to install on my new Golf 8." intent_strength=6, urgency_score=5. Source: MyBroadband.

- **VALIDATE**: `python3 -m py_compile test_b2c_webhook.py`

---

### TASK 4: UPDATE `notion_config.json`

- **IMPLEMENT**: After running `create_b2c_database.py`, the script will write B2C IDs to `notion_config.json`. The script must READ the existing file first, MERGE the new keys, then WRITE back.
- **PATTERN**: `create_notion_databases.py:437–446` — replace with read-merge-write pattern
- **New keys to add**:
  ```json
  {
    "b2c_leads_database_id": "<generated>",
    "b2c_batches_database_id": "<generated>",
    "b2c_created_at": "<timestamp>"
  }
  ```
- **GOTCHA**: Do NOT use `open("notion_config.json", "w")` without reading first — this would delete B2B IDs. Use: `config = json.load(f)` then `config.update({...b2c keys...})` then write.

---

### TASK 5: UPDATE `CLAUDE.md`

- **UPDATE**: Architecture section — add B2C data flow below existing B2B flow
- **UPDATE**: Key files table — add `n8n_b2c_code_node.js`, `create_b2c_database.py`, `test_b2c_webhook.py`
- **ADD**: New `B2C Environment` section listing `B2C_LEADS_DB_ID`, `B2C_BATCHES_DB_ID`, `B2C_WEBHOOK_URL`
- **VALIDATE**: Read CLAUDE.md after update, confirm no B2B entries removed

---

## TESTING STRATEGY

### No formal test framework (project standard)

Project uses syntax checks only (`python3 -m py_compile`). Mirror this standard.

### Syntax Checks (after each file creation)

```bash
python3 -m py_compile create_b2c_database.py
python3 -m py_compile test_b2c_webhook.py
```

### Integration Test (end-to-end)

```bash
# Step 1: Create Notion databases
uv run create_b2c_database.py

# Step 2: Paste n8n_b2c_code_node.js into new n8n workflow at /webhook/b2c-lead-ingestion
# (manual step)

# Step 3: Run test
export B2C_WEBHOOK_URL="https://n8n.bigtorig.com/webhook/b2c-lead-ingestion"
export B2C_WEBHOOK_TOKEN="<same or new token>"
uv run test_b2c_webhook.py

# Expected: 3 leads appear in B2C Leads DB with Status = "Pending QA"
```

### Edge Cases to Verify

1. **Duplicate post URL**: Run `test_b2c_webhook.py` twice → second run: `leads_created: 0, duplicates_skipped: 3`
2. **Missing intent_source_url**: Lead with `null` intent_source_url should be created (no dedup check), not skipped
3. **Missing phone**: Lead with no phone should still be created (phone is desirable but not blocking)
4. **Same person, different URL**: Change `intent_source_url` on an existing lead's name → new lead should be created (person re-qualified)

---

## VALIDATION COMMANDS

### Level 1: Syntax Check

```bash
python3 -m py_compile create_b2c_database.py
python3 -m py_compile test_b2c_webhook.py
```

### Level 2: Database Setup

```bash
uv run create_b2c_database.py
# Verify output: ✅ Created 'B2C Leads' ✅ Created 'B2C Batches' + 6 sources seeded
# Verify notion_config.json has b2c_leads_database_id and b2c_batches_database_id
# Verify B2B IDs still present in notion_config.json
```

### Level 3: End-to-End Test

```bash
export B2C_WEBHOOK_URL="https://n8n.bigtorig.com/webhook/b2c-lead-ingestion"
export B2C_WEBHOOK_TOKEN="<token>"
uv run test_b2c_webhook.py
# Expected response: {"status":"success","leads_created":3,"duplicates_skipped":0}
```

### Level 4: Dedup Validation

```bash
uv run test_b2c_webhook.py   # Run a second time
# Expected: {"leads_created":0,"duplicates_skipped":3}
```

### Level 5: Notion UI Verification

- Open Notion → B2C Leads DB → confirm 3 leads with Status = "Pending QA"
- Confirm Phone, Email, Intent Signal, Intent Source URL fields populated
- Add manual formula properties (B2C Composite Score, Rejection Deadline) per setup instructions
- Create QA Queue view (Status = Pending QA, sort by B2C Composite Score DESC)
- Create Dispute Tracker view (Date Delivered is not empty, Dispute Status = Pending)

---

## ACCEPTANCE CRITERIA

- [ ] `create_b2c_database.py` creates B2C Leads DB with full schema (phone_number, email, url properties all present)
- [ ] `create_b2c_database.py` creates B2C Batches DB
- [ ] `create_b2c_database.py` seeds 6 B2C sources into existing shared Sources DB (does NOT create a new Sources DB)
- [ ] `notion_config.json` updated with B2C IDs without removing B2B IDs
- [ ] `n8n_b2c_code_node.js` can be pasted into n8n with no syntax errors
- [ ] `n8n_b2c_code_node.js` deduplicates on `intent_source_url` (not company name)
- [ ] `n8n_b2c_code_node.js` correctly maps `phone_number` and `email` Notion property types
- [ ] `test_b2c_webhook.py` sends 3 leads → all 3 created in Notion with Status = "Pending QA"
- [ ] Running test script twice → second run returns `duplicates_skipped: 3`
- [ ] B2B pipeline unaffected (test original `test_webhook.py` still works after all changes)
- [ ] `CLAUDE.md` updated with B2C architecture, files, and env vars

---

## COMPLETION CHECKLIST

- [ ] Task 1: `create_b2c_database.py` created and syntax-clean
- [ ] Task 2: `n8n_b2c_code_node.js` created
- [ ] Task 3: `test_b2c_webhook.py` created and syntax-clean
- [ ] Task 4: `notion_config.json` updated (B2C IDs added, B2B IDs preserved)
- [ ] Task 5: `CLAUDE.md` updated
- [ ] Database setup script run successfully against live Notion
- [ ] n8n B2C workflow created and Code node pasted
- [ ] End-to-end test passed (3 leads in Notion)
- [ ] Dedup test passed (second run = 0 created)
- [ ] B2B regression check passed (original test_webhook.py still works)
- [ ] Manual Notion formula properties added (B2C Composite Score, Rejection Deadline, Quality Gate)
- [ ] B2C QA Queue and Dispute Tracker views created in Notion UI

---

## NOTES

### Why separate B2C Leads DB (not same DB with Segment filter)

B2C leads have fundamentally different required fields (phone_number, email Notion types vs rich_text; intent_source_url as dedup key; no fleet scoring). Mixing schemas in one DB would leave many fields blank for most records and make the QA view confusing. Separate DBs also allow independent rollup/formula properties and Notion views without cross-contamination.

### Why intent_source_url as dedup key (not phone/email + 90-day window)

If the same person posts again on Gumtree or Facebook after their first lead was rejected or expired, that's a genuinely fresh signal and should be treated as a new lead. The 90-day window in the API agreement is the *client's* obligation (they check their own CRM for existing customers), not Hugo's scraping obligation. Using URL as the dedup key is simpler, more accurate, and avoids false duplicates when a person legitimately re-enters the market.

### POPIA Compliance Note

All B2C sources must be public posts where the individual voluntarily shared their contact details and intent. Never scrape private Facebook groups, WhatsApp groups, or personal profiles. The `POPIA Status` field in Sources DB should be set appropriately: Facebook Group = "Caution Required", others = "Compliant".

### Rejection Deadline — Business Days Limitation

Notion's formula engine does not natively calculate business days. The `dateAdd(prop("Date Delivered"), 5, "days")` formula gives a calendar day approximation. For strict compliance, Claire should be instructed to treat the deadline as 5 *business* days and adjust manually for weekends/public holidays.

### Phase B Auto-Approval (Future)

Once B2C pipeline is validated with real leads (suggest: 30+ leads reviewed, <20% rejection rate on high-score leads), add auto-approval logic to `n8n_b2c_code_node.js`: if `composite_score >= 7`, set Status = "QA Approved" and `Date Delivered` = now() at creation time. This mirrors the planned Phase B for B2B.

### Confidence Score

**8/10** — High confidence for one-pass implementation.
- Risk: Notion `phone_number` and `email` property type API behaviour needs validation (low risk — well documented)
- Risk: n8n `url` filter for dedup needs testing in live n8n Code node context (medium risk — confirm filter syntax works)
- Mitigated by: strong pattern from existing B2B Code node, clear field mapping table, explicit gotchas documented
