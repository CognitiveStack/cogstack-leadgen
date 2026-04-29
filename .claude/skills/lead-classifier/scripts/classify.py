#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "httpx>=0.28.1",
#     "python-dotenv>=1.2.1",
# ]
# ///
# =============================================================
# classify.py — B2C lead classifier via OpenRouter LLM
# Reads raw leads JSON array (from scrape.py or search.py),
# pre-filters sellers/irrelevant, LLM-classifies buyers,
# outputs B2C webhook-ready JSON array.
# =============================================================
# Usage:
#   uv run scripts/classify.py                       # reads from stdin
#   uv run scripts/classify.py --input leads.json
#   uv run scripts/classify.py --dry-run             # prints without outputting JSON
# =============================================================

import argparse
import html
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path.home() / ".hermes/.env")

# ── Logging ──────────────────────────────────────────────────

log = logging.getLogger("classifier")


def setup_logging(log_dir: Path, source: str) -> None:
    log.setLevel(logging.DEBUG)
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("[%(name)s] %(levelname)s: %(message)s"))
    log.addHandler(console)
    log_dir.mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    fh = logging.FileHandler(log_dir / f"{source}-{today}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    log.addHandler(fh)


# ── Credentials ──────────────────────────────────────────────

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# ── Retry constants — copied verbatim from gumtree_to_b2c.py ─

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 15]

# ── Scoring signals ──────────────────────────────────────────

LUXURY_MODELS = [
    "fortuner", "land cruiser", "prado", "ranger", "hilux", "triton",
    "amarok", "navara", "isuzu d-max", "defender", "discovery", "patrol",
    "pajero", "audi", "bmw", "mercedes", "lexus", "porsche",
]

COMPETITOR_NAMES = ["cartrack", "tracker connect", "tracker", "netstar", "mix telematics", "beame"]

# ── Pre-filter signal lists — copied verbatim from gumtree_to_b2c.py ─

SELLER_SIGNALS = [
    "we are selling", "includes sim", "no subscription", "subscription-free",
    "order now", "shop now", "visit our", "our range",
    "in stock", "available now", "special offer",
    "we deliver", "nationwide delivery", "free delivery",
    "wholesale", "bulk discount", "unit price",
    "(pty) ltd", "pty ltd",
    # Tracker company marketing page signals
    "get a quote", "request a quote", "get your quote",
    "contact us today", "call us today", "sign up today",
    "get started today", "start tracking today",
    "our packages", "our plans", "our pricing", "our solution",
    "view our packages", "view packages", "choose your plan",
    "we offer", "we provide", "our trackers", "our units",
    "per month*", "r per month", "r/month", "monthly fee",
    "free fitment", "free installation included",
    "download our app", "download the app",
]

IRRELEVANT_SIGNALS = [
    "job", "hiring", "vacancy", "looking for a driver",
    "debt collector", "admin assistant", "coordinator",
    "field tracer", "recruitment", "onboarding",
    "pet tracker", "dog tracker", "cat tracker",
    "key cutting", "locksmith",
    "smart health ring", "wearable",
    "obd splitter", "y-splitter", "extension cable",
    "head guide", "game lodge", "safari lodge", "safari",
    "brand engagement", "social media marketing",
]

BLOCKED_URL_SEGMENTS = [
    "/a-heavy-trucks-buses/",
    "/a-other-replacement-car-part/", "/a-car-interior-accessories/",
    "/a-accessories-styling/", "/a-auto-electrical-parts/",
    "/a-electronics-it-services/", "/a-wearable-technology/",
    "/a-other-pets/", "/a-removals-storage/",
    "/a-property-", "/a-other-services/", "/a-legal-services/",
    "/a-other-business", "/a-business+to+business",
    "/a-recruitment-services/", "/a-other-jobs/",
]

# Consumer/forum domains — these are ALLOWED even if they mention "tracker" in path
CONSUMER_DOMAINS = [
    "reddit.com", "hellopeter.com", "mybroadband.co.za", "facebook.com",
    "twitter.com", "instagram.com", "gumtree.co.za", "autotrader.co.za",
    "cars.co.za", "olx.co.za", "arrivealive.co.za", "wheels24.co.za",
    "carbibles.com", "car.co.za", "youtube.com",
]

