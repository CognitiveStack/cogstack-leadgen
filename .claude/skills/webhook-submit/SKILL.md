---
name: webhook-submit
description: POSTs classified B2C lead batches to the n8n webhook on bigtorig. Reads from stdin. Supports --dry-run.
---

# webhook-submit

## Usage
  uv run scripts/submit.py                         # reads from stdin
  uv run scripts/submit.py --input classified.json
  uv run scripts/submit.py --dry-run               # prints payload, no POST
  uv run scripts/submit.py --source gumtree        # sets batch_id source label

## Output
{"submitted": N, "batch_id": "BATCH-YYYY-MM-DD-GUMTREE-B2C"}

## Credentials
Loads N8N_B2C_WEBHOOK_URL, N8N_B2C_BEARER_TOKEN from ~/.hermes/.env
