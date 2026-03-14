# Skill: cogstack-b2c-leadgen

**Version:** 1.1
**Phase:** 2 (HTTP + SearXNG)
**Agent:** Hugo (OpenClaw on Pi4)
**Pipeline:** B2C Webhook → Notion B2C Leads DB → Claire QA → B2C Call Centre

---

## 1. Overview & Trigger

**Purpose:** Find South African individuals with verifiable intent to buy personal vehicle tracking services. Enrich each lead and submit structured batches to the live B2C pipeline.

**Trigger conditions (run when either applies):**
- WhatsApp command: `"Hugo, B2C leads"` or `"Hugo, run B2C lead generation"`
- HEARTBEAT.md schedule: 2–3× per week (e.g. Mon/Wed/Fri)

**Phase 2 scope:** SearXNG-accessible sources only. No browser tool yet. Gumtree is Phase 3.

**Goal per run:** 3–10 quality leads. Quality over quantity — Claire reviews every lead, so a bad lead wastes her time.

---

## 2. Source Query Templates

Run each Phase 2 query against SearXNG. Skip Phase 3 sources until browser is unlocked.

**SearXNG API call:**
```
GET http://localhost:8080/search?q=<URL-encoded query>&format=json&language=en
```

| Source | SearXNG Query | Phase |
|--------|--------------|-------|
| Hellopeter | `site:hellopeter.com cartrack OR tracker OR "vehicle tracking" 1 star 2025 OR 2026` | 2 — ACTIVE |
| MyBroadband | `site:mybroadband.co.za "car tracker" OR "vehicle tracker" OR "GPS tracker" South Africa` | 2 — ACTIVE |
| Reddit r/southafrica | `site:reddit.com/r/southafrica tracker OR "vehicle tracking" OR "car theft"` | 2 — ACTIVE |
| OLX Wanted | `site:olx.co.za wanted tracker OR "GPS tracking"` | 2 — ACTIVE |
| Gumtree Wanted | `site:gumtree.co.za wanted "car tracker" OR "vehicle tracker" OR "GPS"` | 3 — SKIP (browser only) |
| Facebook Groups | `"car tracker" OR "vehicle tracker" site:facebook.com group` | 3 — SKIP (FB auth required) |

**Per source:** Take the top 5–10 results. Filter by qualification criteria before fetching full pages.

---

## 3. Lead Qualification Criteria

**A valid B2C lead MUST:**
- Be a South African individual (not a company or fleet operator)
- Explicitly mention wanting, needing, or comparing a tracker or GPS tracking system
- Have a resolvable `intent_source_url` (the actual post, review, or ad URL — not a search results page)
- Be reasonably recent (ideally < 30 days; older posts get lower urgency_score but are still submittable)
- Not already be in Notion — but **don't pre-check**, the webhook handles dedup automatically by URL

**A lead is NOT valid if:**
- It's a business, fleet company, or B2B entity → route to B2B pipeline instead
- It's general discussion with no purchasing intent (e.g., "what does GPS tracking do?")
- It's about OBD dongles, anti-theft alarms, or devices clearly unrelated to tracking subscriptions
- The URL is a category/listing page, not a specific post or review

**When uncertain:** err on the side of submitting. Claire will QA reject if needed, and that feedback improves the pipeline.

---

## 4. Scoring Instructions

```
B2C Composite Score = (Intent Strength × 0.6) + (Urgency Score × 0.4)
```

### Intent Strength (0–10) — how explicitly are they seeking tracking?

| Score | Signal |
|-------|--------|
| 9–10 | "I need a tracker NOW", "Looking to buy today", 1-star Hellopeter review actively seeking a Cartrack alternative, mentions getting quotes |
| 7–8 | "Comparing tracker options", "Unhappy with current tracker and switching", asking which provider to choose |
| 5–6 | "Thinking about getting a tracker", "Is it worth it?", evaluating options without urgency |
| 3–4 | "Anyone use trackers?", vague curiosity, no purchasing language |
| 1–2 | Tracker mentioned in passing in an unrelated post, no intent evident |

### Urgency Score (0–10) — how time-sensitive is their need?

