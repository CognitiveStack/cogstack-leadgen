# Feature: Gumtree → B2C Webhook Bridge Script

## Feature Description

A Python script (`scripts/gumtree_to_b2c.py`) that reads raw Gumtree scraper output, filters out sellers/irrelevant ads, enriches genuine buyer-intent leads via LLM, and POSTs them as a B2C batch to the n8n webhook — populating the Notion B2C Leads DB with phone-verified leads.

## Problem Statement

The Gumtree scraper (`gumtree_scrapling.py`) successfully extracts ads with phone numbers, but:
1. **Most results are SELLERS** — people offering trackers for sale, not people wanting to buy
2. **Many are irrelevant** — job listings, truck sales, pet trackers, OBD accessories
3. **No automation path exists** to get the valid buyer-intent ads from JSON file → Notion B2C database
4. **No enrichment step** — raw ads lack `full_name`, `intent_strength`, `urgency_score`, `call_script_opener`

The March 17 scrape (15 ads) contained 0 genuine buyer-intent leads — all were sellers or unrelated.

## Solution Statement

Build a bridge script that:
1. Reads `memory/gumtree-leads-YYYY-MM-DD.json`
2. **Pre-filters** obvious non-leads via keyword rules (seller signals, job ads)
3. **LLM-classifies** remaining ads: buyer vs seller, using gpt-4o-mini via OpenRouter
4. **Enriches** genuine buyer leads: infer name from description, score intent/urgency, generate call script
5. **Assembles** a B2C webhook payload and POSTs to `https://n8n.bigtorig.com/webhook/b2c-lead-ingestion`
6. **Reports** results: leads created, duplicates, rejections with reasons

## Feature Metadata

**Feature Type**: New Capability (pipeline glue)
**Estimated Complexity**: Low-Medium
**Primary Systems Affected**: `scripts/gumtree_to_b2c.py` (new)
**Dependencies**: `httpx`, `python-dotenv` (already installed). OpenRouter API key in `.env` for LLM enrichment.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ BEFORE IMPLEMENTING

- `memory/gumtree-leads-YYYY-MM-DD.json` — Input format: `[{title, description, phone, location, price, adid, url, scraped_at}]`
- `test_b2c_webhook.py` — Output payload format: `{batch_id, segment: "B2C", leads: [{full_name, phone, email, province, city, intent_signal, intent_source, intent_source_url, intent_date, ...}]}`
- `n8n_b2c_code_node.js` — Webhook expects: `segment: "B2C"`, dedup on `intent_source_url`, Notion property mappings
- `skills/cogstack-b2c-leadgen/SKILL.md` — Scoring rubric (Section 4), enrichment prompt template (Section 5)
- `scripts/gumtree_scrapling.py` — Upstream scraper; `_BLOCKED_CATEGORIES` for reference on what's already filtered

### Patterns to Follow

- CLI pattern from `gumtree_scrapling.py`: `argparse`, `--out`, `--max`, `[gumtree]` prefix logging
- Webhook POST pattern from `test_b2c_webhook.py`: httpx, Bearer auth, response handling
- Batch ID format: `B2C-BATCH-YYYY-MM-DD-GUMTREE-NNN`

---

## STEP-BY-STEP TASKS

### Task 1: CREATE `scripts/gumtree_to_b2c.py`

**Structure:**

```
1. CLI args: --input (default: today's gumtree-leads file), --dry-run (print but don't POST)
2. Read JSON input file
3. Pre-filter: keyword-based rejection of obvious non-leads
4. LLM classification + enrichment: for each surviving ad, call OpenRouter
5. Score filtering: reject composite score < 5
6. Assemble B2C batch payload
7. POST to webhook (unless --dry-run)
8. Print report
```

**Pre-filter rules (no LLM needed — fast rejection):**

```python
SELLER_SIGNALS = [
    "for sale", "selling", "we are selling", "price:", "only r",
    "includes sim", "no subscription", "subscription-free",
    "order now", "shop now", "visit our", "our range",
    "in stock", "available now", "special offer",
]

IRRELEVANT_SIGNALS = [
    "job", "hiring", "vacancy", "looking for a driver",
    "debt collector", "admin assistant", "coordinator",
    "field tracer", "recruitment",
    "pet tracker", "dog tracker", "cat tracker",
    "key cutting", "locksmith",
    "smart health ring", "wearable",
]
```

