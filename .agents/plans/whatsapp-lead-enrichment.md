# Feature: Phone-to-Name Enrichment & WhatsApp Qualification

## Feature Description

Enrich B2C leads by resolving phone numbers to real names before they reach Notion, then optionally send a WhatsApp qualification message to confirm interest. The primary lookup method is WhatsApp (Baileys) — SA WhatsApp penetration is ~95%, making it the most reliable name resolver for South African mobile numbers. Supplementary sources (Truecaller, PhoneInfoga) serve as fallbacks for non-WhatsApp numbers.

## User Story

As Charles (pipeline engineer),
I want leads with phone numbers to be automatically enriched with the prospect's real name,
So that Notion shows "Thabo Dlamini" instead of "Unknown" and Claire can QA leads with full context.

As Charles,
I want the option to send a friendly WhatsApp message to leads and only create Notion records for those who respond with interest,
So that the B2C call centre only receives warm, pre-qualified leads who have already engaged.

## Problem Statement

1. **Name resolution**: Gumtree ads rarely show the poster's full name. Phone numbers are extracted, but leads arrive in Notion as "Unknown". WhatsApp profiles typically show real names — and ~95% of SA mobile users are on WhatsApp.

2. **Lead quality**: Even with buyer-intent filtering, scraped leads are cold — the person posted an ad days/weeks ago. A WhatsApp message that gets a positive response proves the lead is still active and interested.

