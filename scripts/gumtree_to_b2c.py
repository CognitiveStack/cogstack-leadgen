#!/usr/bin/env python3
# =============================================================
# gumtree_to_b2c.py — Gumtree → B2C Webhook Bridge
# Reads raw Gumtree scraper output, filters sellers/irrelevant
# ads, enriches buyer-intent leads via LLM, and POSTs them as
# a B2C batch to the n8n webhook.
# =============================================================
# Usage:
#   uv run python scripts/gumtree_to_b2c.py
#   uv run python scripts/gumtree_to_b2c.py --input memory/gumtree-leads-2026-03-17.json
#   uv run python scripts/gumtree_to_b2c.py --dry-run
#   uv run python scripts/gumtree_to_b2c.py --skip-llm
#   uv run python scripts/gumtree_to_b2c.py --whatsapp          # enrich names via WhatsApp lookup service
#   uv run python scripts/gumtree_to_b2c.py --whatsapp --whatsapp-url http://127.0.0.1:3457
# =============================================================

import argparse
import html
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

# ── Logging ──────────────────────────────────────────────────

log = logging.getLogger("bridge")


def setup_logging() -> None:
    """Configure console + file logging."""
    log.setLevel(logging.DEBUG)

    # Console: INFO level
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("[%(name)s] %(levelname)s: %(message)s"))
    log.addHandler(console)

    # File: DEBUG level — logs/b2c-bridge-YYYY-MM-DD.log
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    fh = logging.FileHandler(log_dir / f"b2c-bridge-{today}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    log.addHandler(fh)


# ── Environment ──────────────────────────────────────────────

B2C_WEBHOOK_URL = os.environ.get("B2C_WEBHOOK_URL")
B2C_WEBHOOK_TOKEN = os.environ.get("B2C_WEBHOOK_TOKEN") or os.environ.get("WEBHOOK_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
WHATSAPP_LOOKUP_URL = os.environ.get("WHATSAPP_LOOKUP_URL", "http://127.0.0.1:3456")

# ── Retry constants ──────────────────────────────────────────

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 15]  # seconds — exponential backoff

# ── Pre-filter keyword lists ─────────────────────────────────

SELLER_SIGNALS = [
    "for sale", "selling", "we are selling", "price:", "only r",
    "includes sim", "no subscription", "subscription-free",
    "order now", "shop now", "visit our", "our range",
    "in stock", "available now", "special offer",
    "we deliver", "nationwide delivery", "free delivery",
    "wholesale", "bulk discount", "unit price",
    "(pty) ltd", "pty ltd",
]

IRRELEVANT_SIGNALS = [
    "job", "hiring", "vacancy", "looking for a driver",
    "debt collector", "admin assistant", "coordinator",
    "field tracer", "recruitment", "onboarding",
    "pet tracker", "dog tracker", "cat tracker",
    "key cutting", "locksmith",
    "smart health ring", "wearable",
    "obd splitter", "y-splitter", "extension cable",
    "head guide", "lodge", "safari",
    "brand engagement", "social media marketing",
]

# URL path segments that indicate non-buyer ads (mirrors gumtree_scrapling.py blocklist)
BLOCKED_URL_SEGMENTS = [
    "/a-cars-bakkies/", "/a-heavy-trucks-buses/",
    "/a-other-replacement-car-part/", "/a-car-interior-accessories/",
    "/a-accessories-styling/", "/a-auto-electrical-parts/",
    "/a-electronics-it-services/", "/a-wearable-technology/",
    "/a-other-pets/", "/a-removals-storage/",
    "/a-property-", "/a-other-services/", "/a-legal-services/",
    "/a-other-business", "/a-business+to+business",
    "/a-recruitment-services/", "/a-other-jobs/",
]

# ── Location → Province mapping ──────────────────────────────

LOCATION_TO_PROVINCE: dict[str, str] = {
    "johannesburg": "Gauteng", "joburg": "Gauteng", "sandton": "Gauteng",
    "pretoria": "Gauteng", "tshwane": "Gauteng", "centurion": "Gauteng",
    "midrand": "Gauteng", "randburg": "Gauteng", "east rand": "Gauteng",
    "edenvale": "Gauteng", "brakpan": "Gauteng", "benoni": "Gauteng",
    "boksburg": "Gauteng", "germiston": "Gauteng", "kempton park": "Gauteng",
    "roodepoort": "Gauteng", "soweto": "Gauteng", "alberton": "Gauteng",
    "fourways": "Gauteng", "bryanston": "Gauteng",
    "cape town": "Western Cape", "stellenbosch": "Western Cape",
    "paarl": "Western Cape", "durbanville": "Western Cape",
    "northern suburbs": "Western Cape", "century city": "Western Cape",
    "durban": "KwaZulu-Natal", "umhlanga": "KwaZulu-Natal",
    "pietermaritzburg": "KwaZulu-Natal", "durban city": "KwaZulu-Natal",
    "midlands": "KwaZulu-Natal",
    "port elizabeth": "Eastern Cape", "gqeberha": "Eastern Cape",
    "east london": "Eastern Cape",
    "bloemfontein": "Free State",
    "polokwane": "Limpopo",
    "nelspruit": "Mpumalanga", "mbombela": "Mpumalanga",
    "kimberley": "Northern Cape",
    "rustenburg": "North West", "mahikeng": "North West",
}


def infer_province(location: str | None) -> str | None:
    """Try to map a Gumtree location string to a SA province."""
    if not location:
        return None
    loc_lower = location.lower()
    for key, province in LOCATION_TO_PROVINCE.items():
        if key in loc_lower:
            return province
    return None


# ── WhatsApp name lookup ─────────────────────────────────────

def whatsapp_lookup(phone: str, lookup_url: str | None = None) -> str | None:
    """Look up WhatsApp profile name for a phone number.

    Requires the lookup service at /opt/projects/whatsapp-lookup to be running.
    Returns the profile name or None if not found / service unavailable.
    Retries once on timeout (Baileys can be slow after idle).
    """
    base_url = lookup_url or WHATSAPP_LOOKUP_URL
    for attempt in range(2):  # 1 retry on timeout
        try:
            resp = httpx.post(
                f"{base_url}/lookup",
                json={"phone": phone},
                timeout=15.0,
            )
            data = resp.json()
            if data.get("exists") and data.get("name"):
                return data["name"]
            log.debug("WhatsApp lookup for %s: exists=%s, name=%s", phone, data.get("exists"), data.get("name"))
            return None  # exists but no name, or not on WhatsApp — don't retry
        except httpx.TimeoutException:
            if attempt == 0:
                log.debug("WhatsApp lookup timeout for %s, retrying in 3s...", phone)
                time.sleep(3)
                continue
            log.warning("WhatsApp lookup timeout for %s after retry", phone)
        except httpx.HTTPError as e:
            log.warning("WhatsApp lookup HTTP error for %s: %s", phone, e)
            break
    return None


# ── Pre-filter ───────────────────────────────────────────────

def pre_filter(ad: dict) -> str | None:
    """
    Return a rejection reason if the ad should be skipped, or None if it passes.
    Runs before LLM to save API costs.
    """
    title = (ad.get("title") or "").lower()
    desc = html.unescape(ad.get("description") or "").lower()
    text = f"{title} {desc}"

    # Non-SA phone number
    phone = ad.get("phone") or ""
    if phone and not phone.startswith("+27"):
        return f"non-SA phone: {phone}"

    # URL in blocked category
    url = ad.get("url") or ""
    for seg in BLOCKED_URL_SEGMENTS:
        if seg in url:
            return f"blocked URL category: {seg}"

    # Job listing URL pattern
    if "-jobs/" in url:
        return "job listing URL"

    # Seller signals
    for signal in SELLER_SIGNALS:
        if signal in text:
            return f"seller signal: '{signal}'"

    # Irrelevant signals
    for signal in IRRELEVANT_SIGNALS:
        if signal in text:
            return f"irrelevant signal: '{signal}'"

    return None


# ── LLM classification + enrichment ─────────────────────────

LLM_PROMPT_TEMPLATE = """You are classifying a Gumtree ad to determine if the poster is a BUYER seeking a vehicle tracker, or a SELLER/irrelevant ad.

Ad title: {title}
Ad description: {description}
Ad location: {location}
Ad URL: {url}

Respond with ONLY valid JSON (no markdown, no explanation):
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
- BUYER: person explicitly says they WANT/NEED/are LOOKING FOR a vehicle tracker or tracking service
- SELLER: person is OFFERING/SELLING a tracker, tracker product, or related accessory
- IRRELEVANT: job listing, pet tracker, unrelated product, vehicle for sale, service ad"""


def llm_classify(ad: dict) -> dict | None:
    """Classify and enrich a Gumtree ad via gpt-4o-mini on OpenRouter.

    Retries on 429 (rate limit with Retry-After) and 5xx errors.
    """
    if not OPENROUTER_API_KEY:
        return None

    # Decode HTML entities in description
    desc = html.unescape(ad.get("description") or "")
    # Truncate long descriptions to save tokens
    if len(desc) > 1500:
        desc = desc[:1500] + "..."

    prompt = LLM_PROMPT_TEMPLATE.format(
        title=ad.get("title") or "",
        description=desc,
        location=ad.get("location") or "Unknown",
        url=ad.get("url") or "",
    )

    for attempt in range(MAX_RETRIES):
        try:
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

            if response.status_code == 429:
                # Rate limited — respect Retry-After header
                retry_after = int(response.headers.get("Retry-After", RETRY_DELAYS[attempt]))
                log.warning("LLM rate limited (429), retrying in %ds (attempt %d/%d)", retry_after, attempt + 1, MAX_RETRIES)
                time.sleep(retry_after)
                continue

            if response.status_code >= 500:
                # Server error — retry with backoff
                delay = RETRY_DELAYS[attempt]
                log.warning("LLM server error %d, retrying in %ds (attempt %d/%d)", response.status_code, delay, attempt + 1, MAX_RETRIES)
                time.sleep(delay)
                continue

            if response.status_code != 200:
                log.error("LLM API error: %d %s", response.status_code, response.text[:200])
                return None

            content = response.json()["choices"][0]["message"]["content"]
            # Strip markdown code fences if present
            content = content.strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)

            return json.loads(content)

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            log.error("LLM response parse error: %s", e)
            return None
        except httpx.HTTPError as e:
            delay = RETRY_DELAYS[attempt]
            log.warning("LLM request failed: %s, retrying in %ds (attempt %d/%d)", e, delay, attempt + 1, MAX_RETRIES)
            time.sleep(delay)

    log.error("LLM classify failed after %d retries", MAX_RETRIES)
    return None


