# Feature: WhatsApp Lead Enrichment & Qualification

## Feature Description

Enrich Gumtree B2C leads by looking up phone numbers on WhatsApp to resolve real names, then optionally send a qualification message via the Bigtorig Runtime agent. Only leads who respond with interest become "qualified leads" in Notion — turning cold scraped data into warm, engaged prospects.

## User Story

As Charles (pipeline engineer),
I want Gumtree leads with phone numbers to be automatically enriched with the prospect's real name from WhatsApp,
So that Notion shows "Thabo Dlamini" instead of "Unknown" and Claire can QA leads with full context.

As Charles,
I want the Bigtorig Runtime agent to send a friendly WhatsApp message to Gumtree leads and only create Notion records for those who respond with interest,
So that the B2C call centre only receives warm, pre-qualified leads who have already engaged.

## Problem Statement

1. **Name resolution**: Gumtree ads rarely show the poster's full name. Phone numbers are extracted, but leads arrive in Notion as "Unknown". WhatsApp profiles typically show real names.

2. **Lead quality**: Even with buyer-intent filtering, scraped leads are cold — the person posted an ad days/weeks ago. A WhatsApp message that gets a positive response proves the lead is still active and interested.

3. **Current state**: The existing pipeline flow is: scrape → filter → POST to Notion. All qualification happens after the lead is in Notion (Claire's manual QA). WhatsApp qualification would filter BEFORE Notion, saving Claire's time.

## Solution Statement

Two-phase feature:

### Phase A: WhatsApp Name Lookup (passive, no messaging)

Add a phone number → WhatsApp profile name lookup step to `gumtree_to_b2c.py`. This resolves "Unknown" names before leads hit Notion. No messages sent — purely passive enrichment.

**Technical approach options:**

| Method | Pros | Cons | Feasibility |
|--------|------|------|-------------|
| **whatsapp-web.js** (Node.js library) | Full WhatsApp Web API, contact sync reveals names | Requires authenticated WhatsApp session, TOS grey area | High — well-maintained, widely used |
| **Baileys** (Node.js) | Lightweight WhatsApp Web socket library, `onWhatsApp()` checks number existence + returns push name | No browser needed, fast | High — used by many bots |
| **Manual contact sync** | Add number to phone contacts, sync reveals name | Not automatable | Low |
| **WhatsApp Business API (official)** | Fully compliant, supported | Cannot look up names — only send templates to opted-in users | Not applicable for name lookup |
| **Agent-browser** (existing tool) | Use Claude Code's browser agent to load web.whatsapp.com, search number | No extra deps, already available | Medium — fragile, rate-limited |

**Recommended: Baileys (Node.js)**
- `onWhatsApp('+27821234567')` returns `{exists: true, jid: '27821234567@s.whatsapp.net'}`
- `profilePictureUrl(jid)` and contact name available after sync
- Run as a small Node.js service on bigtorig alongside the Python pipeline
- One authenticated WhatsApp session (scan QR once, session persists)

### Phase B: WhatsApp Qualification Outreach

After name lookup, send a templated WhatsApp message via Bigtorig Runtime's existing WhatsApp channel. Only create Notion leads for prospects who respond positively.

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
**Primary Systems Affected**: `scripts/gumtree_to_b2c.py` (add enrichment step), new Node.js service for WhatsApp
**Dependencies**: Baileys or whatsapp-web.js (Node.js), authenticated WhatsApp session on bigtorig

---

## IMPLEMENTATION PLAN

### Phase A: WhatsApp Name Lookup

**Goal:** Resolve phone numbers to real names before leads hit Notion. No messages sent.

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
- Rate limit: max 1 lookup per second (avoid WhatsApp ban)

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
# Scan QR code with WhatsApp on phone

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

## RISK ASSESSMENT

### WhatsApp Account Ban Risk

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Bulk name lookups trigger ban | Medium | Rate limit: 1 lookup/sec, max 20/session, random delays |
| Sending unsolicited messages triggers ban | Medium-High | Keep volume low (3-10/day), use conversational tone, no links |
| Phone number reported as spam | Low-Medium | Message is helpful/relevant (they posted about trackers), include opt-out |
| WhatsApp TOS violation | Medium | Using unofficial API — account could be suspended |

**Mitigation strategy:**
- Use a **dedicated WhatsApp number** for outreach (not Bigtorig Runtime's main number)
- Start with Phase A only (name lookup, no messaging) — lower ban risk
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
- [ ] WhatsApp lookup service runs on bigtorig
- [ ] `gumtree_to_b2c.py --whatsapp` resolves phone → name for valid WhatsApp numbers
- [ ] Leads in Notion show real names instead of "Unknown" (when WhatsApp name available)
- [ ] Rate limiting: max 1 lookup/second, max 30/session
- [ ] Graceful fallback: if service is down or number not on WhatsApp, name stays "Unknown"

### Phase B
- [ ] Qualification message sent to buyer-intent leads
- [ ] Responses tracked in SQLite outreach DB
- [ ] Only responded + interested leads POSTed to webhook
- [ ] 48-hour expiry for non-responses
- [ ] Dedicated WhatsApp number (not Bigtorig Runtime's main channel)
- [ ] Opt-out handling: "STOP" replies mark lead as not_interested

---

## DEPENDENCIES & PREREQUISITES

| Prerequisite | For Phase | Status |
|-------------|-----------|--------|
| Gumtree scraper working | A & B | ✅ Done |
| Gumtree → webhook bridge script | A & B | **Plan created — implement next** |
| Node.js on bigtorig | A & B | ✅ Available (n8n runs on Node) |
| Spare WhatsApp number + SIM | B | **Needed — discuss with Charles** |
| Baileys or whatsapp-web.js installed | A & B | Pending |

## NOTES

### Recommended implementation order

1. **Now:** Build `gumtree_to_b2c.py` (bridge script) — gets leads into Notion immediately
2. **Next:** Phase A (WhatsApp name lookup) — improves lead quality in Notion
3. **Then:** Phase B (WhatsApp qualification) — filters to only warm leads
4. **Future:** Integrate with Bigtorig Runtime's HEARTBEAT schedule for automated runs

### Alternative to Baileys: wa-automate / whatsapp-web.js

If Baileys proves unstable, `whatsapp-web.js` is a more mature alternative:
```bash
npm install whatsapp-web.js
```
Same API pattern: `client.getNumberId('+27821234567')` checks existence, `client.getContactById(jid)` gets name.

### Bigtorig Runtime integration

The Bigtorig Runtime agent already has a WhatsApp channel on `+27639842638`. For Phase B, it could potentially:
- Receive replies and route them to the qualification script
- Use its existing message handling to have a brief conversation before qualifying

However, mixing lead outreach with the runtime's operational channel risks confusion. A dedicated number is safer.

### Confidence Score: 7/10

Phase A (name lookup) is straightforward — 8/10 confidence.
Phase B (outreach + qualification) has more moving parts and WhatsApp ban risk — 6/10 confidence.
The main uncertainty is WhatsApp's tolerance for automated lookups from a datacenter IP.