An ad is pre-rejected if:
- `title` or `description` (lowercased) contains any SELLER_SIGNAL
- `title` or `description` (lowercased) contains any IRRELEVANT_SIGNAL
- Phone number starts with `+971` or other non-SA prefix (not `+27`)
- URL contains any of the already-blocked categories (double-check)

**LLM enrichment prompt (OpenRouter, gpt-4o-mini):**

```
You are classifying a Gumtree ad to determine if the poster is a BUYER seeking a vehicle tracker, or a SELLER/irrelevant ad.

Ad title: {title}
Ad description: {description}
Ad location: {location}
Ad URL: {url}

Respond with ONLY valid JSON:
{{
  "classification": "BUYER" or "SELLER" or "IRRELEVANT",
  "reason": "<one sentence explaining why>",
  "full_name": "<name if visible in ad text, else 'Unknown'>",
  "intent_signal": "<if BUYER: verbatim quote showing they WANT a tracker, max 300 chars. if not BUYER: null>",
  "intent_strength": <integer 0-10, 0 if not a buyer>,
  "urgency_score": <integer 0-10, 0 if not a buyer>,
  "call_script_opener": "<if BUYER: personalized opener referencing their ad, max 200 chars. if not BUYER: null>",
  "province": "<SA province if determinable from location, else null>"
}}

Classification rules:
- BUYER: person explicitly says they WANT/NEED/are LOOKING FOR a vehicle tracker
- SELLER: person is OFFERING/SELLING a tracker or tracker-related product
- IRRELEVANT: job listing, pet tracker, unrelated product, vehicle for sale
```

