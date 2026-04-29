---
name: leadgen-scraper
description: Scrapes Gumtree vehicle-tracker buyer-intent ads using Firecrawl API. Returns JSON array for lead-classifier.
---

# leadgen-scraper

## Usage
  uv run scripts/scrape.py gumtree
  uv run scripts/scrape.py gumtree --max 30 --out /tmp/leads.json

## Output
JSON array to stdout. Schema: { title, description, phone, location, price, adid, url, scraped_at }

## Credentials
Loads FIRECRAWL_API_KEY from ~/.hermes/.env
