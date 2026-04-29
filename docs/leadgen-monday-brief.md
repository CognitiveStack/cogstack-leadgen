# Claude Code Brief: B2C Lead Generation — Monday Deadline

## Context

We need individual private car owner leads by Monday. **B2C only.**

The pipeline is already built (`scrape → classify → submit`). We need to expand the **sources and queries** in:
- `leadgen-search` skill — Exa/Tavily semantic search
- `leadgen-scraper` skill — Firecrawl scraping

Focus: South Africa only.

**Proven signal:** HelloPeter unhappy competitor customers — reviews mentioning Cartrack, Tracker, MiX Telematics, Netstar, Beame. Extract name/details from complaint, enrich with Exa to find phone number.

---

## Source Priority List

### Tier 1 — High Intent (do these first)

| # | Source | Approach |
|---|--------|----------|
| 1 | **HelloPeter.com** | Complaints about Cartrack, Tracker, MiX Telematics, Netstar, Beame |
| 2 | **Gumtree** — new car purchases | People who just bought expensive cars (SUV, bakkie, luxury) → they need a tracker |
| 3 | **Facebook Marketplace SA** | New car purchases via Firecrawl |
| 4 | **OLX South Africa** | Luxury/fleet vehicle purchases |

Gumtree query pattern:
```
"just bought" OR "new car" AND (SUV OR bakkie OR "Land Cruiser" OR "Fortuner" OR "Ranger")
```

---

### Tier 2 — Competitor Churn

| # | Source | Query |
|---|--------|-------|
| 5 | HelloPeter | Cartrack cancellation complaints |
| 6 | HelloPeter | Tracker poor service reviews |
| 7 | HelloPeter | MiX Telematics complaints |
| 8 | HelloPeter | Netstar complaints |
| 9 | Twitter/X | `@Cartrack_SA frustrated` OR `cancel Cartrack` |
| 10 | MyBroadband forums | Tracker cancellation threads (NOT reviews/comparisons) |

---

### Tier 3 — Life Events (new car = needs tracker)

| # | Source | Signal |
|---|--------|--------|
| 11 | Gumtree sold listings | "Sold" expensive vehicles → buyer now needs tracker |
| 12 | AutoTrader SA | Recently listed/sold SUVs and bakkies |
| 13 | Cars.co.za | New purchase signals |
| 14 | Facebook groups SA | "just bought a Fortuner" type posts via Exa |
| 15 | MyBroadband | "just bought" + car model posts |

---

### Tier 4 — Semantic Exa Searches

```
"just bought car need tracker South Africa"
"car stolen no tracker South Africa"
"which car tracker South Africa recommend"
"Cartrack too expensive alternative South Africa"
"cancel Cartrack looking for alternative"
"vehicle stolen Johannesburg no tracking"
"bakkie stolen Cape Town"
"need tracker installed Gauteng"
"car insurance requires tracker South Africa"
"tracker installation johannesburg price"
```

> Note: `car insurance requires tracker` is a forced buyer signal — very high intent.

---

### Tier 5 — Community & Forums

| # | Source | Notes |
|---|--------|-------|
| 26 | Brabys.com | Skip — B2B directory, not useful for B2C |
| 27 | Reddit r/southafrica | Car theft, tracker recommendations |
| 28 | Arrive Alive forums | Vehicle security discussions |
| 29 | MotorTalk SA forums | |
| 30 | CarMag.co.za | Comments and forums |

---

## HelloPeter Enrichment Pipeline (priority build)

For each HelloPeter complaint, run this enrichment chain:

```python
# Step 1 — Scrape
# Extract: reviewer_name, complaint_text, competitor_name, date

# Step 2 — Parse complaint
# From complaint_text extract: car_model, location, specific_pain_point

# Step 3 — Enrich via Exa
# Search: "{reviewer_name} {location} South Africa contact"
# If business mentioned: "{business_name} phone number {location}"

# Step 4 — Output lead record
{
  "name": reviewer_name,
  "phone": enriched_phone,        # from Exa
  "pain_point": complaint_summary, # becomes call centre opening line
  "competitor": "Cartrack",
  "car_model": extracted_model,
  "location": extracted_location,
  "source": "hellopeter",
  "urgency": "high"
}
```

The `pain_point` field becomes the **sales script hook** for the call centre agent.

---

## Classifier Updates (`classify.py`)

Update scoring weights:

| Signal | Score Adjustment |
|--------|-----------------|
| `car_stolen` mentioned | +2 (fear signal, urgent) |
| `insurance requires tracker` | +2 (forced buyer) |
| `just bought` + luxury model | +1 |
| `cancel` + competitor name | +2 (churn signal) |
| Forum/review post, not individual | -3 (filter out) |

---

## New Notion Output Fields

Add these fields to the lead record POSTed to n8n:

| Field | Description |
|-------|-------------|
| `lead_source` | HelloPeter / Gumtree / Exa / AutoTrader / etc. |
| `pain_point` | Extracted from complaint or post text |
| `car_model` | If detectable from content |
| `competitor` | If switching from Cartrack / Tracker / Netstar / etc. |
| `urgency` | `high` / `medium` / `low` based on classifier score |

---

## Immediate First Task

> Start with **HelloPeter → Cartrack complaints** via Firecrawl.
> That is the proven source with the strongest signal.
> Target: **10 real leads into Notion** by end of session.
> Then iterate through Tier 1, Tier 2, Tier 3 in order.