# URL keyword patterns that indicate a tracker company service site
# (catches unlisted domains like trackstar.co.za, fleetwatch.co.za, etc.)
TRACKER_DOMAIN_KEYWORDS = [
    "cartrack", "netstar", "mixtelematics", "mix-telematics",
    "ctrack", "mtrack", "tgtrack", "tgtracking", "beame",
    "fleetwatch", "trackstar", "gpstracking", "gpstracker",
    "vehicletracking", "vehicle-tracking", "vehicletrack",
    "autotrack", "autotracking",
]

# Tracker company domains — their own pages are SELLER not BUYER
BLOCKED_DOMAINS = [
    "cartrack.com", "cartrack.co.za",
    "trackersa.co.za", "tracker.co.za",
    "netstar.co.za",
    "mixtelematics.com", "mixtelematics.co.za",
    "beame.co.za",
    "ctrack.co.za",
    "mtrack.co.za",
    "multitrack.co.za",
    "mzansitracker.co.za",
    "tgtracking.co.za",
    "matrix.co.za",
]

# ── Location → Province mapping — copied verbatim from gumtree_to_b2c.py ─

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
    if not location:
        return None
    loc_lower = location.lower()
    for key, province in LOCATION_TO_PROVINCE.items():
        if key in loc_lower:
            return province
    return None


# ── LLM prompt ───────────────────────────────────────────────

LLM_PROMPT_TEMPLATE = """You are classifying a lead to determine if the person is a BUYER seeking a vehicle tracker.

Ad title: {title}
Ad description: {description}
Ad location: {location}
Ad URL: {url}
Source: {source}
Competitor (if complaint source): {competitor}

Respond with ONLY valid JSON (no markdown, no explanation):
{{
  "classification": "BUYER" or "SELLER" or "IRRELEVANT",
  "reason": "<one sentence explaining why>",
  "full_name": "<name if visible in text, else 'Unknown'>",
  "intent_signal": "<if BUYER: verbatim quote showing they WANT a tracker, max 300 chars. if not BUYER: null>",
  "intent_strength": <integer 0-10, 0 if not a buyer>,
  "urgency_score": <integer 0-10, 0 if not a buyer>,
  "call_script_opener": "<if BUYER: personalized opener referencing their specific situation, max 200 chars. if not BUYER: null>",
  "province": "<SA province if determinable from content, else null>",
  "pain_point": "<if BUYER: their specific problem/frustration in one sentence, e.g. 'Car stolen with no tracker' or 'Unhappy with Cartrack service'. else null>",
  "car_model": "<car model if mentioned, e.g. 'Toyota Fortuner' or 'Ford Ranger'. else null>",
  "competitor": "<competitor name if they are switching FROM Cartrack/Tracker/Netstar/MiX/Beame. else null>"
}}

Classification rules:
- BUYER: a PRIVATE INDIVIDUAL expressing their OWN personal need. This includes:
  (a) Someone who wants/needs/is looking for a vehicle tracker
  (b) CHURN SIGNAL — someone complaining about Cartrack, Tracker Connect, Netstar, MiX, or Beame (cancellation, poor service, unhappy). These people WILL need a new tracker provider. If source is "HelloPeter" and the review is about a competitor, classify BUYER.
  (c) Theft/hijacking victim who needs a tracker
  (d) Insurance requirement forcing them to get a tracker
  Forum posts, Reddit threads, HelloPeter reviews, classified "wanted" ads count.
- SELLER: a company or website PROMOTING its own tracking service/product.
- IRRELEVANT: article/blog/comparison post without a specific person's complaint, job listing, pet tracker, generic news.

CRITICAL: HelloPeter reviews where someone complains about a competitor ARE churn leads — classify as BUYER. The person is effectively saying "I need a new tracker company"."""


# ── Pre-filter ───────────────────────────────────────────────

def _url_domain(url: str) -> str:
    """Extract just the netloc/domain from a URL for matching."""
    # Quick extraction without importing urllib for speed
    try:
        after_scheme = url.split("://", 1)[-1]
        return after_scheme.split("/")[0].lower()
    except Exception:
        return url.lower()


