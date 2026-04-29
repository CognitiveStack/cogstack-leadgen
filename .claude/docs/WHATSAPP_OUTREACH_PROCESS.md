# WhatsApp Outreach Process — Claire's Leads

## Overview

A daily manual pipeline that sends personalised WhatsApp messages to curated leads from Claire's Excel spreadsheets, tracks responses in a dedicated Notion database, and submits warm leads (Yes / No-Reply after 7 days) to the Cartrack CRM.

---

## Infrastructure

| Component | Details |
|-----------|---------|
| **WhatsApp number** | Phone 3 — +27631650794 (WhatsApp Business) |
| **Baileys service** | bigtorig at `100.126.59.117:3456` (Tailscale) |
| **Notion database** | Claire-Prospects DB (`34189024-cd3d-8108-bd69-ce41ebfa2eb2`) |
| **Cartrack CRM** | `https://ctcrm.cartrack.co.za/jsonrpc/crm_hook.php` |
| **State file** | `logs/outreach-state.json` — tracks every sent lead |

---

## Lead Sources

| File | Format | Total | Sent | Remaining |
|------|--------|-------|------|-----------|
| `ClaireLeads/CarTrackSubmissions.xlsx` | Format A (16+ cols) | 118 | 73 | 0 |
| `ClaireLeads/CarTrackSubmission2.xlsx` | Format B (10 cols) | 21 | 20 | 1 (Stefan) |

**Format A columns used:** C=name, D=phone, E=email, F=interest, G=motivation, P=status (skip if `"sent"`)  
**Format B columns used:** A=business, B=name, C=phone, D=email, F=motivation, G=status (skip if `"sent"`)

---

## Daily Workflow (Manual)

Run these three commands each day, in order:

