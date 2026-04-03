#!/usr/bin/env python3
# =============================================================
# hellopeter_scraper.py — Hellopeter competitor churn lead scraper
# Pulls negative reviews from Cartrack competitors (Netstar,
# Tracker Connect) via Hellopeter's public API. These are people
# unhappy with their current tracker — prime Cartrack prospects.
# =============================================================
# Usage:
#   uv run python scripts/hellopeter_scraper.py
#   uv run python scripts/hellopeter_scraper.py --max 50 --days 30
#   uv run python scripts/hellopeter_scraper.py --out /tmp/hellopeter-leads.json
#   uv run python scripts/hellopeter_scraper.py --post          # POST to B2C webhook
# =============================================================

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

# ── Logging ──────────────────────────────────────────────────

log = logging.getLogger("hellopeter")


def setup_logging() -> None:
    """Configure console + file logging."""
    log.setLevel(logging.DEBUG)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("[%(name)s] %(levelname)s: %(message)s"))
    log.addHandler(console)

    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    fh = logging.FileHandler(log_dir / f"b2c-hellopeter-{today}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    log.addHandler(fh)


# ── Retry constants ──────────────────────────────────────────

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 15]  # seconds

# ── Config ───────────────────────────────────────────────────

HELLOPETER_API = "https://api.hellopeter.com/consumer/business"

# Cartrack competitors — slug must match Hellopeter URL
COMPETITORS = [
    {"slug": "netstar", "name": "Netstar"},
    {"slug": "tracker-connect", "name": "Tracker Connect"},
]

B2C_WEBHOOK_URL = os.environ.get("B2C_WEBHOOK_URL")
B2C_WEBHOOK_TOKEN = os.environ.get("B2C_WEBHOOK_TOKEN") or os.environ.get("WEBHOOK_TOKEN")

# ── Scraper ──────────────────────────────────────────────────

def fetch_reviews(slug: str, max_pages: int = 20) -> list[dict]:
    """Fetch reviews from Hellopeter API. Returns raw review dicts."""
    from scrapling.fetchers import Fetcher

    all_reviews = []
    for page_num in range(1, max_pages + 1):
        url = f"{HELLOPETER_API}/{slug}/reviews?page={page_num}"
        try:
            resp = Fetcher.get(url, stealthy_headers=True, timeout=20, retries=2)
            body = resp.body.decode("utf-8", errors="ignore") if isinstance(resp.body, bytes) else str(resp.body)
            data = json.loads(body)
        except Exception as e:
            log.warning("Error fetching page %d for %s: %s", page_num, slug, e)
            break

        reviews = data.get("data", [])
        if not reviews:
            break

        all_reviews.extend(reviews)

        last_page = data.get("last_page", page_num)
        if page_num >= last_page:
            break

        # Polite delay
        time.sleep(0.3)

    return all_reviews