def pre_filter(ad: dict) -> str | None:
    """Return rejection reason or None if ad passes pre-filter."""
    title = (ad.get("title") or "").lower()
    desc = html.unescape(ad.get("description") or "").lower()
    text = f"{title} {desc}"
    source = ad.get("source", "Gumtree")

    # Non-SA phone
    phone = ad.get("phone") or ""
    if phone and not phone.startswith("+27"):
        return f"non-SA phone: {phone}"

    # URL in blocked category (Gumtree path segments only)
    url = ad.get("url") or ""
    domain = _url_domain(url)

    for seg in BLOCKED_URL_SEGMENTS:
        if seg in url:
            return f"blocked URL category: {seg}"

    if "-jobs/" in url:
        return "job listing URL"

    # Tracker company's own domain — always seller, never buyer
    for blocked in BLOCKED_DOMAINS:
        if blocked in domain:
            return f"tracker company domain: {blocked}"

    # Unknown tracker company domain — check DOMAIN ONLY (not path)
    # Skip for known consumer/forum domains
    is_consumer = any(cd in domain for cd in CONSUMER_DOMAINS)
    if not is_consumer:
        for kw in TRACKER_DOMAIN_KEYWORDS:
            if kw in domain:
                return f"tracker company domain keyword: {kw}"

    # SELLER_SIGNALS — only apply to Gumtree classifieds ads.
    # Exa/Tavily results include forum posts where phrases like "monthly fee" or
    # "we offer" appear in discussion context, not as seller signals.
    if source == "Gumtree":
        for signal in SELLER_SIGNALS:
            if signal in text:
                return f"seller signal: '{signal}'"

    for signal in IRRELEVANT_SIGNALS:
        if signal in text:
            return f"irrelevant signal: '{signal}'"

    # ── IDENTITY GATE — no LLM call for anonymous leads ──────────
    # We need a phone OR an identifiable name before spending tokens.
    # HelloPeter reviewers use first names only — that's sufficient (real account, known complaint).
    # Gumtree/Exa results require 2+ word name OR phone.
    phone = ad.get("phone")
    name = ad.get("name") or ad.get("reviewer_name") or ""
    source = ad.get("source", "")
    has_phone = bool(phone)
    is_hellopeter = source == "HelloPeter"
    has_name = bool(name and name.lower() not in ("unknown", "") and (
        is_hellopeter or len(name.split()) >= 2  # HelloPeter: first name OK
    ))
    if not has_phone and not has_name:
        return "no identity: no phone or full name"

    return None


# ── LLM classification ───────────────────────────────────────

def llm_classify(ad: dict) -> dict | None:
    """Classify and enrich a lead via gpt-4o-mini on OpenRouter."""
    if not OPENROUTER_API_KEY:
        log.error("OPENROUTER_API_KEY not set")
        return None

    desc = html.unescape(ad.get("description") or "")
    if len(desc) > 1500:
        desc = desc[:1500] + "..."

    prompt = LLM_PROMPT_TEMPLATE.format(
        title=ad.get("title") or "",
        description=desc,
        location=ad.get("location") or "Unknown",
        url=ad.get("url") or "",
        source=ad.get("source", "Gumtree"),
        competitor=ad.get("competitor") or "None",
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
                    "temperature": 0.2,
                    "max_tokens": 600,
                    "response_format": {"type": "json_object"},
                },
                timeout=30.0,
            )

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", RETRY_DELAYS[attempt]))
                log.warning("LLM rate limited (429), retrying in %ds (%d/%d)", retry_after, attempt + 1, MAX_RETRIES)
                time.sleep(retry_after)
                continue

            if response.status_code >= 500:
                delay = RETRY_DELAYS[attempt]
                log.warning("LLM server error %d, retrying in %ds (%d/%d)", response.status_code, delay, attempt + 1, MAX_RETRIES)
                time.sleep(delay)
                continue

            if response.status_code != 200:
                log.error("LLM API error: %d %s", response.status_code, response.text[:200])
                return None

            content = response.json()["choices"][0]["message"]["content"]
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
            log.warning("LLM request failed: %s, retrying in %ds (%d/%d)", e, delay, attempt + 1, MAX_RETRIES)
            if attempt < MAX_RETRIES - 1:
                time.sleep(delay)

    log.error("LLM classify failed after %d retries", MAX_RETRIES)
    return None


