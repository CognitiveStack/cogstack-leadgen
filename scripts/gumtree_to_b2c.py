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
# =============================================================

import argparse
import html
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

# ── Environment ──────────────────────────────────────────────

B2C_WEBHOOK_URL = os.environ.get("B2C_WEBHOOK_URL")
B2C_WEBHOOK_TOKEN = os.environ.get("B2C_WEBHOOK_TOKEN") or os.environ.get("WEBHOOK_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

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
    """Classify and enrich a Gumtree ad via gpt-4o-mini on OpenRouter."""
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

        if response.status_code != 200:
            print(f"[bridge] LLM API error: {response.status_code} {response.text[:200]}", file=sys.stderr)
            return None

        content = response.json()["choices"][0]["message"]["content"]
        # Strip markdown code fences if present
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)

        return json.loads(content)

    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"[bridge] LLM response parse error: {e}", file=sys.stderr)
        return None
    except httpx.HTTPError as e:
        print(f"[bridge] LLM request failed: {e}", file=sys.stderr)
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
    """POST the B2C batch to the n8n webhook. Returns response JSON or None."""
    if not B2C_WEBHOOK_URL:
        print("[bridge] ERROR: B2C_WEBHOOK_URL not set in .env", file=sys.stderr)
        return None
    if not B2C_WEBHOOK_TOKEN:
        print("[bridge] ERROR: B2C_WEBHOOK_TOKEN not set in .env", file=sys.stderr)
        return None

    payload = {
        "batch_id": batch_id,
        "segment": "B2C",
        "leads": leads,
    }

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
        print(f"[bridge] Webhook response: {response.status_code}", file=sys.stderr)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"[bridge] Webhook error: {response.text[:500]}", file=sys.stderr)
            return None
    except httpx.HTTPError as e:
        print(f"[bridge] Webhook request failed: {e}", file=sys.stderr)
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # ── Load input ──
    input_path = args.input
    if not Path(input_path).exists():
        print(f"[bridge] ERROR: Input file not found: {input_path}", file=sys.stderr)
        print(f"[bridge] Run gumtree_scrapling.py first, or use --input to specify a file", file=sys.stderr)
        sys.exit(1)

    with open(input_path, encoding="utf-8") as f:
        ads = json.load(f)

    if not isinstance(ads, list):
        print(f"[bridge] ERROR: Expected JSON array, got {type(ads).__name__}", file=sys.stderr)
        sys.exit(1)

    total = len(ads)
    print(f"[bridge] Loaded {total} ads from {input_path}", file=sys.stderr)

    # ── Check env for non-dry-run ──
    if not args.dry_run and not args.skip_llm and not OPENROUTER_API_KEY:
        print("[bridge] ERROR: OPENROUTER_API_KEY not set in .env", file=sys.stderr)
        print("[bridge] Set it or use --skip-llm to run without LLM classification", file=sys.stderr)
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

    print(f"[bridge] Pre-filter: {len(pre_filtered)} passed, {len(pre_rejected)} rejected", file=sys.stderr)
    for ad, reason in pre_rejected:
        print(f"  [x] \"{ad.get('title', '?')[:60]}\" — {reason}", file=sys.stderr)

    if args.skip_llm:
        # In skip-llm mode, treat all pre-filtered ads as potential leads
        print(f"[bridge] --skip-llm: {len(pre_filtered)} ads passed pre-filter (no LLM classification)", file=sys.stderr)
        for ad in pre_filtered:
            print(f"  [?] \"{ad.get('title', '?')[:60]}\" | phone: {ad.get('phone') or 'none'}", file=sys.stderr)

        # Output summary as JSON
        result = {"ok": True, "total": total, "pre_filtered": len(pre_rejected), "passed": len(pre_filtered)}
        print(json.dumps(result))
        return

    # ── Phase 2: LLM classification + enrichment ──
    buyers: list[dict] = []
    llm_rejected: list[tuple[dict, str]] = []

    for i, ad in enumerate(pre_filtered):
        if i > 0:
            time.sleep(0.2)  # Rate limit: 200ms between LLM calls

        print(f"[bridge] LLM classifying ({i + 1}/{len(pre_filtered)}): \"{ad.get('title', '?')[:50]}\"", file=sys.stderr)

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
                print(f"  [~] BUYER but composite {composite:.1f} < 5 — skipped", file=sys.stderr)
            else:
                lead = gumtree_ad_to_lead(ad, enrichment)
                buyers.append(lead)
                print(f"  [+] BUYER (score {composite:.1f}): {reason}", file=sys.stderr)
        else:
            llm_rejected.append((ad, f"{classification}: {reason}"))
            print(f"  [-] {classification}: {reason}", file=sys.stderr)

    # ── Report ──
    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[bridge] REPORT", file=sys.stderr)
    print(f"  Total ads loaded:      {total}", file=sys.stderr)
    print(f"  Pre-filter rejected:   {len(pre_rejected)}", file=sys.stderr)
    print(f"  LLM classified:        {len(pre_filtered)}", file=sys.stderr)
    print(f"  LLM rejected:          {len(llm_rejected)}", file=sys.stderr)
    print(f"  Qualified buyers:      {len(buyers)}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    if not buyers:
        print(f"[bridge] No qualified buyer leads found. Nothing to POST.", file=sys.stderr)
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
        print(f"\n  Qualified lead:", file=sys.stderr)
        print(f"    Name:    {lead['full_name']}", file=sys.stderr)
        print(f"    Phone:   {lead['phone'] or 'none'}", file=sys.stderr)
        print(f"    City:    {lead['city'] or '?'}", file=sys.stderr)
        print(f"    Province:{lead['province'] or '?'}", file=sys.stderr)
        print(f"    Score:   {composite:.1f} (intent={lead['intent_strength']}, urgency={lead['urgency_score']})", file=sys.stderr)
        print(f"    Signal:  {(lead['intent_signal'] or '')[:100]}...", file=sys.stderr)
        print(f"    Opener:  {(lead['call_script_opener'] or '')[:100]}...", file=sys.stderr)

    # ── Phase 3: POST to webhook ──
    if args.dry_run:
        print(f"\n[bridge] --dry-run: {len(buyers)} leads would be POSTed (skipped)", file=sys.stderr)
        result = {
            "ok": True, "total": total,
            "pre_filtered": len(pre_rejected),
            "llm_rejected": len(llm_rejected),
            "qualified": len(buyers), "posted": False, "dry_run": True,
        }
        print(json.dumps(result))
        return

    batch_id = f"B2C-BATCH-{datetime.now().strftime('%Y-%m-%d')}-GUMTREE-001"
    print(f"\n[bridge] POSTing {len(buyers)} leads as batch {batch_id}", file=sys.stderr)

    webhook_result = post_to_webhook(buyers, batch_id)
    if webhook_result:
        print(f"[bridge] Webhook result: {json.dumps(webhook_result, indent=2)}", file=sys.stderr)
        result = {
            "ok": True, "total": total,
            "pre_filtered": len(pre_rejected),
            "llm_rejected": len(llm_rejected),
            "qualified": len(buyers), "posted": True,
            "webhook_response": webhook_result,
        }
    else:
        print(f"[bridge] Webhook POST failed", file=sys.stderr)
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