def filter_negative_reviews(
    reviews: list[dict],
    max_rating: int = 2,
    days: int = 90,
) -> list[dict]:
    """Filter to negative reviews within the date window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    filtered = []

    for r in reviews:
        # Rating filter
        rating = r.get("review_rating", 5)
        if rating > max_rating:
            continue

        # Date filter
        created = r.get("created_at", "")
        try:
            review_date = datetime.strptime(created, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if review_date < cutoff:
                continue
        except ValueError:
            continue

        filtered.append(r)

    return filtered


# ── Churn signal keywords ────────────────────────────────────

CHURN_KEYWORDS = [
    "cancel", "cancellation", "want to cancel",
    "switch", "switching", "moving to",
    "terrible", "worst", "disgusted", "furious",
    "stolen", "car was stolen", "vehicle stolen",
    "no response", "no one answers", "ignored",
    "rip off", "rip-off", "waste of money",
    "not worth", "overcharged", "billing",
    "uninstall", "remove tracker",
    "looking for alternative", "another company",
]


def score_churn_intent(review: dict) -> tuple[int, int, list[str]]:
    """
    Score a review for churn intent and urgency.
    Returns (intent_strength 0-10, urgency_score 0-10, matched_keywords).
    """
    text = f"{review.get('review_title', '')} {review.get('review_content', '')}".lower()

    matched = [kw for kw in CHURN_KEYWORDS if kw in text]

    # Intent: how clearly do they want to leave?
    intent = min(10, 3 + len(matched) * 2)
    if any(kw in text for kw in ["cancel", "cancellation", "switch", "moving to", "another company"]):
        intent = max(intent, 8)
    if any(kw in text for kw in ["stolen", "car was stolen"]):
        intent = max(intent, 9)  # Theft = urgent need for better tracker

    # Urgency: how recent/heated?
    rating = review.get("review_rating", 3)
    urgency = max(0, 8 - rating * 2)  # 1-star = 6, 2-star = 4
    if any(kw in text for kw in ["furious", "disgusted", "worst", "terrible"]):
        urgency = max(urgency, 8)
    if "stolen" in text:
        urgency = 10

    return intent, urgency, matched


def build_story(review: dict) -> str:
    """Build a brief customer story from the review for Claire's context."""
    title = review.get("review_title", "").strip()
    content = review.get("review_content", "").strip()
    rating = review.get("review_rating", "?")
    company = review.get("business_name", "?")
    date = (review.get("created_at") or "")[:10]

    # Truncate content but keep it meaningful
    if len(content) > 500:
        # Cut at sentence boundary
        cut = content[:500].rfind(".")
        if cut > 200:
            content = content[: cut + 1]
        else:
            content = content[:500] + "..."

    return (
        f"[{rating}★ review on {date} about {company}] "
        f"{title}. "
        f"{content}"
    )


def build_call_opener(review: dict, matched_keywords: list[str]) -> str:
    """Generate a personalised call script opener."""
    name = review.get("author", "").split()[0] if review.get("author") else "there"
    company = review.get("business_name", "your current provider")

    if "stolen" in " ".join(matched_keywords):
        return (
            f"Hi {name}, I saw you had a difficult experience with {company} "
            f"after a vehicle theft. Cartrack has a 90%+ recovery rate — "
            f"would you like to hear how we could help?"
        )
    if any(kw in matched_keywords for kw in ["cancel", "cancellation", "switch"]):
        return (
            f"Hi {name}, I understand you've been considering alternatives to {company}. "
            f"Cartrack offers hassle-free switching with no installation fee — "
            f"can I share what we offer?"
        )
    return (
        f"Hi {name}, I noticed your recent experience with {company} "
        f"and wanted to reach out. Cartrack is rated 4.6★ on Hellopeter — "
        f"would you be open to hearing how we compare?"
    )


# ── Lead assembly ────────────────────────────────────────────

def review_to_lead(review: dict) -> dict:
    """Convert a Hellopeter review to a B2C lead."""
    intent, urgency, matched = score_churn_intent(review)
    story = build_story(review)
    opener = build_call_opener(review, matched)

    permalink = review.get("permalink", "")
    slug = review.get("business_slug", "")
    source_url = f"https://www.hellopeter.com/{slug}/{permalink}" if permalink else ""

    return {
        "full_name": review.get("author") or review.get("authorDisplayName") or "Unknown",
        "phone": None,  # Hellopeter doesn't expose phone — enrich via WhatsApp later
        "email": None,
        "province": None,
        "city": None,
        "intent_signal": story,
        "intent_source": f"Hellopeter ({review.get('business_name', 'competitor')} complaint)",
        "intent_source_url": source_url,
        "intent_date": (review.get("created_at") or "")[:10],
        "vehicle_make_model": None,
        "vehicle_year": None,
        "call_script_opener": opener,
        "data_confidence": "Medium",  # No phone yet
        "sources_used": "Hellopeter public API",
        "intent_strength": intent,
        "urgency_score": urgency,
        "competitor": review.get("business_name"),
        "review_rating": review.get("review_rating"),
    }


# ── Webhook POST ─────────────────────────────────────────────

