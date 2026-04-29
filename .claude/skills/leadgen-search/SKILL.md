---
name: leadgen-search
description: Finds B2C vehicle tracker leads via Exa and Tavily semantic search — competitor churn, forum posts, theft signals. Returns JSON for lead-classifier.
---

# leadgen-search

## Usage
  uv run scripts/search.py                         # runs all default B2C queries
  uv run scripts/search.py --type=churn            # Hellopeter/competitor churn
  uv run scripts/search.py --type=forums           # forum + Reddit signals
  uv run scripts/search.py --type=theft            # recent theft → tracking need
  uv run scripts/search.py --query "custom query"  # ad hoc

## Output
JSON array to stdout. Same schema as scrape.py output (title, description, phone, location, price, adid, url, scraped_at). Source field = "Exa" or "Tavily".

## Credentials
Loads EXA_API_KEY, TAVILY_API_KEY from ~/.hermes/.env