| Score | Signal |
|-------|--------|
| 9–10 | Post < 3 days ago, mentions active theft / break-in attempt, says "urgent" or "ASAP" |
| 7–8 | Post < 2 weeks old, clearly motivated buyer, subscription just expired |
| 5–6 | Post 2–4 weeks old, general research phase |
| 3–4 | Post 1–3 months old |
| 1–2 | Post > 3 months old |

**Submission threshold:** Composite Score ≥ 6. Submit all leads that meet qualification criteria AND score ≥ 6. Do not submit below 5.

---

## 5. Subagent Enrichment Instructions

For each qualified candidate URL, spawn a **gpt-4o-mini** subagent via OpenRouter with the following prompt. The main Hugo session (DeepSeek) handles orchestration; gpt-4o-mini does the JSON extraction — cheapest capable model for structured output, routed through OpenRouter (no direct Anthropic dependency).

**Model:** `openrouter/openai/gpt-4o-mini`

**Subagent prompt template (paste verbatim, filling in the placeholders):**

```
You are enriching a B2C lead for a South African vehicle tracking company (Cartrack reseller).

Given this raw post/review:
URL: <intent_source_url>
Raw text: <page_content — paste the full fetched text here>

Extract and return ONLY valid JSON (no explanation, no markdown):
{
  "full_name": "<name if visible, else 'Unknown'>",
  "phone": "<phone number if visible, else null>",
  "email": "<email address if visible, else null>",
  "province": "<SA province if mentioned, else null>",
  "city": "<city or area if mentioned, else null>",
  "intent_signal": "<verbatim quote or close paraphrase showing they want tracking — max 500 chars>",
  "vehicle_make_model": "<vehicle make and model if mentioned, else null>",
  "vehicle_year": <year as integer if mentioned, else null>,
  "intent_strength": <integer 0-10>,
  "urgency_score": <integer 0-10>,
  "call_script_opener": "<personalized opening line for a B2C sales call, reference their specific situation — max 200 chars>",
  "data_confidence": "<High|Medium|Low>"
}

Data confidence rules:
- High: phone or email is visible AND intent is explicit
- Medium: intent is clear but no direct contact info found
- Low: indirect intent signal, old post, or ambiguous content

call_script_opener guidance: Reference the specific platform and their situation.
Examples:
- "Hi, I saw your Hellopeter review about Cartrack — are you still looking for a better tracking option?"
- "Hi, I came across your MyBroadband post about GPS trackers — I'd love to help you find the right fit."
```

**After receiving the JSON:** validate that all required fields are present before including in the batch. If `intent_source_url` is missing or `intent_signal` is empty, discard the lead.

---

## 6. Output Schema — POST Payload

Assemble all enriched leads into a single batch payload:

```json
{
  "batch_id": "B2C-BATCH-YYYY-MM-DD-HUGO-RUN-001",
  "segment": "B2C",
  "leads": [
    {
      "full_name": "Jane Dlamini",
      "phone": "+27821234567",
      "email": null,
      "province": "Gauteng",
      "city": "Sandton",
      "intent_signal": "My Cartrack subscription is up and they want to charge me R400/month. Looking for a better option urgently.",
      "intent_source": "Hellopeter",
      "intent_source_url": "https://www.hellopeter.com/cartrack/reviews/12345",
      "intent_date": "2026-03-12",
      "vehicle_make_model": "Toyota Hilux",
      "vehicle_year": 2021,
      "call_script_opener": "Hi Jane, I saw your Hellopeter review about Cartrack pricing — are you still looking for a better tracking option?",
      "sources_used": "Hellopeter public review",
      "data_confidence": "Medium",
      "intent_strength": 9,
      "urgency_score": 8
    }
  ]
}
```

**Field requirements:**
- `batch_id`: format `B2C-BATCH-YYYY-MM-DD-HUGO-RUN-NNN` where NNN increments per run per day
- `segment`: always `"B2C"` (required — webhook rejects wrong segment)
- `intent_source`: must be one of `Hellopeter`, `Gumtree`, `MyBroadband`, `Facebook`, `OLX`, `Reddit`
- `intent_source_url`: required, must be a specific post/review URL (not a listing page)
- `intent_date`: ISO date string `YYYY-MM-DD` of the original post (estimate if not shown)
- `phone` / `email`: null if not found (do not guess or fabricate)
- `intent_strength` / `urgency_score`: integers 0–10

