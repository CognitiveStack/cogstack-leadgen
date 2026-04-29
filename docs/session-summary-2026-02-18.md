# AI Lead Generation System — Session Summary
## Date: 18 February 2026

---

## PROJECT OVERVIEW

**Client**: Paul (via Claire Shuttleworth) — large SA car tracking company with 500-person call centre.
**Goal**: AI-powered lead generation delivering 10 new customers/month.
**Architecture**: OpenClaw (Pi4) → n8n webhook (Hostinger) → Notion (shared CRM)

---

## WHAT WE ACCOMPLISHED THIS SESSION

### 1. Strategy Document ✅
- Created `ai_lead_gen_strategy.docx` — professional brainstorming document for Claire
- Covers: 4-stage pipeline, POPIA compliance, B2B vs B2C comparison, data sources, scoring model
- Cover page: "Prepared by Cogstack / In partnership with Claire Shuttleworth"

### 2. Notion Schema Design v2 (with QA) ✅
- Created `notion_schema_v2.docx` — full technical specification
- Added QA workflow: Pending QA → QA Approved → Sent to Call Centre → Contacted → Converted
- Added Prospect Profile section (Paul's "description" requirement): Prospect Summary, Company Profile, Fleet Assessment, Tracking Need Reasoning, Call Script Opener
- Phase A: manual QA for months 1-2, Phase B: auto-approve score ≥ 7

### 3. Notion Workspace Setup ✅
- Created "Charles's Space" workspace on Notion
- Created "AI Lead Pipeline" parent page
- Created Notion API integration: "Cogstack Lead Ingestion"
- Ran `create_notion_databases.py` — created all 3 databases:
  - **Leads** (DB ID: `30b89024-cd3d-8123-94f7-ee27b966bc0d`)
  - **Sources** (DB ID: `30b89024-cd3d-81b1-ab3a-c900965b5d64`)
  - **Batches** (DB ID: `30b89024-cd3d-8198-bb49-ec8e3e9fe40e`)
- Seeded 6 data sources (CIPC, eTenders, Yellow Pages, LinkedIn, SAPS Crime Stats, Road Freight Association)
- Added Composite Score and Quality Gate formula properties
- Added QA Reviewed By (Person) property
- Created QA Queue view (table, filtered by Pending QA, sorted by Composite Score)
- Created Full Pipeline view (Kanban board, grouped by Status)
- Deleted duplicate databases that were created by accidental double-run

### 4. n8n Workflow Setup (PARTIALLY COMPLETE)
- Created Notion API credential: "Notion-Cogstack Lead Ingestion"
- Created Header Auth credential: "Header Auth account 2" with Bearer token
- Bearer token: `1951a0fc1ba5e577c1dc50ac78833c6acd76f9ade858361396cc3eb438877257`
- **v1 workflow** (8 nodes with Notion nodes): Had issues with property mappings and validation conditions. UNPUBLISHED — keep but don't use.
- **v2 workflow** (3 nodes with Code node): Created and partially tested. Uses direct Notion API calls via `$http.request()`.

---

## WHAT STILL NEEDS TO BE DONE (NEXT SESSION)

### Immediate — Get test leads into Notion:
1. Open the **v2 workflow** ("Lead Ingestion v2 — OpenClaw to Notion")
2. Click the **"Process Leads (Notion API)"** Code node
3. **Replace the JavaScript code** with the contents of `n8n_code_node.js` (already downloaded)
   - The new code uses `$http.request()` instead of `fetch` (which isn't available in n8n)
4. In the new code, replace `REPLACE_WITH_YOUR_NOTION_API_KEY` with your actual `ntn_...` key
5. Database IDs are already hardcoded correctly in the code
6. Ensure Webhook node has "Header Auth account 2" credential attached
7. **Publish** and **Activate** the workflow
8. Test with production URL:
   ```bash
   cd ~/cogstack-leadgen
   export WEBHOOK_URL="https://n8n.bigtorig.com/webhook/lead-ingestion-v2"
   export WEBHOOK_TOKEN="1951a0fc1ba5e577c1dc50ac78833c6acd76f9ade858361396cc3eb438877257"
   uv run test_webhook.py
   ```
9. Expected result: 3 leads appear in Notion with "Pending QA" status
10. Check Batches database for batch record "BATCH-2026-02-18-TEST"

### After test leads work:
- Add Rollup properties manually (Leads Generated on Sources, QA Approved on Batches)
- Create remaining views (Approved — Ready to Send, QA Rejected, High Priority, etc.)
- Invite Claire as Editor, Paul as Commenter
- Reconnect validation node in v2 workflow (optional, low priority)
- Configure production webhook for OpenClaw Phase 1.5

### Longer term:
- Write OpenClaw crawl + enrichment instructions
- Configure OpenClaw to POST to the n8n webhook
- First real batch from eTenders/CIPC data
- Iterate scoring based on QA feedback
- Postgres dedup index for faster exact matching
- WhatsApp/email notification to Claire on new batches

---

## FILES IN ~/cogstack-leadgen/

| File | Purpose | Status |
|------|---------|--------|
| `create_notion_databases.py` | Creates all 3 Notion databases | ✅ Done |
| `notion_config.json` | Database IDs and config | ✅ Generated |
| `test_webhook.py` | Sends 3 test leads to n8n | ✅ Ready |
| `n8n_lead_ingestion_workflow.json` | v1 workflow (8 nodes) | ⚠️ Had issues |
| `n8n_lead_ingestion_v2.json` | v2 workflow (3 nodes) | ✅ Imported |
| `n8n_code_node.js` | Fixed code for v2 Code node | 🔄 NEEDS TO BE PASTED |
| `SETUP_GUIDE.md` | Setup reference guide | ✅ Reference |
| `pyproject.toml` | UV project config | ✅ Done |

## FILES SHARED WITH CLAIRE (via download)

| File | Purpose |
|------|---------|
| `ai_lead_gen_strategy.docx` | Strategy document for Claire |
| `notion_schema_v2.docx` | Technical schema with QA workflow |

---

## KEY CREDENTIALS & URLs

- **Notion workspace**: Charles's Space
- **Notion API key**: starts with `ntn_...` (stored locally)
- **Notion page**: AI Lead Pipeline
- **n8n instance**: https://n8n.bigtorig.com
- **Webhook (v2)**: https://n8n.bigtorig.com/webhook/lead-ingestion-v2
- **Bearer token**: `1951a0fc1ba5e577c1dc50ac78833c6acd76f9ade858361396cc3eb438877257`

---

## ARCHITECTURE DIAGRAM

```
OpenClaw (Pi4, Tailscale)
    │
    │ POST JSON (batch_id + leads[])
    ▼
n8n Webhook (Hostinger, Tailscale)
    │
    │ Code node: validate, dedup, create
    ▼
Notion API
    │
    ├── Batches DB (batch record)
    ├── Leads DB (individual leads, Status = "Pending QA")
    └── Sources DB (reference data)
    
    ▼
Claire/Paul QA Review (Notion UI)
    │
    ├── QA Approved → Sent to Call Centre
    └── QA Rejected → Feeds back into AI tuning
```