# ── Lead assembly ────────────────────────────────────────────

def gumtree_ad_to_lead(ad: dict, enrichment: dict) -> dict:
    """Map a Gumtree ad + LLM enrichment to a B2C webhook lead."""
    return {
        "full_name": enrichment.get("full_name") or "Unknown",
        "phone": ad.get("phone"),
        "email": None,
        "province": enrichment.get("province") or infer_province(ad.get("location")),
        "city": ad.get("location"),
        "intent_signal": enrichment.get("intent_signal") or html.unescape(ad.get("description") or "")[:300],
        "intent_source": "Gumtree",
        "intent_source_url": ad["url"],
        "intent_date": (ad.get("scraped_at") or "")[:10],
        "vehicle_make_model": None,
        "vehicle_year": None,
        "call_script_opener": enrichment.get("call_script_opener") or "",
        "data_confidence": "High" if ad.get("phone") else "Medium",
        "sources_used": "Gumtree SA public listing",
        "intent_strength": enrichment.get("intent_strength", 5),
        "urgency_score": enrichment.get("urgency_score", 5),
    }


# ── Webhook POST ─────────────────────────────────────────────

def post_to_webhook(leads: list[dict], batch_id: str) -> dict | None:
    """POST the B2C batch to the n8n webhook. Returns response JSON or None.

    Retries on 5xx and timeout errors with exponential backoff.
    4xx errors fail immediately (client error — don't retry).
    """
    if not B2C_WEBHOOK_URL:
        log.error("B2C_WEBHOOK_URL not set in .env")
        return None
    if not B2C_WEBHOOK_TOKEN:
        log.error("B2C_WEBHOOK_TOKEN not set in .env")
        return None

    payload = {
        "batch_id": batch_id,
        "segment": "B2C",
        "leads": leads,
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = httpx.post(
                B2C_WEBHOOK_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {B2C_WEBHOOK_TOKEN}",
                },
                timeout=60.0,
            )
            log.info("Webhook response: %d", response.status_code)
            if response.status_code == 200:
                return response.json()
            if response.status_code >= 500:
                delay = RETRY_DELAYS[attempt]
                log.warning("Webhook server error %d, retrying in %ds (attempt %d/%d)", response.status_code, delay, attempt + 1, MAX_RETRIES)
                time.sleep(delay)
                continue
            # 4xx — client error, don't retry
            log.error("Webhook error %d: %s", response.status_code, response.text[:500])
            return None
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            delay = RETRY_DELAYS[attempt]
            log.warning("Webhook request failed: %s, retrying in %ds (attempt %d/%d)", e, delay, attempt + 1, MAX_RETRIES)
            time.sleep(delay)

    log.error("Webhook POST failed after %d retries", MAX_RETRIES)
    return None