def post_to_webhook(leads: list[dict], batch_id: str) -> dict | None:
    """POST the B2C batch to the n8n webhook.

    Retries on 5xx and timeout errors with exponential backoff.
    4xx errors fail immediately.
    """
    if not B2C_WEBHOOK_URL or not B2C_WEBHOOK_TOKEN:
        log.error("B2C_WEBHOOK_URL / B2C_WEBHOOK_TOKEN not set")
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
    default_out = str(
        Path(__file__).parent.parent / "memory" / f"hellopeter-leads-{today}.json"
    )

    parser = argparse.ArgumentParser(
        description="Scrape Hellopeter for competitor churn leads (Netstar, Tracker Connect)"
    )
    parser.add_argument("--max", type=int, default=50, dest="max_leads", help="Max leads to collect (default: 50)")
    parser.add_argument("--days", type=int, default=90, help="Only reviews from last N days (default: 90)")
    parser.add_argument("--max-rating", type=int, default=2, help="Max star rating to include (default: 2)")
    parser.add_argument("--out", type=str, default=default_out, help="Output JSON file path")
    parser.add_argument("--post", action="store_true", help="POST leads to B2C webhook")
    return parser.parse_args()


def main() -> None:
    setup_logging()
    args = parse_args()

    log.info("Starting — max %d leads, last %d days, ≤%d★", args.max_leads, args.days, args.max_rating)

    all_leads: list[dict] = []
    seen_authors: set[str] = set()  # Dedup by author name

    for comp in COMPETITORS:
        if len(all_leads) >= args.max_leads:
            break

        slug = comp["slug"]
        name = comp["name"]

        # Calculate pages needed (11 reviews per page, but many will be filtered)
        max_pages = min(50, (args.max_leads * 3) // 11 + 1)

        log.info("Fetching %s reviews (up to %d pages)...", name, max_pages)
        reviews = fetch_reviews(slug, max_pages=max_pages)
        log.info("%s: %d raw reviews fetched", name, len(reviews))

        # Filter
        negative = filter_negative_reviews(reviews, max_rating=args.max_rating, days=args.days)
        log.info("%s: %d negative reviews in last %d days", name, len(negative), args.days)

        # Convert to leads
        for review in negative:
            if len(all_leads) >= args.max_leads:
                break

            # Dedup by author
            author = review.get("author") or review.get("authorDisplayName") or ""
            if not author or author.lower() == "anonymous":
                continue
            if author in seen_authors:
                continue
            seen_authors.add(author)

            lead = review_to_lead(review)

            # Only include leads with meaningful churn intent
            composite = lead["intent_strength"] * 0.6 + lead["urgency_score"] * 0.4
            if composite < 4:
                continue

            all_leads.append(lead)

    # Sort by composite score (highest first)
    all_leads.sort(
        key=lambda l: l["intent_strength"] * 0.6 + l["urgency_score"] * 0.4,
        reverse=True,
    )

    # Trim to max
    all_leads = all_leads[: args.max_leads]

    # Report
    log.info("")
    log.info("=" * 60)
    log.info("RESULTS: %d qualified churn leads", len(all_leads))
    log.info("=" * 60)

    for i, lead in enumerate(all_leads[:10], 1):  # Show top 10
        composite = lead["intent_strength"] * 0.6 + lead["urgency_score"] * 0.4
        log.info("")
        log.info("  #%d %s (%s, %d★)", i, lead['full_name'], lead['competitor'], lead['review_rating'])
        log.info("     Score: %.1f (intent=%d, urgency=%d)", composite, lead['intent_strength'], lead['urgency_score'])
        log.info("     Date:  %s", lead['intent_date'])
        log.debug("     Story: %s...", lead['intent_signal'][:150])

    if len(all_leads) > 10:
        log.info("  ... and %d more leads", len(all_leads) - 10)

    # Write output file
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(all_leads, f, indent=2, ensure_ascii=False)
    log.info("Saved → %s", args.out)

    # POST to webhook
    if args.post:
        batch_id = f"B2C-BATCH-{datetime.now().strftime('%Y-%m-%d')}-HELLOPETER-001"
        log.info("POSTing %d leads as batch %s", len(all_leads), batch_id)
        result = post_to_webhook(all_leads, batch_id)
        if result:
            log.info("Webhook result: %s", json.dumps(result, indent=2))

    # Stdout: structured result
    print(json.dumps({
        "ok": True,
        "count": len(all_leads),
        "out": args.out,
        "competitors": {c["name"]: sum(1 for l in all_leads if l.get("competitor") == c["name"]) for c in COMPETITORS},
    }))


if __name__ == "__main__":
    main()
