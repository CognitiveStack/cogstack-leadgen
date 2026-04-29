---
name: leadgen-pipeline
description: Orchestrates the full B2C lead pipeline: scrape/search → classify → submit. Hermes cron entry point.
---

# leadgen-pipeline

## Usage
  uv run scripts/pipeline.py --source=gumtree      # Firecrawl Gumtree scrape
  uv run scripts/pipeline.py --source=search       # Exa/Tavily competitor search
  uv run scripts/pipeline.py --source=all          # both sources (gumtree + search)
  uv run scripts/pipeline.py --source=all --dry-run

## Logs
Run summaries written to: ~/vault/projects/cogstack-leadgen/pipeline-runs/run-YYYY-MM-DD-HHmmss.json

## Credentials
Loads all keys from ~/.hermes/.env