3. **Current state**: The existing pipeline flow is: scrape → filter → POST to Notion. All qualification happens after the lead is in Notion (Claire's manual QA). WhatsApp qualification would filter BEFORE Notion, saving Claire's time.

## Solution Statement

Two-phase feature:

### Phase A: Phone-to-Name Lookup (passive, no messaging)

Add a phone number → name resolution step to `gumtree_to_b2c.py` and `hellopeter_scraper.py`. Primary source is WhatsApp (Baileys), with optional Truecaller and PhoneInfoga fallbacks.

**Lookup cascade (in priority order):**

| Priority | Source | SA Coverage | Cost | Status |
|----------|--------|-------------|------|--------|
| 1 | **WhatsApp (Baileys)** | ~95% of SA mobile | Free | ✅ Service built, pending QR auth |
| 2 | **Truecaller (unofficial)** | Excellent DB | Free (fragile, ~20/day/account) | Future enhancement |
| 3 | **PhoneInfoga** | Variable | Free (OSINT, hit-or-miss) | Future enhancement |

**Why WhatsApp is primary (not fallback):**
- ~95% SA mobile penetration — highest hit rate of any source
- `pushName` from WhatsApp profiles usually contains real names
- Already built and integrated (`gumtree_to_b2c.py --whatsapp`)
- Free, no API costs
- Truecaller has no free API — unofficial wrappers break frequently and get accounts banned
- Sync.me, CallApp, SA WhitePages: no usable APIs, limited SA coverage

**Account type: WhatsApp Business**

Baileys `onWhatsApp()` lookup works identically from both personal and Business accounts. WhatsApp Business is chosen because:
- Phase B outreach looks more professional from a Business profile
- Business accounts are expected to message non-contacts — less likely to be flagged
- Avoids needing to switch account type later (re-auth, new QR scan)
- No tradeoff for Phase A — lookups are identical

### Phase B: WhatsApp Qualification Outreach

After name lookup, send a templated WhatsApp message via the dedicated Business account. Only create Notion leads for prospects who respond positively.

**Message template:**
```
Hi {name}, I came across your Gumtree ad about vehicle trackers.
I work with a tracking company and we have competitive rates
with same-day installation in {city}.
Would you like me to send you a quick quote? 😊
```

**Qualification flow:**
```
Gumtree scrape → filter → LLM classify → WhatsApp name lookup
    → Send qualification message
    → Wait for response (up to 48 hours)
    → Response = interested? → POST to B2C webhook → Notion
    → No response / not interested → Log, don't create Notion lead
```

## Feature Metadata

**Feature Type**: New Capability (lead enrichment + qualification)
**Estimated Complexity**: Medium (Phase A), High (Phase B)
**Primary Systems Affected**: `scripts/gumtree_to_b2c.py` (add enrichment step), `scripts/hellopeter_scraper.py`, Node.js WhatsApp service
**Dependencies**: Baileys (Node.js), authenticated WhatsApp Business session on bigtorig

---

## IMPLEMENTATION PLAN

### Phase A: Phone-to-Name Lookup

**Goal:** Resolve phone numbers to real names before leads hit Notion. No messages sent.

#### Task A0: Set up WhatsApp Business account on Phone 3

1. Register the new SIM number with **WhatsApp Business** app on Phone 3 (Samsung SM-J720F)
2. Configure business profile:
   - **Display name:** Charles Bates (or chosen name)
   - **Business name:** Vehicle Tracking Solutions (or chosen name)
   - **Profile picture:** Add a credible photo
   - **Business description:** Short line about vehicle tracking services
3. Use the account normally for 2 weeks before heavy automated lookups (account aging)
4. Do NOT connect Phone 1 (personal) or Phone 2 (Hugo/dental) to Baileys — only Phone 3

#### Task A1: Set up Baileys WhatsApp session on bigtorig

```bash
# On bigtorig:
mkdir -p /opt/projects/whatsapp-lookup
cd /opt/projects/whatsapp-lookup
npm init -y
npm install @whiskeysockets/baileys qrcode-terminal
```

Create `lookup.js` — a simple HTTP service:
```javascript
// POST /lookup { phone: "+27821234567" }
// Returns: { exists: true, name: "Thabo Dlamini", jid: "27821234567@s.whatsapp.net" }
```

- Listens on `localhost:3456` (Tailscale-only, not exposed)
- On first run: prints QR code for WhatsApp authentication
- Persists auth state to `auth_info/` directory
- Rate limiting: see revised limits below

#### Task A2: Add WhatsApp lookup to `gumtree_to_b2c.py`

After LLM enrichment, before POST:
```python
def whatsapp_lookup(phone: str) -> str | None:
    """Look up WhatsApp profile name for a phone number."""
    try:
        resp = httpx.post(
            "http://localhost:3456/lookup",
            json={"phone": phone},
            timeout=10.0,
        )
        data = resp.json()
        if data.get("exists") and data.get("name"):
            return data["name"]
    except Exception:
        pass
    return None
```

Add `--whatsapp` flag to enable lookup (disabled by default until service is running).

#### Task A3: Validate Phase A

```bash
# Start WhatsApp lookup service on bigtorig
cd /opt/projects/whatsapp-lookup && node lookup.js
# Scan QR code with WhatsApp Business on Phone 3

# Run bridge with WhatsApp enrichment
uv run python scripts/gumtree_to_b2c.py --whatsapp --dry-run
# Expected: leads show resolved names instead of "Unknown"
```

### Phase B: WhatsApp Qualification Outreach

**Goal:** Send qualification messages, only create leads for responders.

#### Task B1: Add send capability to WhatsApp service

Extend `lookup.js`:
```javascript
// POST /send { phone: "+27821234567", message: "Hi Thabo, ..." }
// Returns: { sent: true, messageId: "..." }
```

#### Task B2: Add response tracking

Extend `lookup.js` with webhook callback:
```javascript
// When a reply is received from a prospect:
// POST http://localhost:PORT/webhook/whatsapp-reply
// { phone: "+27...", message: "Yes, please send a quote", timestamp: "..." }
```

Store pending outreach in a local SQLite DB:
```sql
CREATE TABLE outreach (
    phone TEXT PRIMARY KEY,
    ad_url TEXT,
    lead_json TEXT,  -- full enriched lead, ready to POST
    message_sent_at TIMESTAMP,
    response TEXT,
    response_at TIMESTAMP,
    status TEXT DEFAULT 'pending'  -- pending, responded, expired, not_interested
);
```

#### Task B3: Create qualification script

`scripts/whatsapp_qualify.py`:
1. Read outreach DB for leads with `status = 'pending'` and `message_sent_at > 48 hours ago` → mark expired
2. Read outreach DB for leads with `status = 'responded'` and positive response → POST to B2C webhook
3. Run on a cron (every 6 hours) or triggered by the WhatsApp reply webhook

#### Task B4: Integrate into pipeline

Update `gumtree_to_b2c.py` with `--qualify` flag:
```
--qualify: instead of POSTing directly to webhook, send WhatsApp message
           and store lead in outreach DB. whatsapp_qualify.py handles the
           webhook POST after response is received.
```

---

## RATE LIMITS & BAN AVOIDANCE

### What's actually enforced?

WhatsApp does not publish hard rate limits for presence checks. The limits below are based on Baileys community experience and conservative safety margins.

**Baileys `onWhatsApp()` is a lightweight presence check** — the same call that happens when you add a new contact in WhatsApp. It's far lighter than sending messages.

### Revised Rate Limits

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Delay between lookups | 2–5 seconds (random jitter) | Mimics natural contact-adding behaviour |
| Lookups per session | 50–100 | Safe for established accounts |
| Sessions per day | 2–3 with 30–60 min cooldown | Avoids sustained bot-like patterns |
| Daily capacity | 150–200 | Well within safe range after aging |
| Account aging before heavy use | **2 weeks minimum** | New accounts are more aggressively monitored |
| Chunk size | 10 lookups per chunk | 30–60 sec pause between chunks |

**Batch processing pattern:**
```
Batch of 50 numbers:
  - Process in chunks of 10
  - Random 2–5 sec delay between each lookup
  - 30–60 sec pause between chunks
  - Total time: ~10–15 minutes for 50 numbers
```

### Phase B (messaging) — separate, stricter limits

| Parameter | Value |
|-----------|-------|
| Messages per day | Start at 3–5, monitor for warnings |
| Ramp-up period | 2 weeks at low volume before increasing |
| Max daily messages | 10–15 (never bulk-blast) |

---

## RISK ASSESSMENT

### WhatsApp Account Ban Risk

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Bulk name lookups trigger ban | Low (with jitter + aging) | Rate limit with random delays, age account 2 weeks, chunk lookups |
| Sending unsolicited messages (Phase B) | Medium-High | Keep volume low (3-10/day), conversational tone, no links |
| Phone number reported as spam | Low-Medium | Message is relevant (they posted about trackers), include opt-out |
| WhatsApp TOS violation | Medium | Using unofficial API — account could be suspended |

**Mitigation strategy:**
- Use **dedicated WhatsApp Business number** (Phone 3) — expendable if banned
- **Never connect Phone 1 (personal) or Phone 2 (Hugo/dental) to Baileys**
- Start with Phase A only (name lookup, no messaging) — low ban risk
- Phase B: start with 3-5 messages/day, monitor for warnings
- If banned: switch to a new SIM, or fall back to Phase A only
- Consider WhatsApp Business API for Phase B if volume grows (requires Meta approval)

### POPIA Compliance

- **Phase A (name lookup)**: Low risk — no message sent, no data shared with prospect
- **Phase B (outreach)**: Medium risk — sending unsolicited messages to people who posted public ads
  - Mitigated: Gumtree ads are public, person shared their phone number publicly
  - Include opt-out: "Reply STOP if you're not interested"
  - Don't store or share personal data beyond what's needed for the lead

---

## ACCEPTANCE CRITERIA

### Phase A
- [x] WhatsApp Business account set up on Phone 3 with professional profile (2026-03-20)
  - Display name: Charles B | Business: Vehicle Tracking Solutions | Photo: SUV | Number: +27631650794
- [ ] Account aged for 2 weeks with normal use before heavy lookups (target: ~2026-04-03)
- [x] WhatsApp lookup service (Baileys) runs on bigtorig (2026-03-20)
- [x] QR code scanned with Phone 3's WhatsApp Business (2026-03-20)
- [x] Connection verified: `exists` check works, auth persists in `auth_info/` (2026-03-20)
- [x] Name resolution code fixed (2026-03-20): `makeInMemoryStore` removed (not in Baileys v6.7), replaced with event-based contact cache + `presenceSubscribe` + `syncFullHistory: true`
- [x] Name resolution **verified working** on Phone 1 (personal): "Claire Shuttleworth" resolved from 278 cached contacts (2026-03-20)
- [ ] Name resolution on Phone 3 (Business): returns `null` — account has no chat history yet, cache is empty. Will work after aging + normal use builds history.
- [ ] `gumtree_to_b2c.py --whatsapp` resolves phone → name for valid WhatsApp numbers
- [ ] Leads in Notion show real names instead of "Unknown" (when WhatsApp name available)
- [x] Rate limiting: `lookup.js` updated to 2–5 sec random jitter, 100/session (2026-03-20)
- [x] Graceful fallback: if service is down or number not on WhatsApp, name stays "Unknown" (2026-03-29 — `whatsapp_lookup()` catches all HTTP + timeout errors, returns None, name stays as LLM-resolved or "Unknown")

### Phase B
- [ ] Qualification message sent to buyer-intent leads
- [ ] Responses tracked in SQLite outreach DB
- [ ] Only responded + interested leads POSTed to webhook
- [ ] 48-hour expiry for non-responses
- [ ] Dedicated WhatsApp Business number (Phone 3 — not Phone 1 or Phone 2)
- [ ] Opt-out handling: "STOP" replies mark lead as not_interested

---

## DEPENDENCIES & PREREQUISITES

| Prerequisite | For Phase | Status |
|-------------|-----------|--------|
| Gumtree scraper working | A & B | ✅ Done (Fetcher-based, 50x faster) |
| Gumtree → webhook bridge script | A & B | ✅ Done (`scripts/gumtree_to_b2c.py`) |
| Node.js on bigtorig | A & B | ✅ Available (v22.22.0) |
| Baileys lookup service | A & B | ✅ Built (`/opt/projects/whatsapp-lookup/lookup.js`) |
| `--whatsapp` flag in bridge script | A | ✅ Done |
| `--whatsapp-url` override flag | A | ✅ Done (2026-03-29) — allows runtime port switching for Phone 1 fallback |
| Spare WhatsApp number + SIM (Phone 3) | A & B | ✅ Available (Samsung SM-J720F, dedicated leadgen number) |
| WhatsApp Business app installed on Phone 3 | A & B | ✅ Done (2026-03-20) — "Charles B" / "Vehicle Tracking Solutions" / +27631650794 |
| WhatsApp Business profile configured | A & B | ✅ Done (2026-03-20) — SUV photo, description set |
| QR code scanned with Phone 3 | A & B | ✅ Done (2026-03-20) — linked as "Baileys Lookup", auth persists |
| Baileys connection verified | A & B | ✅ Done (2026-03-20) — `exists` works on both phones |
| `lookup.js` v2 with event-based name cache | A & B | ✅ Done (2026-03-20) — `syncFullHistory`, `presenceSubscribe`, `contact_names.json` persistence |
| Name resolution verified (Phone 1) | A | ✅ Done (2026-03-20) — "Claire Shuttleworth" resolved, 278 names cached |
| Name resolution on Phone 3 | A | **Pending — needs chat history (aging). Re-test ~2026-04-03** |
| Temp Phone 1 instance | A | ✅ Running at `/opt/projects/whatsapp-lookup-personal/` PORT=3457 — **delete after Phone 3 verified** |
| 2-week account aging period | A | **In progress — started 2026-03-20, target ~2026-04-03** |
| Webhook retry logic (3× backoff) | A & B | ✅ Done (2026-03-29) — `gumtree_to_b2c.py`, `hellopeter_scraper.py` |
| LLM retry logic (429 + 5xx) | A | ✅ Done (2026-03-29) — `gumtree_to_b2c.py` |
| Structured logging (`logs/` dir) | A & B | ✅ Done (2026-03-29) — console INFO + file DEBUG |
| Unified runner `b2c_run.py` | A & B | ✅ Done (2026-03-29) — orchestrates both pipelines, JSON run log |
| Health check `b2c_healthcheck.py` | A & B | ✅ Done (2026-03-29) — checks all 4 external dependencies |
| Cron schedule on bigtorig | A & B | **Pending — reference in `crontab-b2c.txt`, install with `crontab -e`** |

## NOTES

### Recommended implementation order

1. ~~**Now:** Set up WhatsApp Business on Phone 3, configure profile, start aging~~ ✅ Done 2026-03-20
2. ~~**Now:** Build `gumtree_to_b2c.py` (bridge script)~~ ✅ Done
3. ~~**Now:** Connect Baileys to Phone 3, verify connection~~ ✅ Done 2026-03-20
4. ~~**Now:** Fix name resolution — `makeInMemoryStore` removed in Baileys v6.7, replaced with event-based cache~~ ✅ Done 2026-03-20
5. ~~**Now:** Verify name resolution works (Phone 1 temporary instance)~~ ✅ Done 2026-03-20 — "Claire Shuttleworth" confirmed
6. ~~**Now → April 3rd:** Use Phone 1 temp instance (PORT=3457) for limited lookups. Use Phone 3 normally to build chat history.~~ ✅ In progress — `.env` set to PORT=3457, `--whatsapp-url` fallback wired
7. ~~**Harden pipeline:** retry logic, structured logging, unified runner, health check~~ ✅ Done 2026-03-29 — see `b2c_run.py`, `b2c_healthcheck.py`, `logs/`
8. **~2026-04-03:** Re-scan Phone 3 QR (`rm -rf auth_info/` to force fresh `syncFullHistory`), verify name resolution, `sed` `.env` 3457→3456
9. **After Phone 3 verified:** Delete `/opt/projects/whatsapp-lookup-personal/`, unlink Phone 1 from Baileys
10. **Install cron** on bigtorig — `crontab -e`, paste from `crontab-b2c.txt`
11. **Then:** Phase B (WhatsApp qualification) — filters to only warm leads
12. **Future:** Add Truecaller unofficial wrapper as supplementary fallback

### Why not other lookup services?

Research conducted 2026-03-20 found that WhatsApp/Baileys is the best primary source for SA numbers:
- **Truecaller**: Excellent SA database, but no free API. Unofficial Python wrappers require burner accounts, break frequently, get banned after ~20-50 lookups. Possible future supplement.
- **Sync.me**: No API at all. Consumer app only.
- **CallApp**: No API. Limited SA coverage.
- **SA WhitePages**: Doesn't exist for mobile numbers. Telkom directory is landline-only.
- **PhoneInfoga**: Free OSINT tool, Google-dork-based. Hit-or-miss for SA numbers. Possible future fallback.

### Alternative to Baileys: whatsapp-web.js

If Baileys proves unstable, `whatsapp-web.js` is a more mature alternative:
```bash
npm install whatsapp-web.js
```
Same API pattern: `client.getNumberId('+27821234567')` checks existence, `client.getContactById(jid)` gets name.

### Bigtorig Runtime integration

The Bigtorig Runtime agent already has a WhatsApp channel on `+27639842638` (Phone 2). For Phase B, it could potentially:
- Receive replies and route them to the qualification script
- Use its existing message handling to have a brief conversation before qualifying

However, mixing lead outreach with the runtime's operational channel risks confusion. The dedicated Phone 3 Business number is safer.

### Key technical findings (2026-03-20)

- **Baileys v6.7.21** removed `makeInMemoryStore()` — contact names must be collected from socket events (`contacts.upsert`, `contacts.update`, `messages.upsert`, `messaging-history.set`)
- **`onWhatsApp(jid)` does NOT return pushName** — it only confirms existence + returns canonical JID
- **`syncFullHistory: true`** must be set in socket config, AND auth must be fresh (`rm -rf auth_info/`) to trigger initial contact sync
- **`presenceSubscribe(jid)`** sometimes triggers a `contacts.update` event with pushName — used as on-demand fallback (5s wait)
- **New accounts with no chat history** will have empty contact caches — name resolution requires the account to have prior interactions
- **Contact names persist** to `contact_names.json` on disk — survives service restarts

### Confidence Score: 8/10

Phase A (name lookup) is straightforward — 9/10 confidence. Code proven working, "Claire Shuttleworth" resolved. WhatsApp's ~95% SA penetration means high hit rate.
Phase B (outreach + qualification) has more moving parts and WhatsApp ban risk — 6/10 confidence.
Revised upward from 7/10 overall after confirming WhatsApp is the best primary source (not just a fallback).
