# PRD — Step 5 Bulk WhatsApp Canary Deploy



**Status:** Blocked at Stage 1 on cogstack-ui → Baileys networking. Resume after networking fix.

**Last updated:** 2026-05-06 07:30 UTC (end of session 1, decision made)

**Owner:** Charles

**Repo:** [`CognitiveStack/cogstack-leadgen`](https://github.com/CognitiveStack/cogstack-leadgen) on branch `feat/ui-phase-1`, HEAD `327341a`



---



## DECIDED — networking fix is Option 3 (containerize Baileys)



Charles picked Option 3 at end of session 1. Tomorrow's Claude should NOT re-ask which option to use. Proceed directly to executing the Baileys containerization plan in the "Networking fix — Option 3 execution plan" section below.



Time budget: ~60-90 minutes for migration. Then ~45-60 minutes for canary stages. Total ~2-2.5 hours of focused work.



Risks acknowledged (Charles knows these going in):

- Possible WhatsApp re-pair if auth_info ownership/permissions don't survive container migration

- Bad MAC errors in current session continue regardless

- pm2 vs Docker ops inconsistency (only Baileys becomes Dockerized; other CogStack services stay pm2)

- Any other consumers reaching Baileys via host port 3456 break unless port is published



---



## Workflow setup — three layers



This work runs across three concurrent contexts. Tomorrow's Claude (the model reading this PRD) is **layer 1** and should not write code into bigtorig directly.



| Layer | Role | What it does |

|---|---|---|

| **1. Claude (this chat)** | Design + review | Writes briefs Charles pastes into tmux. Reviews agent output. Drafts gate plans. Investigates failures. Should NEVER push, commit, or modify production directly. |

| **2. tmux Claude Code agent on bigtorig** | Building agent | Receives briefs from Charles, writes code in `/opt/services/cogstack-leadgen/`. Runs tests in container. Drafts commits but does NOT push. Has bypassPermissions/autoMemory enabled. |

| **3. Charles in Zed Editor terminal** | Operator + integrator | Runs git/curl/eyeball checks. Executes `docker compose` flips, env edits, UFW changes. Pushes commits. Runs verification commands. Pastes evidence between layers 1 ↔ 2. |



### Discipline rules for layer 1 (this Claude)



- Layer 2 is the agent. Briefs must include explicit "DO NOT push, DO NOT commit without approval, DO NOT add Co-Authored-By trailers, DO NOT write to memory after commits"

- Always require `cat` not `Read` tool for showing files (Read collapses long output in UI)

- Always require `git commit -F-` heredoc for multi-line commits, NEVER `git commit -m "$(cat <<EOF...)"` (latter mangles Unicode)

- After context compaction, agent must re-verify state before acting (it has form for skipping sanity checks under pressure)

- For canary stages: layer 3 (Charles) drives, agent is passive log-grep helper only



---



## Current state — production environment



### What's deployed and working



- **cogstack-ui** Docker container on bigtorig, image `cogstack-leadgen-cogstack-ui`, container `cogstack-ui`, on `caddy-shared` Docker network (gateway `172.19.0.1`, bridge `br-ce7c1422d007`), exposed via Caddy at `https://leads.bigtorig.com` (basic_auth `claire` / `charles`)

- All five Step 5 gates shipped: 5.1 (multi-select + eligibility), 5.2 (preview + atomic batches), 5.3 (async worker + restart safety + retry/abort matrix), 5.4 (HTMX progress polling), 5.5 (results view + kill-switch)

- Latest commit `327341a` on `feat/ui-phase-1`, pushed to origin

- Production rebuilt from this commit. Verified: `docker exec cogstack-ui python3 -c "from cogstack_ui.whatsapp.worker import _KILLSWITCH_FILE; print(_KILLSWITCH_FILE)"` → `/app/logs/batch.killswitch`



### Pre-canary modifications still live (need restore after canary completes)



| Change | File | Purpose | Restore command |

|---|---|---|---|

| MAX_SENDS_PER_DAY raised 40→100 | `/opt/projects/whatsapp-lookup/lookup.js` | Fit canary's 56 total sends in one day | `mv /opt/projects/whatsapp-lookup/lookup.js.bak /opt/projects/whatsapp-lookup/lookup.js && pm2 restart whatsapp-lookup` |

| `COGSTACK_DRY_RUN=false` | `/opt/services/cogstack-leadgen/.env` | Enable real-mode sends | `sed -i.canarybak '/^# canary mode/d; /^COGSTACK_DRY_RUN=false$/d' .env && docker compose up -d cogstack-ui` |

| `extra_hosts: ["baileys:host-gateway"]` | `/opt/services/cogstack-leadgen/docker-compose.yml` | Was networking attempt, currently useless (host-gateway → 172.17.0.1, UFW-blocked) | Optional: leave or remove. Backup at `docker-compose.yml.pre-canary-bak` |

| Runtime iptables rule | DOCKER-USER chain | `sudo iptables -I DOCKER-USER 1 -i br-ce7c1422d007 -p tcp --dport 3456 -j ACCEPT` — currently ineffective (UFW intercepts before DOCKER-USER) | Wipes on reboot. If networking fix doesn't use iptables, just leave or wipe with `sudo iptables -D DOCKER-USER 1` |



### Pre-existing artifacts from yesterday's failed Stage 1



- One batch in `/app/logs/batches.json`: `1fd77dac-0645-48db-b3b6-a64d9b0965a2`, status=done, 0 sent, 1 failed (Test Charles Self / +27836177469). Reason: `[Errno -3] Temporary failure in name resolution`. Keep as record.

- Test prospect "Test Charles Self" / `+27836177469` / Claire-Prospects in Notion. Still eligible (failure was network-level, state.json never touched). Reuse for Stage 1 retry.

- Pre-canary state backups: `/app/logs/batches.pre-canary.json` and `/app/logs/outreach-state.pre-canary.json` (the latter empty because state.json didn't exist yet).



---



## The blocker — networking



**Problem:** cogstack-ui container cannot reach Baileys (host pm2 process on bigtorig, listening on `0.0.0.0:3456`).



**Tested and failing from inside container:**

- `http://baileys:3456` (DNS fail — no entry)

- `http://host.docker.internal:3456` (Linux Docker doesn't define this hostname)

- `http://172.17.0.1:3456` (default bridge gateway — times out, UFW blocks)

- `http://172.19.0.1:3456` (caddy-shared gateway — times out, UFW blocks)

- `http://100.126.59.117:3456` (bigtorig Tailscale IP — times out, UFW blocks)



**Root cause confirmed:** UFW's INPUT chain drops port 3456 before iptables DOCKER-USER rules can ACCEPT. UFW status shows port 3456 not in any allow list. Container traffic to host port 3456 dies at UFW INPUT regardless of source IP.



**From bigtorig host shell, all of these work** (loopback bypasses UFW): localhost:3456, 172.17.0.1:3456, 172.19.0.1:3456, 100.126.59.117:3456. So the issue is purely container → host crossing.



---



## Networking fix — Option 3 execution plan (containerize Baileys)



This is the locked-in plan. Tomorrow's Claude should help Charles work through these stages sequentially, asking for evidence at each step.



### Source state (from session 1 inspection)



```

/opt/projects/whatsapp-lookup/

├── auth_info/                  ← WhatsApp signal-protocol keys (CRITICAL — losing these = re-pair QR)

├── contact_names.json          ← 278 cached names cache

├── lookup.js                   ← Express HTTP server, listens on 0.0.0.0:3456, line 458

├── lookup.js.bak               ← cap-restoration backup (raised 40→100)

├── node_modules/               ← Baileys + libsignal + deps

├── package.json                ← node_modules manifest, Node 20-compatible

└── package-lock.json           ← lock file

```



Currently runs as: pm2 fork-mode process id 0 named `whatsapp-lookup`, started by user `charles`, listening 0.0.0.0:3456. `pm2 status` shows online. `pm2 logs whatsapp-lookup` shows occasional Bad MAC and MessageCounterError but `/health` returns connected:true with sendsToday:0, maxSendsPerDay:100, cachedNames:278.



### Pre-flight — audit existing Baileys consumers



Before changing anything, find what else reaches Baileys on the host. Tomorrow's Claude should run this as the first command:



```bash

# What's currently connecting to port 3456 on bigtorig?

sudo ss -tnp | grep 3456 | grep -v LISTEN



# Recent Baileys access — who's been hitting it?

pm2 logs whatsapp-lookup --lines 200 --nostream | grep -E "POST|GET" | tail -30



# Check for any cron/systemd jobs that might call Baileys

sudo grep -rE "3456|whatsapp-lookup" /etc/cron.* /etc/systemd/system/ 2>/dev/null | head

sudo crontab -l 2>/dev/null | grep -iE "3456|whatsapp"

crontab -l 2>/dev/null | grep -iE "3456|whatsapp"

```



If anything else accesses Baileys (cogstack-ui via the new container path is the main consumer, but possibly the lead-pipeline scrapers or n8n workflows), document it. Decision: either add port publish (`ports: ["3456:3456"]` in compose) to keep host accessibility, or migrate those consumers too.



### Stage A — Write Dockerfile for whatsapp-lookup



Create `/opt/projects/whatsapp-lookup/Dockerfile`:



```dockerfile

FROM node:20-slim



WORKDIR /app



# Copy manifest first for better layer caching

COPY package.json package-lock.json ./



# Install deps — production only

RUN npm ci --omit=dev



# Copy source

COPY lookup.js ./



# auth_info and contact_names.json mounted as volumes — NOT copied into image



EXPOSE 3456



CMD ["node", "lookup.js"]

```



Also create `/opt/projects/whatsapp-lookup/.dockerignore`:



```

node_modules

auth_info

contact_names.json

lookup.js.bak

*.log

.git

```



The .dockerignore prevents the existing host node_modules / auth_info from leaking into the image build context (the container will install fresh node_modules and mount auth_info from host).



### Stage B — Add Baileys to docker-compose.yml



Decision point: where does the Baileys service live in compose? Two options:



**Option B-i — same compose file as cogstack-ui** (`/opt/services/cogstack-leadgen/docker-compose.yml`)



Pro: single deployable unit, both services brought up together, hostname resolution via shared compose network is automatic.

Con: couples Baileys lifecycle to cogstack-leadgen project.



**Option B-ii — dedicated compose** (e.g. `/opt/services/whatsapp-lookup/docker-compose.yml`)



Pro: Baileys is logically separate, can be managed independently, doesn't entangle with cogstack-leadgen rebuilds.

Con: must explicitly attach to `caddy-shared` external network for cogstack-ui to reach it.



Recommended: **Option B-ii** (dedicated compose). Cleaner separation; matches CogStack's "one service per directory under /opt/services/" convention.



Create `/opt/services/whatsapp-lookup/` directory with this compose:



```yaml

services:

  baileys:

    build:

      context: /opt/projects/whatsapp-lookup

      dockerfile: Dockerfile

    container_name: baileys

    restart: unless-stopped

    user: "${UID:-1000}:${GID:-1000}"   # Match host user owning auth_info

    volumes:

      - /opt/projects/whatsapp-lookup/auth_info:/app/auth_info

      - /opt/projects/whatsapp-lookup/contact_names.json:/app/contact_names.json

    ports:

      - "127.0.0.1:3456:3456"   # Keep host loopback access for any existing consumers

    networks:

      - caddy-shared



networks:

  caddy-shared:

    external: true

```



Note the `user:` directive — without it the container runs as root and may write auth_info files with root ownership, breaking pm2 access if you ever rollback. Match host UID/GID to keep file ownership consistent. Find your UID/GID with `id -u` and `id -g` on bigtorig (likely 1000:1000 for charles).



The `ports: ["127.0.0.1:3456:3456"]` keeps Baileys reachable on bigtorig's localhost — preserves any pm2-era consumers via loopback, while keeping it private (not exposed on Tailscale or public interfaces).



### Stage C — Migration sequence



1. **Stop pm2 Baileys** (don't delete — keep as fallback)

   ```bash

   pm2 stop whatsapp-lookup

   pm2 status   # confirm "stopped"

   ```



2. **Verify host port 3456 freed**

   ```bash

   sudo ss -tlnp | grep 3456   # should be empty

   ```



3. **Build and start Baileys container**

   ```bash

   cd /opt/services/whatsapp-lookup

   docker compose build

   docker compose up -d

   sleep 5

   docker compose ps

   docker logs baileys --tail 30

   ```



4. **Watch the connection log carefully** — three possible outcomes:



   **Outcome 1 — connects with existing auth (best case):** logs show `[wa] Loaded 278 cached names from ./contact_names.json` followed by `[wa] Connected to WhatsApp` within ~10 seconds. No QR needed. Proceed to Stage D.



   **Outcome 2 — needs QR pair:** logs show a QR code or `[wa] Generating QR for pairing`. Scan QR with phone's WhatsApp Web > Link a Device. Wait for `[wa] Connected to WhatsApp`. Cached names will need to rebuild (auto-populates as messages flow). Proceed to Stage D.



   **Outcome 3 — auth_info permission errors:** logs show `EACCES: permission denied` on auth_info. UID/GID mismatch. Fix:

   ```bash

   docker compose down

   sudo chown -R $(id -u):$(id -g) /opt/projects/whatsapp-lookup/auth_info

   sudo chown $(id -u):$(id -g) /opt/projects/whatsapp-lookup/contact_names.json

   docker compose up -d

   ```

   Then re-watch logs.



5. **Verify health**

   ```bash

   # From bigtorig host (via published port)

   curl -s http://127.0.0.1:3456/health | python3 -m json.tool



   # From cogstack-ui container (via Docker network DNS — THIS IS THE FIX)

   docker exec cogstack-ui python3 -c "

   import urllib.request

   r = urllib.request.urlopen('http://baileys:3456/health', timeout=3)

   print(r.read().decode())

   "

   ```



   Both should return `{"ok":true,"connected":true,...}`.



### Stage D — Update cogstack-ui to use the Docker DNS hostname



```bash

cd /opt/services/cogstack-leadgen



# Remove the now-unused extra_hosts and runtime iptables rule

# (The extra_hosts line was a session 1 attempt that resolved to wrong gateway.)



# Edit docker-compose.yml, remove:

#     extra_hosts:

#       - "baileys:host-gateway"

# (Or leave; it'll be harmless since BAILEYS_URL hostname now resolves via Docker DNS instead.)



# BAILEYS_URL is already defaulted to "http://baileys:3456" in config.py

# So no .env change needed UNLESS you've explicitly set it elsewhere.

# Verify:

grep BAILEYS_URL .env   # should be empty (using default)



# Recreate cogstack-ui to pick up clean state

docker compose up -d cogstack-ui

sleep 4



# Verify

docker exec cogstack-ui python3 -c "

from cogstack_ui import config

print('BAILEYS_URL:', config.BAILEYS_URL)

import urllib.request

r = urllib.request.urlopen(f'{config.BAILEYS_URL}/health', timeout=3)

print(r.read().decode())

"

```



Optional cleanup: remove the runtime iptables rule (no longer needed):

```bash

sudo iptables -L DOCKER-USER -n --line-numbers | head

# If the port-3456 rule is at line 1, remove it:

sudo iptables -D DOCKER-USER 1

```



### Stage E — Smoke test before canary



```bash

# Trigger a Baileys lookup from cogstack-ui to confirm two-way comms work

docker exec cogstack-ui python3 -c "

from cogstack_ui.baileys.client import BaileysClient

from cogstack_ui import config

import asyncio



async def go():

    async with BaileysClient(config.BAILEYS_URL) as c:

        result = await c.health_check() if hasattr(c, 'health_check') else None

        print('Health check OK' if result else 'No health_check method, but URL reachable')



asyncio.run(go())

"

```



If smoke test passes, Baileys containerization is complete. Proceed to Stage 0 of canary plan (resumption pre-flight).



### Rollback plan if Stage A-E fails badly



```bash

# Stop new container

cd /opt/services/whatsapp-lookup && docker compose down



# Restart pm2 Baileys (still has all auth_info)

pm2 start whatsapp-lookup

pm2 status



# Verify host-only access still works

curl -s http://127.0.0.1:3456/health | python3 -m json.tool

```



You're back to session 1's state — Baileys works on host, container can't reach it. Then fall back to Option 1 (UFW rule) or Option 2 (host networking) per the alternatives in the original PRD spec.



### Filed for Phase 1.5 (post-canary)



If Option 3 succeeds, file as tech debt:

- pm2 vs Docker ops consistency: decide whether to migrate other services (Hermes Honcho, etc.) to Docker too, or keep mixed model with explicit per-service ops docs

- The pm2-resident `whatsapp-lookup` process can be deleted from pm2 after Docker-Baileys proves stable for ~1 week: `pm2 delete whatsapp-lookup && pm2 save`



---



## Alternative options (NOT chosen, kept for reference only)



If Option 3 falls through during execution and you need to fall back tomorrow, the alternatives from session 1's analysis:



- **Option 1:** UFW rule `sudo ufw allow from 172.19.0.0/16 to any port 3456 proto tcp` — keeps Baileys on host pm2, just opens firewall to caddy-shared bridge. ~15-30 min.

- **Option 2:** `network_mode: host` for cogstack-ui — bypasses Docker network entirely. ~5 min for compose edit but ~10-15 min for Caddy proxy_pass adjustment to `localhost:8000`. ~15-20 min total.



---



## Canary plan — Stages 1 through 4



Locked decisions from yesterday's session:

- Strict 4-stage progression (1 → 5 → 10 → 40), full eyeball stop between each

- File-based killswitch already shipped (`/app/logs/batch.killswitch`)

- No Telegram pinging; logs + batches.json + WhatsApp Web are sufficient

- Stage 1 recipient: Charles's own number `+27836177469`



### Stage 0 — Resumption pre-flight (after networking fix)



```bash

# Confirm pre-canary state still in place

cat /opt/services/cogstack-leadgen/.env | grep COGSTACK_DRY_RUN          # → false

grep "MAX_SENDS_PER_DAY = " /opt/projects/whatsapp-lookup/lookup.js | head -1  # → 100

docker exec cogstack-ui python3 -c "from cogstack_ui import config; print(config.DRY_RUN)"  # → False



# Confirm Baileys is still healthy

curl -s http://localhost:3456/health | python3 -m json.tool

# expect: connected:true, sendsToday:0, maxSendsPerDay:100, cachedNames:278



# CRITICAL — confirm container can NOW reach Baileys after networking fix

docker exec cogstack-ui python3 -c "

import urllib.request

from cogstack_ui import config

r = urllib.request.urlopen(f'{config.BAILEYS_URL}/health', timeout=3)

print(r.read().decode())

"

# expect: same JSON as above. If still timing out, networking fix not effective.

```



### Stage 1 — Single send to Charles's own number



Test prospect "Test Charles Self" / `+27836177469` already in Notion Claire DB.



1. Browser: `https://leads.bigtorig.com/prospects` (basic_auth claire/charles)

2. Search box: `+27836177469` (search is phone-only by design)

3. Verify row appears, checkbox enabled, Claire badge

4. Click checkbox → `1 / 40 selected`

5. Click "Send to 1 selected"

6. **Preview page eyeball:**

   - DRY-RUN banner GONE

   - Test Charles Self / Self Test in valid table

   - Message body in `<pre>` block, name correctly merged

   - Text input asking for `SEND-1` (NOT single-click confirm)

7. Type `SEND-1` exactly, click Confirm

8. Auto-redirect to `/outreach/batch/{uuid}`. Status partial polls every 2s. Watch for status=running → status=done within ~5s

9. **Phone should buzz.** Open WhatsApp, verify message arrived



**Verification commands:**

```bash

docker logs cogstack-ui --since 5m | grep "batch=" | grep -E "phase=start|phase=send|phase=recorded|phase=done"

# expect: phase=send result=sent (NOT result=dry_run, NOT phase=send_failed)



docker exec cogstack-ui cat /app/logs/outreach-state.json | python3 -m json.tool

# expect: 1 entry, +27836177469, dry_run:false



docker exec cogstack-ui cat /app/logs/batches.json | python3 -m json.tool

# expect: yesterday's failed batch + today's done batch with completed=[+27836177469]



curl -s http://localhost:3456/health | python3 -m json.tool

# expect: sendsToday:1

```



**Stage 1 success criteria:** WhatsApp message arrived on phone, all four log/state outputs match expected.



If failure on session corruption (Bad MAC errors during real send): re-pair Baileys procedure: `pm2 stop whatsapp-lookup && cp -r /opt/projects/whatsapp-lookup/auth_info /opt/projects/whatsapp-lookup/auth_info.broken.$(date +%s) && rm -rf /opt/projects/whatsapp-lookup/auth_info && pm2 start whatsapp-lookup` then scan QR.



### Stage 2 — Five real prospects



Select 5 QA-Approved B2C or B2B from /prospects (avoiding +27836177469 which is now in state.json). Type `SEND-5`. Watch ~15-25s wall clock with 3-5s jitter.



Verify: 5/5/0/0 counters, 5 rows on results page all `outcome=sent`, batches.json clean, WhatsApp Web spot-check 2 random sends, Notion records present for all 5.



### Stage 3 — Ten real prospects



Same as Stage 2 with 10 prospects. ~30-50s wall clock. **Practice eyeballing the kill-switch button** (visible while running, gone after done) but don't click it.



### Stage 4 — Forty real prospects



Full blast radius. ~120-200s wall clock. Watch progress bar advance smoothly. **Kill-switch is your safety net** — `docker exec cogstack-ui touch /app/logs/batch.killswitch` aborts cleanly, remaining prospects mark `not_attempted`.



After completion: 40 results page, WhatsApp Web spot-check 5 random, Notion records for all 40, batches.json final.



---



## Post-canary cleanup checklist



After Stage 4 completes successfully, in order:



1. **Restore Baileys cap:**

   ```bash

   mv /opt/projects/whatsapp-lookup/lookup.js.bak /opt/projects/whatsapp-lookup/lookup.js

   pm2 restart whatsapp-lookup

   curl -s http://localhost:3456/health | python3 -m json.tool   # confirm maxSendsPerDay:40

   ```



2. **Decision on DRY_RUN:** Leave `COGSTACK_DRY_RUN=false` if production is now operationally live, or restore to default (remove the line) if you want safe-by-default while you decide. Recommendation: leave `false` since the canary just validated production behavior.



3. **Clean up extra_hosts** (if not removed during networking fix):

   ```bash

   # Remove the now-unused lines from docker-compose.yml

   # Or leave — harmless

   ```



4. **Persist any iptables/UFW rules** added during networking fix (depends on Option 1/2/3 chosen).



5. **Optional — archive batches.json** if you want a clean slate for production ops:

   ```bash

   docker exec cogstack-ui cp -p /app/logs/batches.json /app/logs/batches.canary-archive.json

   ```



6. **Notion cleanup:** Delete or archive "Test Charles Self" record from Claire-Prospects DB.



7. **Do NOT delete state.json** — that's the dedup truth. Removing it would allow re-contacting all 56 canary recipients.



---



## Filed tech debt for Phase 1.5



Surfaced during yesterday's session:



1. `_REPO_ROOT` calculation in `apps/ui/src/cogstack_ui/config.py` resolves to `/app/.venv` inside container instead of `/app`. The dotenv fallback path is broken. Currently harmless because Docker's `env_file:` injects vars into `os.environ` first, but if anyone removes `env_file:` expecting dotenv fallback, it silently fails.



2. `/prospects` search is phone-only. Name search would be useful (e.g. searching "Test Charles Self" returns nothing because the Search button only matches phone numbers).



3. Prospects with null `Date Added` fall off the unfiltered `/prospects` list (sorts to bottom, beyond pagination cap). Real prospects with malformed Notion entries become un-findable until phone-searched.



4. UI bug: "Stop batch" button still rendered briefly when status=done (caching/polling lag). Visual only, not blocking.



5. Bad MAC errors / MessageCounterError in pm2 logs from earlier Baileys connection cycles. Session shows connected:true but encryption layer occasionally rejects messages. May need fresh QR pair if real sends start failing on session-protocol errors.



6. iptables rule for the canary-shared bridge needs persistence path — runtime rule wipes on reboot. Phase 1.5 issue: pick UFW or iptables-persistent and codify.



---



## Reference: yesterday's commit log



```

327341a feat: Step 5.5 — result-summary view + kill-switch

dd1e8b6 feat: Step 5.4 — HTMX progress polling for in-flight batches

408517e feat: Step 5.3 — async batch worker + restart safety + UI surfacing

5394aeb feat: Step 5.2 — preview + atomic batches.json

3761d86 feat: Step 5.1 — multi-select + eligibility helper

```



All five pushed to origin/feat/ui-phase-1.



---



## How to start tomorrow's session



Layer 1 (the new Claude conversation): paste this PRD as initial context. The networking fix decision is **already made** — Option 3 (containerize Baileys). Do NOT re-ask Charles to pick. Proceed directly to executing the "Networking fix — Option 3 execution plan" section above, working through Stage A → B → C → D → E sequentially with Charles. Ask for evidence at each stage transition.



After Option 3 stages complete (Baileys container live, cogstack-ui can reach `http://baileys:3456`), proceed to Stage 0 of the canary plan (resumption pre-flight).



Charles: paste this PRD into the new conversation, confirm Layer 1 understands "Option 3 already chosen, execute it," then drive execution from your Zed terminal. The pm2 → Docker migration is layer 3 work (you running commands), not layer 2 (no agent coding work needed for Baileys containerization).



Estimated total time tomorrow: ~60-90 min for Baileys migration + ~45-60 min for canary stages 1-4 + ~10 min post-canary cleanup = ~2-2.5 hours of focused work.