### Step 1 — Check Responses
```bash
uv run python scripts/whatsapp_responses.py
```
- Polls `/inbox` on Baileys, drains the message buffer
- Classifies each reply: **Yes / No / Maybe / Unclear**
- Updates Notion (Response Status, Response At, response text)
- Auto-submits **Yes** leads to the B2C webhook (Claire's call centre queue)
- Marks leads with no reply after **48h** as `no_reply` in Notion and state file
- Raw inbox saved to `logs/inbox-raw-YYYY-MM-DD.json` for crash recovery

### Step 2 — Send Next Batch
```bash
uv run python scripts/whatsapp_outreach.py --max 20
# Or target a specific file:
uv run python scripts/whatsapp_outreach.py --file ClaireLeads/CarTrackSubmission2.xlsx --max 5
```
- Reads Excel, skips already-sent phones (checked against `outreach-state.json`)
- Does a WhatsApp name lookup per lead (falls back to Excel name)
- Sends personalised message from Phone 3
- Creates a Notion Claire-Prospects record (Response Status = Pending)
- Appends entry to `logs/outreach-state.json`
- Rate limited: 3–5s jitter between sends; server adds 30–60s jitter per message
- **Daily send limit**: 40 messages/day (configured in Baileys `lookup.js`)

### Step 3 — Submit to Cartrack
```bash
uv run python scripts/cartrack_submit.py
# Dry-run preview first (recommended):
uv run python scripts/cartrack_submit.py --dry-run
# Yes responses only (skip no-reply):
uv run python scripts/cartrack_submit.py --yes-only
```
- Submits **Yes** leads immediately
- Submits **No-Reply** leads after **7 days** with no response
- Marks `cartrack_submitted: true` in state file — will not resubmit
- Phone format converted from `+27XXXXXXXXX` → `0XXXXXXXXX` for Cartrack

---

## Message Template

```
Hi {name}! 👋

Do you have vehicle tracking for your {expressed_interest}?

We offer competitive vehicle GPS tracking from *R99/month*, installation included.
Can we give you a free quote?

Reply *YES* to be called, *NO* if not interested, or *MAYBE* if you'd like more info first. 😊
```

If no expressed interest is available, the second line becomes:  
*"Do you have vehicle tracking for your business vehicles?"*

---

## Response Classification

| Classification | Keywords |
|---------------|---------|
| **Yes** | yes, ja, yep, yeah, ok, okay, sure, please, call me, interested, send quote, sounds good, let's go |
| **No** | no, nee, not interested, stop, don't, do not, remove, unsubscribe, leave me alone, not looking |
| **Maybe** | maybe, possibly, perhaps, not sure, depends, more info, tell me more, what is, how much, what does, send more, details please |
| **Unclear** | anything else — left as Pending for manual review |

---

## Notion — Claire-Prospects Schema

| Property | Type | Notes |
|----------|------|-------|
| Full Name | title | WhatsApp name if resolved, else Excel name |
| Phone | phone_number | +27 normalised |
| Email | email | From Excel |
| Business | rich_text | Expressed interest / business context |
| Motivation | rich_text | Why they want tracking |
| Outreach Message | rich_text | Exact message sent |
| Outreach Sent At | date | When message was sent |
| Response | rich_text | Verbatim reply text |
| Response Status | select | Pending / Yes / No / Maybe / No Reply |
| Response At | date | When they replied |
| Submitted to Pipeline | checkbox | True once POSTed to B2C webhook |
| Date Added | date | Record creation timestamp |

**Suggested Notion views:**
- **Active Outreach** — filter: Response Status = Pending, sort: Outreach Sent At ASC
- **Warm Leads** — filter: Response Status = Yes OR Maybe
- **All Prospects** — ungrouped full table

---

## Cartrack CRM Payload

```json
{
  "token": "611d6f1a-04a1-42eb-889f-c3ff8a29bf45",
  "method": "createLead",
  "external_system_uid": "B2C - 9PointPlanWA",
  "external_source_id": "10001",
  "instance_uid": "793c83c2-f829-464c-ad82-a157cf85bf34",
  "campaign_uid": "af7b2cbb-29a4-446b-b4fd-0199a060d9ad",
  "name": "<first name>",
  "phone": "0XXXXXXXXX",
  "email": "",
  "lead_in_date": "D-Month-YYYY HH:MM:SS",
  "remark_message": "<source + response context, max 500 chars>",
  "meta": {
    "additional_partner_field1": "Suburb",
    "additional_partner_field2": ""
  }
}
```

Same static token is used for both Yes and No-Reply submissions.

---

## Useful Debug Commands

```bash
# Preview without sending anything
uv run python scripts/whatsapp_outreach.py --dry-run --max 5
uv run python scripts/cartrack_submit.py --dry-run

# Check Baileys service health
curl -s http://100.126.59.117:3456/health | python3 -m json.tool

# Check raw inbox manually (drains buffer — use carefully)
curl -s http://100.126.59.117:3456/inbox | python3 -m json.tool

# View current state summary
python3 -c "
import json; from collections import Counter
state = json.loads(open('logs/outreach-state.json').read())
print(Counter(e['status'] for e in state))
print('Cartrack submitted:', sum(1 for e in state if e.get('cartrack_submitted')))
"

# View today's logs
tail -f logs/whatsapp-outreach-$(date +%Y-%m-%d).log
tail -f logs/whatsapp-responses-$(date +%Y-%m-%d).log
```

---

## Known Gotchas

- **Phone 3 must stay connected** to WiFi/data on bigtorig — Baileys runs as a background process; the physical handset does not need to be held but must remain powered and connected.
- **openpyxl reads phone numbers as integers** — `0827712303` becomes `827712303`. The scripts handle this with `str(int(raw)).zfill(10)`.
- **Inbox drain is destructive** — `GET /inbox` clears the buffer. Raw messages are saved to `logs/inbox-raw-YYYY-MM-DD.json` before processing for crash recovery.
- **Cartrack won't resubmit** — once `cartrack_submitted: true` is set in the state file, the lead is skipped on all future runs.
- **No-Reply 7-day vs 48h** — `whatsapp_responses.py` expires leads to `no_reply` after 48h (for Notion tracking). `cartrack_submit.py` only submits no-reply leads after 7 days (Cartrack's requirement).
