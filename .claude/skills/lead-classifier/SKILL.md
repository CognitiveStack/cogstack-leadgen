---
name: lead-classifier
description: Classifies raw B2C leads via OpenRouter LLM. Filters seller/irrelevant ads, scores intent and urgency, outputs B2C webhook-ready JSON.
---

# lead-classifier

## Usage
  uv run scripts/classify.py                       # reads from stdin
  uv run scripts/classify.py --input leads.json
  uv run scripts/classify.py --dry-run             # prints without outputting JSON

## Output
B2C webhook-ready JSON array (matching n8n b2c-lead-ingestion schema).

## Credentials
Loads OPENROUTER_API_KEY from ~/.hermes/.env
