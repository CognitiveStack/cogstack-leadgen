# Deployment & Operations — cogstack-ui



Operational guide for the CogStack Leadgen UI. Covers first-time deployment to bigtorig, day-to-day operations, and the gotchas worth knowing.



For the project intro and quickstart, see [`apps/ui/README.md`](../apps/ui/README.md). For why this UI exists and what it covers, see [`prd-ui-phase-1.md`](prd-ui-phase-1.md).



## First-time deployment to bigtorig



The order matters — do these steps in sequence the first time. Subsequent deploys only need step 5.



### 1. Logs directory ownership



The container runs as `appuser` (uid `10001`). The host-mounted `logs/` directory must be writable by that uid.



```bash

sudo chown -R 10001:10001 /opt/services/cogstack-leadgen/logs/

```



If you skip this, the first WhatsApp send returns 500 with `PermissionError: '/app/logs/outreach-state.json'` in the container logs.



### 2. Environment variables



Copy `.env` to `/opt/services/cogstack-leadgen/.env`. See [Environment](#environment) below for the full list.



### 3. Generate Caddy basic_auth password hashes



For each user (e.g. `claire`, `charles`), generate a separate hash:



```bash

docker exec -it caddy caddy hash-password

# Enter password (won't display)

# Confirm password

# Copy the $2a$14$... hash

```



Store the passwords in your password manager. Hashes are NOT secrets, but the underlying passwords are.



### 4. Add Caddy block to the live Caddyfile



Edit `/opt/infra/local-ai-packaged/Caddyfile` and append:



```caddyfile

# CogStack Leadgen UI — operations console for Claire and Charles

leads.bigtorig.com {

    encode zstd gzip

    basic_auth {

        claire   $2a$14$YOUR_CLAIRE_HASH_HERE

        charles  $2a$14$YOUR_CHARLES_HASH_HERE

    }

    reverse_proxy cogstack-ui:8000

}

```



Validate before reloading:



```bash

docker exec caddy caddy validate --config /etc/caddy/Caddyfile

# Expect: "Valid configuration"

```



**Reload via container restart, NOT `caddy reload`** (see [Caddy bind-mount gotcha](#caddy-bind-mount-gotcha)):



```bash

docker restart caddy

```



### 5. Start the cogstack-ui container



```bash

cd /opt/services/cogstack-leadgen

docker compose up -d cogstack-ui

```



Verify it joined the `caddy-shared` network:



```bash

docker inspect cogstack-ui --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'

# Expect: an IP on the caddy-shared subnet

```



### 6. DNS



Point `leads.bigtorig.com` at the bigtorig public IP via Cloudflare. Either grey cloud (DNS only) or orange cloud (proxied) works. Caddy will negotiate a Let's Encrypt cert on first traffic.



If using orange cloud, set Cloudflare's SSL/TLS mode to **Full** or **Full (strict)** — it expects an HTTPS origin. If Caddy doesn't have a cert yet (first deploy), temporarily switch to grey cloud, hit the URL once to trigger cert issuance, then switch back to orange.



### 7. Verify the URL works



```bash

curl -sI https://leads.bigtorig.com 2>&1 | head -10

# Expect: HTTP/2 401, www-authenticate: Basic

```



Open `https://leads.bigtorig.com` in a browser. Sign in as `claire` or `charles`. Dashboard should render with live counts.



## Operational notes



### DRY_RUN mode (the safety net)



`COGSTACK_DRY_RUN` defaults to `true`. In dry-run mode:



- WhatsApp sends are **logged** but not delivered (Baileys `/send` is skipped)

- Notion writes **proceed** (reversible by Charles if needed)

- `outreach-state.json` records the attempt with `dry_run: true` flag for audit

- The UI shows "Dry-run mode" notices in confirmation panels



To enable real sends:



```bash

echo 'COGSTACK_DRY_RUN=false' >> /opt/services/cogstack-leadgen/.env

docker compose up -d cogstack-ui  # restart to pick up env

docker exec cogstack-ui python -c "from cogstack_ui import config; print('DRY_RUN =', config.DRY_RUN)"

# Expect: DRY_RUN = False

```



Don't flip this until you've confirmed the workflow end-to-end with dry-run. Production sends touch real WhatsApp accounts of real people.



### Caddy bind-mount gotcha



The Caddyfile is bind-mounted into the Caddy container at `/etc/caddy/Caddyfile`. When you edit the host file with nvim (or any editor that uses atomic writes — write temp + rename), the inode changes. Docker bind mounts are inode-based, so the container keeps reading the *old* inode and `caddy reload` doesn't see your changes.



**After any Caddyfile edit, run:**



```bash

docker restart caddy

```



Not `caddy reload`. The restart forces Docker to re-resolve the bind mount.



This affects all sites Caddy serves (n8n, supabase, langfuse, etc.) for the ~5 second restart window. Acceptable for internal infra; just know.



To verify your edit landed in the container's view:



```bash

docker exec caddy md5sum /etc/caddy/Caddyfile

sudo md5sum /opt/infra/local-ai-packaged/Caddyfile

# Hashes must match. If they differ, restart caddy.

```



### Notion property type quirks



`schema.py` is auto-generated from `scripts/introspect_notion.py`. The `Literal[...]` type annotations capture the value space but **don't** distinguish between Notion's `select` and `status` property types. These look identical in code but require different write payloads:



| Field | DB | Notion type | Write payload |

|---|---|---|---|

| `Status` | B2C Leads | `select` | `{"select": {"name": "..."}}` |

| `Status` | B2B Leads | `select` | `{"select": {"name": "..."}}` |

| `Submitted to Pipeline` | Claire-Prospects | `checkbox` | `{"checkbox": true/false}` |

| `Response Status` | Claire-Prospects | `select` | `{"select": {"name": "..."}}` |



Before adding any new write path, verify the property type with `GET https://api.notion.com/v1/databases/{id}` and inspect `properties.{name}.type`. The naming convention is misleading — a field called `Status` is NOT necessarily Notion's `status` property type.



### Atomicity ordering for sends



`outreach-state.json` is the source of truth for "was this phone already sent to." The send flow is:



```

normalize phone → idempotency check → Baileys send → state append → Notion write (best-effort)

```



If Notion fails *after* Baileys succeeds, the state file still records the send. Idempotency holds: the next click sees "Already sent." A missing Notion record can be re-created manually; a duplicate WhatsApp send to a real human cannot be undone.



### Two Notion integrations



This app uses two separate Notion integrations with different capabilities:



| Integration | Token env var | Capability |

|---|---|---|

| `cogstack-leadgen-readonly` | `NOTION_READONLY_TOKEN` | Read content only |

| `cogstack-leadgen-write` | `NOTION_WRITE_TOKEN` | Read + Update + Insert |



The codebase NEVER reads `NOTION_API_KEY`. Read paths use the readonly token; write paths use the write token. This enforces blast-radius separation by token capability.



## Common operations



### Restart the UI after a code change



```bash

cd /opt/services/cogstack-leadgen

docker compose build cogstack-ui

docker compose up -d cogstack-ui

```



### Tail UI logs



```bash

docker logs cogstack-ui --tail 100 -f

```



### Inspect the outreach state file



```bash

cat /opt/services/cogstack-leadgen/logs/outreach-state.json | python3 -m json.tool | head -50

```



### Re-introspect Notion DBs (after schema changes)



```bash

cd /opt/services/cogstack-leadgen

uv run python scripts/introspect_notion.py

# Then commit apps/ui/src/cogstack_ui/notion/schema.py

```



### Reload Caddy after editing Caddyfile



```bash

docker exec caddy caddy validate --config /etc/caddy/Caddyfile

# Expect: "Valid configuration"

docker restart caddy   # NOT `caddy reload` — see bind-mount gotcha above

```



## Environment



| Variable | Default | Purpose |

|---|---|---|

| `NOTION_READONLY_TOKEN` | (required) | Read-only Notion integration |

| `NOTION_WRITE_TOKEN` | (required) | Write Notion integration |

| `BAILEYS_URL` | `http://baileys:3456` | WhatsApp service URL |

| `OUTREACH_STATE_PATH` | `/app/logs/outreach-state.json` | Shared state file path (in container) |

| `COGSTACK_DRY_RUN` | `true` | Set to `false` to enable real WhatsApp sends |



`OUTREACH_STATE_PATH` is the in-container path. The volume mount in `docker-compose.yml` maps host `./logs/` to container `/app/logs/`. Both the script (on desktop-wsl) and the UI (on bigtorig) read/write the same file via this mount, ensuring cross-surface idempotency.



## Troubleshooting



### `HTTP/2 525` when hitting the URL



Cloudflare is in front (orange cloud) but Cloudflare can't establish HTTPS to the origin. Either:

- Caddy hasn't issued a cert yet → temporarily switch to grey cloud, trigger cert issuance, switch back

- Cloudflare SSL mode is wrong → set to Full or Full (strict)



### `502 Bad Gateway` when hitting the URL



Caddy reached, but can't talk to `cogstack-ui` container. Check:

```bash

docker compose ps cogstack-ui   # Is it running?

docker logs cogstack-ui --tail 50   # Any startup errors?

docker network inspect caddy-shared | grep cogstack-ui   # On the network?

```



### `PermissionError` on first WhatsApp send



`logs/` directory ownership wrong. Fix:

```bash

sudo chown -R 10001:10001 /opt/services/cogstack-leadgen/logs/

docker compose restart cogstack-ui

```



### Caddy reload doesn't pick up Caddyfile changes



Bind-mount inode mismatch (see [Caddy bind-mount gotcha](#caddy-bind-mount-gotcha)). Use `docker restart caddy` instead of `caddy reload`.



### `Status is expected to be select` from Notion



Wrong write payload shape — using `{"status": {...}}` for a `select` property. Check the property type via:

```bash

curl -s "https://api.notion.com/v1/databases/{db_id}" \

  -H "Authorization: Bearer $NOTION_WRITE_TOKEN" \

  -H "Notion-Version: 2022-06-28" \

  | python3 -c "import json,sys; d=json.load(sys.stdin); print({k: v.get('type') for k,v in d['properties'].items()})"

```



---



*Last updated: 2026-05-02 (after Step 4 deployment). See [`session-summary-2026-05-02.md`](session-summary-2026-05-02.md) for context.*
