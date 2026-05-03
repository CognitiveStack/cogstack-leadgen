# cogstack-ui



Operations console for the CogStack Leadgen pipeline. Provides Claire and Charles with a unified web interface to browse, search, and outreach prospects across three Notion databases (B2C Leads, B2B Leads, Claire-Prospects).



Built with FastAPI + HTMX + Tailwind CDN + Jinja2. Async throughout. Containerised, behind Caddy reverse-proxy with basic_auth.



## Live deployment



| What | Where |

|---|---|

| URL | `https://leads.bigtorig.com` |

| Auth | Caddy `basic_auth` — users `claire` and `charles` (separate passwords) |

| Host | bigtorig (`82.25.116.252`) |



For deployment instructions, operational notes, and architecture details, see **[`docs/deployment.md`](../../docs/deployment.md)**.



## Local development



```bash

# From apps/ui/

uv sync

uv run uvicorn cogstack_ui.main:app --reload --port 8000

```



Open `http://localhost:8000`.



To talk to a local Baileys instance instead of the production one, set `BAILEYS_URL=http://localhost:3456` in your `.env`.



## Environment



Copy `.env` from the repo root or create at `/opt/services/cogstack-leadgen/.env`. Required:



| Variable | Default | Purpose |

|---|---|---|

| `NOTION_READONLY_TOKEN` | (required) | Read-only Notion integration |

| `NOTION_WRITE_TOKEN` | (required) | Write Notion integration |

| `BAILEYS_URL` | `http://baileys:3456` | WhatsApp service URL |

| `OUTREACH_STATE_PATH` | `/app/logs/outreach-state.json` | Shared state file path (in container) |

| `COGSTACK_DRY_RUN` | `true` | Set to `false` to enable real WhatsApp sends |



The codebase NEVER reads `NOTION_API_KEY` directly. Read paths use the readonly token; write paths use the write token. This enforces blast-radius separation by token capability. See PRD §4.



## Docker



```bash

# From repo root

docker compose up -d cogstack-ui

```



The container joins the `caddy-shared` external network and is reverse-proxied at `leads.bigtorig.com` by Caddy.



## Architecture



| Concern | Read |

|---|---|

| Why this UI exists, what it covers | [`docs/prd-ui-phase-1.md`](../../docs/prd-ui-phase-1.md) |

| Deployment + operations | [`docs/deployment.md`](../../docs/deployment.md) |

| Notion DB schemas (auto-generated) | [`apps/ui/src/cogstack_ui/notion/schema.py`](src/cogstack_ui/notion/schema.py) |

| WhatsApp message template | [`apps/ui/src/cogstack_ui/whatsapp/templates.py`](src/cogstack_ui/whatsapp/templates.py) |

| Production script (template source of truth) | [`scripts/whatsapp_outreach.py`](../../scripts/whatsapp_outreach.py) |

| Session history & lessons | [`docs/session-summary-*.md`](../../docs/) |



## Notes for future work



- **Filters on `/prospects`** (DB-of-origin, status, date range) — deferred to Phase 1.5

- **Bulk WhatsApp send** — Step 5

- **Drag-drop ingest** (Excel/XML) — Step 6

- **Help docs** rendered at `/help` — Step 7

- **Per-user audit attribution** via Caddy basic_auth header — Phase 2



---



*Last updated: 2026-05-02 (after Step 4 deployment). See [`docs/session-summary-2026-05-02.md`](../../docs/session-summary-2026-05-02.md) for context.*