---

## 7. Webhook POST

```
POST https://n8n.bigtorig.com/webhook/b2c-lead-ingestion
Authorization: Bearer <B2C_WEBHOOK_TOKEN>
Content-Type: application/json
Body: <JSON batch payload>
```

**Environment variables required on Pi4:**
```bash
B2C_WEBHOOK_URL=https://n8n.bigtorig.com/webhook/b2c-lead-ingestion
B2C_WEBHOOK_TOKEN=<from cogstack-leadgen .env — same bearer token as B2B>
```

**Expected success response:**
```json
{
  "status": "success",
  "batch_id": "B2C-BATCH-...",
  "leads_created": 3,
  "duplicates_skipped": 1,
  "errors": []
}
```

If `status` is not `"success"`, log the full response and report to Charles.

---

## 8. Dedup Awareness

- **Dedup key:** `intent_source_url` — the webhook automatically skips any URL already in Notion
- **Do not pre-check Notion** — just submit; the webhook returns `duplicates_skipped` count
- **Same person + different URL = fresh lead** — re-qualification is intentional; submit it
- **Log `duplicates_skipped`** from the response — high counts indicate a source is exhausted; rotate to other queries

---

## 9. Full Run Procedure

Execute these steps in order:

```
1. SEARCH
   For each Phase 2 source query:
   - GET http://localhost:8080/search?q=<url-encoded-query>&format=json&language=en
   - Extract result URLs and titles
   - Skip results that are clearly not individual posts/reviews (category pages, homepages)

2. FILTER
   Review each result title + snippet:
   - Discard if it's a business/company post
   - Discard if there's no purchasing intent signal visible
   - Keep candidates that look like individual consumers seeking tracking

3. FETCH
   For each candidate URL:
   - GET the page (HTTP fetch)
   - Extract the main post/review text (skip nav, footer, ads)
   - If the page requires login or returns 403, skip it and note the URL

4. ENRICH
   For each fetched candidate:
   - Spawn gpt-4o-mini subagent via OpenRouter (openrouter/openai/gpt-4o-mini) with the enrichment prompt (Section 5)
   - Receive structured JSON back
   - Apply scoring threshold: discard if Composite Score < 5
   - Validate required fields are present

5. BATCH
   Collect all valid enriched leads into one batch payload (Section 6)
   - Target: 3–10 leads per run
   - If < 3 valid leads found, still submit what you have (don't pad with low-quality leads)
   - Generate batch_id: B2C-BATCH-<today's date>-HUGO-RUN-<NNN>

6. POST
   POST batch to webhook (Section 7)
   Log the full response

7. REPORT
   WhatsApp Charles:
   "B2C run done: <leads_created> leads created, <duplicates_skipped> duplicates skipped.
   Sources searched: Hellopeter, MyBroadband, Reddit, OLX.
   Batch ID: <batch_id>"

   If any errors in response:
   "B2C run completed with errors: <error details>"
```

---

## 10. Phase 3 Preview (Browser Required — Not Yet Active)

When the browser tool is unlocked, add these sources:

| Source | Why it's high value |
|--------|-------------------|
| Gumtree Wanted ads | Phone numbers visible on listing pages — highest conversion rate |
| Facebook Groups | Real-time posts from consumers — can catch urgent buyers same day |

Expected uplift: 2–5 phone-verified leads per run. Revisit this section when Hugo graduates to Phase 3.

---

## Quick Reference

| Item | Value |
|------|-------|
| Webhook URL | `https://n8n.bigtorig.com/webhook/b2c-lead-ingestion` |
| SearXNG | `http://localhost:8080/search?q=<query>&format=json&language=en` |
| Enrichment model | `openrouter/openai/gpt-4o-mini` (subagent) |
| Orchestration model | DeepSeek v3 (main Hugo session) |
| Dedup key | `intent_source_url` |
| Scoring threshold | Composite Score ≥ 6 |
| Segment value | `"B2C"` (exact, required) |
| QA entry state | Pending QA (set by webhook) |