# ── Score adjustment ─────────────────────────────────────────

def signal_score_adjustment(ad: dict, enrichment: dict) -> float:
    """Apply rule-based score adjustments on top of the LLM composite score."""
    text = f"{(ad.get('title') or '')} {(ad.get('description') or '')}".lower()
    adjustment = 0.0

    # +2: car stolen (fear signal, very urgent)
    if any(p in text for p in ("car stolen", "vehicle stolen", "bakkie stolen", "hijacked")):
        adjustment += 2.0

    # +2: insurance requires tracker (forced buyer — highest intent)
    if any(p in text for p in ("insurance requires tracker", "insurance tracker required",
                               "insurance won't cover", "insurance company tracker",
                               "tracker for insurance")):
        adjustment += 2.0

    # +2: cancel + competitor name (churn signal)
    if any(c in text for c in COMPETITOR_NAMES):
        if any(p in text for p in ("cancel", "cancellation", "switch", "switching",
                                    "alternative", "unhappy", "complaint", "poor service")):
            adjustment += 2.0

    # +1: just bought + luxury model (new car = needs tracker)
    if any(p in text for p in ("just bought", "just purchased", "new car", "newly bought")):
        if any(m in text for m in LUXURY_MODELS):
            adjustment += 1.0

    # -3: generic article/forum thread (not an individual buyer)
    # Signals: review comparisons, "top 10", "best tracker", news articles
    if any(p in text for p in ("top 10", "best car tracker", "tracker comparison",
                                "review of cartrack", "compare trackers",
                                "tracker review south africa")):
        adjustment -= 3.0

    return adjustment


# ── Lead assembly ────────────────────────────────────────────

def build_b2c_lead(ad: dict, enrichment: dict, adjusted_composite: float) -> dict:
    """Map raw lead + LLM enrichment to B2C webhook schema."""
    location = ad.get("location")
    province = enrichment.get("province") or infer_province(location)
    intent_date = (ad.get("scraped_at") or datetime.now(timezone.utc).isoformat())[:10]
    source = ad.get("source", "Gumtree")

    # Derive urgency label from adjusted composite score
    if adjusted_composite >= 8.0:
        urgency = "high"
    elif adjusted_composite >= 5.5:
        urgency = "medium"
    else:
        urgency = "low"

    # Competitor: prefer raw lead field (HelloPeter has it set), fall back to LLM
    competitor = ad.get("competitor") or enrichment.get("competitor")
    # pain_point: prefer raw lead field (HelloPeter scraper sets it), fall back to LLM
    pain_point = ad.get("pain_point") or enrichment.get("pain_point")

    # ── Two-bucket status ─────────────────────────────────────
    # "Pending QA"          — phone present, call centre can dial now
    # "Pending Enrichment"  — named lead, needs Exa phone lookup first
    phone = ad.get("phone")
    full_name = enrichment.get("full_name") or ad.get("reviewer_name") or "Unknown"
    if phone:
        notion_status = "Pending QA"
    elif full_name and full_name != "Unknown":
        notion_status = "Pending Enrichment"
    else:
        notion_status = "Pending Enrichment"  # identity gate ensures name exists

    return {
        "full_name": full_name,
        "phone": phone,
        "email": None,
        "province": province,
        "city": location,
        "intent_signal": enrichment.get("intent_signal") or html.unescape(ad.get("description") or "")[:300],
        "intent_source": source,
        "intent_source_url": ad["url"],
        "intent_date": intent_date,
        "vehicle_make_model": enrichment.get("car_model"),
        "vehicle_year": None,
        "call_script_opener": enrichment.get("call_script_opener") or "",
        "data_confidence": "High" if phone else "Medium",
        "sources_used": f"{source} public listing",
        "intent_strength": enrichment.get("intent_strength", 5),
        "urgency_score": enrichment.get("urgency_score", 5),
        "lead_source": source,
        "pain_point": pain_point,
        "car_model": enrichment.get("car_model"),
        "competitor": competitor,
        "urgency": urgency,
        "status": notion_status,
    }