**Location → Province mapping (for ads where LLM can't determine):**

```python
LOCATION_TO_PROVINCE = {
    "johannesburg": "Gauteng", "joburg": "Gauteng", "sandton": "Gauteng",
    "pretoria": "Gauteng", "tshwane": "Gauteng", "centurion": "Gauteng",
    "midrand": "Gauteng", "randburg": "Gauteng", "east rand": "Gauteng",
    "edenvale": "Gauteng", "brakpan": "Gauteng", "benoni": "Gauteng",
    "cape town": "Western Cape", "stellenbosch": "Western Cape",
    "durban": "KwaZulu-Natal", "umhlanga": "KwaZulu-Natal",
    "pietermaritzburg": "KwaZulu-Natal",
    "port elizabeth": "Eastern Cape", "gqeberha": "Eastern Cape",
    "bloemfontein": "Free State",
    "polokwane": "Limpopo",
    "nelspruit": "Mpumalanga", "mbombela": "Mpumalanga",
    "kimberley": "Northern Cape",
    "rustenburg": "North West",
}
```

**OpenRouter API call pattern:**

```python
import httpx

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

def llm_classify(ad: dict) -> dict | None:
    """Classify and enrich a Gumtree ad via gpt-4o-mini."""
    prompt = f"""..."""  # template above

    response = httpx.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "openai/gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 500,
        },
        timeout=30.0,
    )
    # Parse JSON from response.json()["choices"][0]["message"]["content"]
```

**Output assembly — map Gumtree ad + LLM enrichment → B2C lead:**

```python
def gumtree_ad_to_lead(ad: dict, enrichment: dict) -> dict:
    return {
        "full_name": enrichment.get("full_name", "Unknown"),
        "phone": ad["phone"],  # already normalised by scraper
        "email": None,  # Gumtree ads rarely have email
        "province": enrichment.get("province") or infer_province(ad["location"]),
        "city": ad["location"],
        "intent_signal": enrichment.get("intent_signal", ad.get("description", "")[:300]),
        "intent_source": "Gumtree",
        "intent_source_url": ad["url"],
        "intent_date": ad["scraped_at"][:10],  # date portion of ISO timestamp
        "vehicle_make_model": None,  # rarely in Gumtree wanted ads
        "vehicle_year": None,
        "call_script_opener": enrichment.get("call_script_opener", ""),
        "data_confidence": "High" if ad["phone"] else "Medium",
        "sources_used": "Gumtree SA public listing",
        "intent_strength": enrichment.get("intent_strength", 5),
        "urgency_score": enrichment.get("urgency_score", 5),
    }
```

**CLI interface:**

```
uv run python scripts/gumtree_to_b2c.py
uv run python scripts/gumtree_to_b2c.py --input memory/gumtree-leads-2026-03-17.json
uv run python scripts/gumtree_to_b2c.py --dry-run  # classify + enrich but don't POST
uv run python scripts/gumtree_to_b2c.py --skip-llm  # pre-filter only, no OpenRouter calls
```

**GOTCHAS:**
1. `OPENROUTER_API_KEY` must be in `.env` — script should exit with clear message if missing
2. OpenRouter rate limits: add 200ms delay between LLM calls
3. Pre-filter should run BEFORE LLM to minimise API costs (gpt-4o-mini is ~$0.15/M input tokens, but still)
4. The `phone` field from gumtree_scrapling.py is already normalised to `+27...` format
5. `intent_source_url` is the dedup key in the webhook — each Gumtree ad URL is unique
6. Some ads may have HTML entities in description (`&#39;`, `&#43;`) — decode before LLM prompt
7. The `scraped_at` field is ISO8601 with timezone — extract just the date for `intent_date`
8. If 0 buyer-intent leads survive filtering, still print a report but don't POST an empty batch

### Task 2: ADD `OPENROUTER_API_KEY` to `.env` documentation

Update `CLAUDE.md` Environment section to note:
```
OPENROUTER_API_KEY — OpenRouter API key for LLM enrichment (gpt-4o-mini)
```

### Task 3: VALIDATE

```bash
# Syntax check
python3 -m py_compile scripts/gumtree_to_b2c.py

# Dry run against existing data (no webhook POST)
uv run python scripts/gumtree_to_b2c.py --input memory/gumtree-leads-2026-03-17.json --dry-run

# Expected: all 15 ads classified as SELLER or IRRELEVANT (March 17 data has no buyers)
# This validates the pre-filter and LLM classification are working

# Full run (after a fresh scrape with improved blocklist):
uv run python scripts/gumtree_scrapling.py --max 20
uv run python scripts/gumtree_to_b2c.py
# Expected: some buyer leads POST'd to webhook, visible in Notion B2C Leads DB
```

---

## ACCEPTANCE CRITERIA

- [ ] `scripts/gumtree_to_b2c.py` exists and passes syntax check
- [ ] Pre-filter correctly rejects seller/irrelevant ads before LLM
- [ ] LLM classifies buyer vs seller via OpenRouter (gpt-4o-mini)
- [ ] Only BUYER-classified ads with composite score >= 5 are included in batch
- [ ] Output payload matches B2C webhook schema exactly
- [ ] `--dry-run` mode prints classification results without POSTing
- [ ] `--skip-llm` mode applies only pre-filter rules
- [ ] Report shows: total ads, pre-filtered, LLM-rejected, qualified, posted
- [ ] March 17 data (all sellers) results in 0 leads posted (correct behaviour)
- [ ] Deployed to bigtorig and runs end-to-end after a fresh Gumtree scrape

---

## NOTES

### Pipeline flow after this feature

```
gumtree_scrapling.py → memory/gumtree-leads-YYYY-MM-DD.json
                              ↓
gumtree_to_b2c.py    → pre-filter → LLM classify → enrich → POST
                              ↓
n8n B2C webhook      → dedup → Notion B2C Leads DB
                              ↓
Claire QA            → Approve/Reject → Call Centre
```

### Cost estimate

- gpt-4o-mini via OpenRouter: ~$0.15/M input tokens, ~$0.60/M output tokens
- Average ad description: ~200 tokens input, ~100 tokens output
- 20 ads per run: ~4K input + 2K output = ~$0.002 per run
- Negligible cost — no need for batching or caching

### Future: combine with WhatsApp enrichment

After the WhatsApp name lookup feature is built, the pipeline becomes:
```
gumtree_scrapling.py → gumtree_to_b2c.py → [WhatsApp name lookup] → POST
```
The bridge script should be designed so WhatsApp enrichment can be inserted as an optional step.

### Confidence Score: 9/10

High confidence — this is straightforward glue code connecting two working systems. The only risk is LLM classification accuracy, mitigated by the `--dry-run` mode for tuning the prompt.
