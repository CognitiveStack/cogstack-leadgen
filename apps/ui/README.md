# cogstack-ui

Operations console for the CogStack Leadgen pipeline.

## Run locally

```bash
# From apps/ui/
uv sync
uv run uvicorn cogstack_ui.main:app --reload --port 8000
```

Open http://localhost:8000

## Environment

Copy `.env` from the repo root. Required:

| Variable | Purpose |
|---|---|
| `NOTION_READONLY_TOKEN` | Read-only Notion integration — dashboard, search, list views |
| `NOTION_WRITE_TOKEN` | Write Notion integration — status updates, ingest (Step 4+) |
| `BAILEYS_URL` | WhatsApp service URL (default: `http://baileys:3456`) |

Never set `NOTION_API_KEY` in this app. See PRD §4.

## Docker

```bash
# From repo root
docker compose up -d
```

The container joins the `caddy-shared` external network. Caddy proxies
`leads.bigtorig.com` → `cogstack-ui:8000`.

## Starlette 1.0 note

This app uses Starlette 1.0+. `TemplateResponse` takes `(request, name)`
not `(name, {"request": request})`. All route handlers follow this convention.