# ── CLI + Main ───────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    today = datetime.now().strftime("%Y-%m-%d")
    default_input = str(
        Path(__file__).parent.parent / "memory" / f"gumtree-leads-{today}.json"
    )

    parser = argparse.ArgumentParser(
        description="Bridge: Gumtree scraper output → B2C webhook (filter + enrich + POST)"
    )
    parser.add_argument(
        "--input", type=str, default=default_input,
        help="Input JSON file from gumtree_scrapling.py (default: today's file)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Classify and enrich but don't POST to webhook"
    )
    parser.add_argument(
        "--skip-llm", action="store_true",
        help="Apply pre-filter only, no LLM classification"
    )
    parser.add_argument(
        "--whatsapp", action="store_true",
        help="Enrich leads with WhatsApp profile names (requires lookup service running)"
    )
    parser.add_argument(
        "--whatsapp-url", type=str, default=None,
        help="Override WHATSAPP_LOOKUP_URL (e.g. http://127.0.0.1:3457 for Phone 1 fallback)"
    )
    return parser.parse_args()


def main() -> None:
    setup_logging()
    args = parse_args()

    # ── Override WhatsApp URL if specified ──
    global WHATSAPP_LOOKUP_URL
    if args.whatsapp_url:
        WHATSAPP_LOOKUP_URL = args.whatsapp_url
        log.info("WhatsApp URL overridden to %s", WHATSAPP_LOOKUP_URL)

    # ── Load input ──
    input_path = args.input
    if not Path(input_path).exists():
        log.error("Input file not found: %s", input_path)
        log.error("Run gumtree_scrapling.py first, or use --input to specify a file")
        sys.exit(1)

    with open(input_path, encoding="utf-8") as f:
        ads = json.load(f)

    if not isinstance(ads, list):
        log.error("Expected JSON array, got %s", type(ads).__name__)
        sys.exit(1)

    total = len(ads)
    log.info("Loaded %d ads from %s", total, input_path)

    # ── Check env for non-dry-run ──
    if not args.dry_run and not args.skip_llm and not OPENROUTER_API_KEY:
        log.error("OPENROUTER_API_KEY not set in .env")
        log.error("Set it or use --skip-llm to run without LLM classification")
        sys.exit(1)

    # ── Phase 1: Pre-filter ──
    pre_filtered: list[dict] = []
    pre_rejected: list[tuple[dict, str]] = []

    for ad in ads:
        reason = pre_filter(ad)
        if reason:
            pre_rejected.append((ad, reason))
        else:
            pre_filtered.append(ad)

    log.info("Pre-filter: %d passed, %d rejected", len(pre_filtered), len(pre_rejected))
    for ad, reason in pre_rejected:
        log.debug('  [x] "%s" — %s', ad.get('title', '?')[:60], reason)

    if args.skip_llm:
        log.info("--skip-llm: %d ads passed pre-filter (no LLM classification)", len(pre_filtered))
        for ad in pre_filtered:
            log.debug('  [?] "%s" | phone: %s', ad.get('title', '?')[:60], ad.get('phone') or 'none')

        result = {"ok": True, "total": total, "pre_filtered": len(pre_rejected), "passed": len(pre_filtered)}
        print(json.dumps(result))
        return

    # ── Phase 2: LLM classification + enrichment ──
    buyers: list[dict] = []
    llm_rejected: list[tuple[dict, str]] = []
    wa_resolved = 0
    wa_attempted = 0

    for i, ad in enumerate(pre_filtered):
        if i > 0:
            time.sleep(0.2)  # Rate limit: 200ms between LLM calls

        log.info('LLM classifying (%d/%d): "%s"', i + 1, len(pre_filtered), ad.get('title', '?')[:50])

        enrichment = llm_classify(ad)
        if not enrichment:
            llm_rejected.append((ad, "LLM call failed"))
            continue

        classification = enrichment.get("classification", "IRRELEVANT")
        reason = enrichment.get("reason", "no reason")

        if classification == "BUYER":
            composite = enrichment.get("intent_strength", 0) * 0.6 + enrichment.get("urgency_score", 0) * 0.4
            if composite < 5:
                llm_rejected.append((ad, f"BUYER but score too low ({composite:.1f})"))
                log.info("  [~] BUYER but composite %.1f < 5 — skipped", composite)
            else:
                lead = gumtree_ad_to_lead(ad, enrichment)

                # WhatsApp name enrichment (if enabled and lead has a phone)
                if args.whatsapp and lead.get("phone"):
                    wa_attempted += 1
                    wa_name = whatsapp_lookup(lead["phone"], args.whatsapp_url)
                    if wa_name:
                        lead["full_name"] = wa_name
                        wa_resolved += 1
                        log.info("  [wa] Resolved name: %s", wa_name)
                    else:
                        log.info("  [wa] No WhatsApp name for %s", lead['phone'])

                buyers.append(lead)
                log.info("  [+] BUYER (score %.1f): %s", composite, reason)
        else:
            llm_rejected.append((ad, f"{classification}: {reason}"))
            log.debug("  [-] %s: %s", classification, reason)

    # ── Report ──
    log.info("")
    log.info("=" * 60)
    log.info("REPORT")
    log.info("  Total ads loaded:      %d", total)
    log.info("  Pre-filter rejected:   %d", len(pre_rejected))
    log.info("  LLM classified:        %d", len(pre_filtered))
    log.info("  LLM rejected:          %d", len(llm_rejected))
    log.info("  Qualified buyers:      %d", len(buyers))
    if args.whatsapp:
        log.info("  WhatsApp:              %d/%d resolved", wa_resolved, wa_attempted)
    log.info("=" * 60)

    if not buyers:
        log.info("No qualified buyer leads found. Nothing to POST.")
        result = {
            "ok": True, "total": total,
            "pre_filtered": len(pre_rejected),
            "llm_rejected": len(llm_rejected),
            "qualified": 0, "posted": False,
        }
        print(json.dumps(result))
        return

    # Print qualified leads
    for lead in buyers:
        composite = lead["intent_strength"] * 0.6 + lead["urgency_score"] * 0.4
        log.info("")
        log.info("  Qualified lead:")
        log.info("    Name:     %s", lead['full_name'])
        log.info("    Phone:    %s", lead['phone'] or 'none')
        log.info("    City:     %s", lead['city'] or '?')
        log.info("    Province: %s", lead['province'] or '?')
        log.info("    Score:    %.1f (intent=%s, urgency=%s)", composite, lead['intent_strength'], lead['urgency_score'])
        log.debug("    Signal:   %s...", (lead['intent_signal'] or '')[:100])
        log.debug("    Opener:   %s...", (lead['call_script_opener'] or '')[:100])

    # ── Phase 3: POST to webhook ──
    if args.dry_run:
        log.info("--dry-run: %d leads would be POSTed (skipped)", len(buyers))
        result = {
            "ok": True, "total": total,
            "pre_filtered": len(pre_rejected),
            "llm_rejected": len(llm_rejected),
            "qualified": len(buyers), "posted": False, "dry_run": True,
        }
        print(json.dumps(result))
        return

    batch_id = f"B2C-BATCH-{datetime.now().strftime('%Y-%m-%d')}-GUMTREE-001"
    log.info("POSTing %d leads as batch %s", len(buyers), batch_id)

    webhook_result = post_to_webhook(buyers, batch_id)
    if webhook_result:
        log.info("Webhook result: %s", json.dumps(webhook_result, indent=2))
        result = {
            "ok": True, "total": total,
            "pre_filtered": len(pre_rejected),
            "llm_rejected": len(llm_rejected),
            "qualified": len(buyers), "posted": True,
            "webhook_response": webhook_result,
        }
    else:
        log.error("Webhook POST failed")
        result = {
            "ok": False, "total": total,
            "pre_filtered": len(pre_rejected),
            "llm_rejected": len(llm_rejected),
            "qualified": len(buyers), "posted": False,
            "error": "webhook POST failed",
        }

    print(json.dumps(result))


if __name__ == "__main__":
    main()
