# Cogstack Lead Generation

AI-powered lead generation system for a South African car tracking company. Delivers qualified B2B leads through automated data collection, enrichment, and a human QA workflow.

## Architecture

```
OpenClaw (Pi4, Tailscale)
    |
    | POST JSON (batch_id + leads[])
    v
n8n Webhook (Hostinger, Tailscale)
    |
    | Code node: validate, dedup, create
    v
Notion API
    |
    +-- Batches DB (batch records)
    +-- Leads DB (individual leads, Status = "Pending QA")
    +-- Sources DB (reference data)
    |
    v
QA Review (Notion UI)
    |
    +-- QA Approved -> Sent to Call Centre
    +-- QA Rejected -> Feeds back into AI tuning
```

## Project Structure

```
cogstack-leadgen/
+-- main.py                            # Entry point
+-- create_notion_databases.py         # One-time Notion DB setup script
+-- test_webhook.py                    # Send test leads to n8n webhook
+-- n8n_code_node.js                   # JavaScript for n8n v2 Code node
+-- n8n_lead_ingestion_workflow.json   # n8n v1 workflow export (deprecated)
+-- notion_config.json                 # Notion database IDs
+-- pyproject.toml                     # Python project config (uv)
+-- .env                               # Environment variables (not committed)
```

## Setup

### Prerequisites

- Python 3.13+ with [uv](https://docs.astral.sh/uv/)
- A Notion workspace with an API integration
- An n8n instance with webhook access

### Install Dependencies

```bash
uv sync
```

### Environment Variables

Create a `.env` file:

```bash
NOTION_API_KEY=ntn_your_secret_here
NOTION_PAGE_ID=your_page_id_here
```

### Create Notion Databases

```bash
uv run create_notion_databases.py
```

This creates three databases under your Notion page: **Leads**, **Sources**, and **Batches** with the full schema including QA workflow properties.

### Test the Webhook

```bash
export WEBHOOK_URL="https://your-n8n-instance.com/webhook/lead-ingestion-v2"
export WEBHOOK_TOKEN="your_bearer_token"
uv run test_webhook.py
```

Sends 3 test leads. Expected result: leads appear in Notion with "Pending QA" status.

## QA Workflow

1. Leads arrive with status **Pending QA** and a composite score
2. QA reviewer checks prospect profile (summary, fleet assessment, call script opener)
3. Leads scoring >= 7 can be auto-approved (Phase B)
4. **QA Approved** leads move to **Sent to Call Centre**

## Data Sources

- CIPC (company registrations)
- eTenders (government tenders)
- Yellow Pages
- LinkedIn
- SAPS Crime Stats
- Road Freight Association