# ── Main ──────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify raw B2C leads via OpenRouter LLM"
    )
    parser.add_argument("--input", type=str, default=None, help="Input JSON file (default: stdin)")
    parser.add_argument("--dry-run", action="store_true", help="Print classified leads to stderr, don't emit JSON to stdout")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    log_dir = Path.home() / "vault/projects/cogstack-leadgen/logs"
    setup_logging(log_dir, "classifier")

    # Load input
    if args.input:
        with open(args.input, encoding="utf-8") as f:
            ads = json.load(f)
    else:
        try:
            ads = json.load(sys.stdin)
        except json.JSONDecodeError as e:
            log.error("Failed to parse stdin as JSON: %s", e)
            sys.exit(1)

    if not isinstance(ads, list):
        log.error("Expected JSON array, got %s", type(ads).__name__)
        sys.exit(1)

    total = len(ads)
    log.info("Loaded %d leads for classification", total)

    if not args.dry_run and not OPENROUTER_API_KEY:
        log.error("OPENROUTER_API_KEY not set in ~/.hermes/.env")
        sys.exit(1)

    # Phase 1: pre-filter
    pre_filtered = []
    pre_rejected_count = 0
    for ad in ads:
        reason = pre_filter(ad)
        if reason:
            log.debug('[x] "%s" — %s', (ad.get("title") or "?")[:60], reason)
            pre_rejected_count += 1
        else:
            pre_filtered.append(ad)

    log.info("Pre-filter: %d passed, %d rejected", len(pre_filtered), pre_rejected_count)

    # Phase 2: LLM classification
    qualified_leads = []
    llm_rejected_count = 0

    for i, ad in enumerate(pre_filtered):
        if i > 0:
            time.sleep(0.2)  # 200ms rate limit between LLM calls

        log.info('LLM classifying (%d/%d): "%s"', i + 1, len(pre_filtered), (ad.get("title") or "?")[:50])

        enrichment = llm_classify(ad)
        if not enrichment:
            llm_rejected_count += 1
            continue

        classification = enrichment.get("classification", "IRRELEVANT")
        reason = enrichment.get("reason", "no reason")

        if classification == "BUYER":
            intent_strength = enrichment.get("intent_strength", 0)
            urgency_score = enrichment.get("urgency_score", 0)
            composite = (intent_strength * 0.6) + (urgency_score * 0.4)
            adjustment = signal_score_adjustment(ad, enrichment)
            adjusted_composite = composite + adjustment

            # Identity-first threshold: if lead has a phone or full name, accept score >= 4.
            # Anonymous leads (Exa/Tavily) keep the higher 5.0 bar.
            phone_present = bool(ad.get("phone"))
            name_present = bool(ad.get("name") or ad.get("reviewer_name"))
            has_identity = phone_present or name_present
            min_score = 4.0 if has_identity else 5.0

            if adjusted_composite < min_score:
                log.info("  [~] BUYER but score %.1f < %.1f (identity=%s) — skipped",
                         adjusted_composite, min_score, has_identity)
                llm_rejected_count += 1
            else:
                lead = build_b2c_lead(ad, enrichment, adjusted_composite)
                qualified_leads.append(lead)
                log.info("  [+] BUYER (score %.1f, adj %+.1f): %s",
                         adjusted_composite, adjustment, reason)
        else:
            log.debug("  [-] %s: %s", classification, reason)
            llm_rejected_count += 1

    log.info("")
    log.info("=" * 60)
    log.info("Total: %d | Pre-rejected: %d | LLM-rejected: %d | Qualified: %d",
             total, pre_rejected_count, llm_rejected_count, len(qualified_leads))
    log.info("=" * 60)

    if args.dry_run:
        log.info("--dry-run: would output %d leads", len(qualified_leads))
        for lead in qualified_leads:
            composite = lead["intent_strength"] * 0.6 + lead["urgency_score"] * 0.4
            log.info("  • %s | %s | score %.1f | urgency: %s | competitor: %s | phone: %s",
                     lead.get("city") or "?",
                     lead.get("lead_source", "?"),
                     composite,
                     lead.get("urgency", "?"),
                     lead.get("competitor") or "none",
                     lead.get("phone") or "none")
        return

    print(json.dumps(qualified_leads, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
