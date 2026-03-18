#!/usr/bin/env python3
# =============================================================
# gumtree_scrapling.py — Gumtree Wanted ads scraper
# Uses Scrapling StealthyFetcher (patchright + Cloudflare solver)
# to bypass bot protection that defeated curl-impersonate and
# vanilla Playwright+stealth.
# =============================================================
# Usage:
#   uv run python scripts/gumtree_scrapling.py
#   uv run python scripts/gumtree_scrapling.py --max 20 --out /tmp/gumtree.json
#
# Requires (one-time setup on bigtorig):
#   uv pip install "scrapling[fetchers]>=0.4.2"
#   uv run scrapling install   # downloads Chromium + patchright binaries (~300MB)
#
# Output JSON per lead: { title, description, phone, location, price, adid, url, scraped_at }
# Drop-in replacement for gumtree_scraper.js — same schema, same CLI flags.
# =============================================================

import argparse
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Gumtree-owned numbers injected site-wide (WhatsApp button, support links).
# These appear in the rendered DOM on every ad page — not seller phones.
_GUMTREE_NUMBERS = {"+27756035177", "27756035177", "0870220222", "+27870220222"}

from dotenv import load_dotenv

load_dotenv()

# ── Constants ─────────────────────────────────────────────────

# NOTE: Gumtree removed the "Wanted Ads" top-level category (c9110) in 2025/2026.
# All /s-wanted-ads/... paths now 301-redirect to /s-all-the-ads/v1b0p1 (losing the keyword).
# Use buyer-intent keyword phrases (?q=) to surface people looking to BUY a tracker.
# Category-level blocklist in extract_ad_links() further filters seller/job/car ads by URL.
SEARCH_URLS = [
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=need+car+tracker",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=want+car+tracker",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=car+tracker+wanted",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=looking+for+tracker",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=gps+tracker+needed",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=vehicle+tracker+wanted",
]

# Gumtree URL path segments for categories that never produce buyer-intent tracker leads.
# Checked at link-extraction time to skip irrelevant ads before fetching their pages.
# Rule: any URL segment containing "-jobs/" is a job ad — blocked in extract_ad_links().
_BLOCKED_CATEGORIES = [
    # Cars/vehicles for sale (sellers, not tracker buyers)
    "/a-cars-bakkies/",
    "/a-heavy-trucks-buses/",
    "/a-other-replacement-car-part/",
    "/a-car-interior-accessories/",
    "/a-accessories-styling/",
    "/a-auto-electrical-parts/",
    # Electronics sellers (GPS/tracker sellers, not buyers)
    "/a-electronics-it-services/",
    "/a-wearable-technology/",
    # Pets
    "/a-other-pets/",
    # Removals/property/services
    "/a-removals-storage/",
    "/a-property-",
    "/a-other-services/",
    "/a-legal-services/",
    # Business-to-business
    "/a-other-business",
    "/a-business+to+business",
    # Recruitment / job listings
    "/a-recruitment-services/",
    "/a-other-jobs/",
]

BLOCK_SIGNALS = ["The request is blocked", "Access Denied", "cf-challenge"]

PHONE_RE = re.compile(r"(?:\+27|27|0)[6-8]\d[\s\-]?\d{3}[\s\-]?\d{4}")

GUMTREE_BASE = "https://www.gumtree.co.za"


# ── Helpers ───────────────────────────────────────────────────

def extract_phone(text: str | None) -> str | None:
    """Extract and normalise a SA phone number from text."""
    if not text:
        return None
    match = PHONE_RE.search(text)
    if not match:
        return None
    # Normalise: strip spaces and dashes
    number = re.sub(r"[\s\-]", "", match.group(0))
    # Ensure +27 prefix
    if number.startswith("0"):
        number = "+27" + number[1:]
    elif number.startswith("27"):
        number = "+" + number
    return number


def extract_ad_links(page) -> list[str]:
    """
    Extract individual ad URLs from a Gumtree listing page.
    Accept:  URLs with /a- pattern (individual ads)
    Reject:  /s-user/, /s-my-gumtree/
    Dedupe via set, strip query params.
    """
    hrefs = page.css("a::attr(href)").getall()
    seen = set()
    links = []
    for href in hrefs:
        if not href:
            continue
        # Normalise to absolute URL
        if href.startswith("/"):
            href = GUMTREE_BASE + href
        href = href.split("?")[0]  # strip query params
        # Filter: only /a- pattern ad links
        if "/a-" not in href:
            continue
        if "/s-user/" in href or "/s-my-gumtree/" in href:
            continue
        if not href.startswith(GUMTREE_BASE):
            continue
        if any(cat in href for cat in _BLOCKED_CATEGORIES):
            continue
        # Block all job listing categories (catches *-jobs/ patterns generically)
        if "-jobs/" in href:
            continue
        if href not in seen:
            seen.add(href)
            links.append(href)
    return links


def extract_adid(page, url: str) -> str | None:
    """
    Try data-adid attribute first, fall back to last numeric URL segment.
    """
    # Try data-adid attribute
    adid_els = page.css("[data-adid]::attr(data-adid)").getall()
    if adid_els:
        return adid_els[0]
    # Fall back to last numeric segment of URL
    parts = [p for p in url.rstrip("/").split("/") if p]
    if parts and re.match(r"^\d+$", parts[-1]):
        return parts[-1]
    return None


def is_blocked(page) -> bool:
    """Check whether the page is a bot-block or Cloudflare shell."""
    try:
        body_text = page.body.decode("utf-8", errors="ignore") if isinstance(page.body, bytes) else str(page.body)
    except Exception:
        return True
    # Very short response = JS shell (curl-impersonate used to return 98 bytes)
    if len(body_text) < 500:
        return True
    for signal in BLOCK_SIGNALS:
        if signal in body_text:
            return True
    return False


def _extract_location_from_jsonld(body_text: str) -> str | None:
    """
    Parse JSON-LD Place schema embedded in page HTML.
    Gumtree encodes location as addressLocality + addressRegion.
    Returns e.g. "Cape Town" or "Johannesburg, Gauteng".
    """
    for m in re.finditer(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        body_text,
        re.DOTALL,
    ):
        try:
            data = json.loads(m.group(1))
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "Place":
                    addr = item.get("address", {})
                    locality = addr.get("addressLocality", "")
                    region = addr.get("addressRegion", "")
                    # "Other" is Gumtree's placeholder when locality is unknown
                    parts = [p for p in [locality, region] if p and p.lower() != "other"]
                    if parts:
                        return ", ".join(parts)
        except Exception:
            pass
    return None


def parse_ad_page(page, url: str) -> dict | None:
    """Extract lead fields from an individual Gumtree ad page."""
    if is_blocked(page):
        print(f"[gumtree] block page detected: {url}", file=sys.stderr)
        return None

    # Get raw body once — reused for JSON-LD, phone scan, etc.
    try:
        body_text = page.body.decode("utf-8", errors="ignore") if isinstance(page.body, bytes) else str(page.body)
    except Exception:
        body_text = ""

    # Title
    title = page.css("h1::text").get()
    if title:
        title = title.strip()

    # Description
    # Gumtree changed HTML structure in 2025/2026 — no more data-q attributes.
    # Try multiple selectors with *::text (captures nested <p>/<span> content).
    # Fall back to <meta name="description"> which is always present (truncated ~150 chars).
    description = None
    for sel in [
        '[data-q="ad-description"] *::text',
        ".description *::text",
        ".vip-ad-description *::text",
        ".ad-description *::text",
    ]:
        parts = page.css(sel).getall()
        if parts:
            description = " ".join(t.strip() for t in parts if t.strip())
            if description:
                break
    if not description:
        description = page.css('meta[name="description"]::attr(content)').get()
        if description:
            description = description.strip()

    # Location — JSON-LD Place schema is the most reliable source on current Gumtree
    location = _extract_location_from_jsonld(body_text)
    if not location:
        for sel in ['[data-q="ad-location"]::text', ".location::text"]:
            loc = page.css(sel).get()
            if loc and loc.strip() and loc.strip() != ",":
                location = loc.strip()
                break

    # Price
    price = None
    for sel in ['[data-q="ad-price"]::text', ".price::text"]:
        price = page.css(sel).get()
        if price and price.strip():
            price = price.strip()
            break

    # Phone
    # Priority: rendered tel: links (filtered) > data-phone > regex in description > body scan
    # NOTE: Gumtree injects its own numbers (+27756035177, 0870220222) into every page
    # via JS-rendered DOM elements. Skip these — they are not seller phones.
    phone = None
    for tel_href in page.css('a[href^="tel:"]::attr(href)').getall():
        candidate = re.sub(r"[\s\-]", "", tel_href.replace("tel:", "").strip())
        if candidate not in _GUMTREE_NUMBERS:
            phone = candidate
            if phone.startswith("0"):
                phone = "+27" + phone[1:]
            elif phone.startswith("27") and not phone.startswith("+"):
                phone = "+" + phone
            break
    if not phone:
        data_phone = page.css("[data-phone]::attr(data-phone)").get()
        if data_phone:
            phone = re.sub(r"[\s\-]", "", data_phone.strip())
    if not phone:
        phone = extract_phone(description)
    if not phone and body_text:
        # Seller phone is typically in description text at ~100K chars into the body.
        # Scan up to 200K to capture it; avoid the related-ads section (~120K+).
        phone = extract_phone(body_text[5000:200000])

    # AdID
    adid = extract_adid(page, url)

    return {
        "title": title,
        "description": description,
        "phone": phone,
        "location": location,
        "price": price,
        "adid": adid,
        "url": url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Main ──────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    today = datetime.now().strftime("%Y-%m-%d")
    default_out = str(
        Path(__file__).parent.parent / "memory" / f"gumtree-leads-{today}.json"
    )
    parser = argparse.ArgumentParser(
        description="Scrape Gumtree Wanted ads for vehicle trackers using Scrapling StealthyFetcher"
    )
    parser.add_argument("--max", type=int, default=15, dest="max_ads", help="Max ads to collect (default: 15)")
    parser.add_argument("--out", type=str, default=default_out, help="Output JSON file path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    max_ads: int = args.max_ads
    out_path: str = args.out

    print(f"[gumtree] Starting — max {max_ads} ads → {out_path}", file=sys.stderr)

    # Lazy import so the error message is helpful if scrapling isn't installed
    try:
        from scrapling.fetchers import StealthySession
    except ImportError:
        print(
            "[gumtree] ERROR: scrapling not installed.\n"
            "  Run: uv pip install 'scrapling[fetchers]>=0.4.2'\n"
            "  Then: uv run scrapling install",
            file=sys.stderr,
        )
        print(json.dumps({"ok": False, "error": "scrapling not installed"}))
        sys.exit(1)

    results: list[dict] = []
    seen_urls: set[str] = set()
    seen_adids: set[str] = set()

    try:
        with StealthySession(
            headless=True,
            solve_cloudflare=True,
            network_idle=True,
            block_webrtc=True,
            hide_canvas=True,
            timeout=90000,
            retries=3,
        ) as session:
            for search_url in SEARCH_URLS:
                if len(results) >= max_ads:
                    break

                print(f"[gumtree] Fetching listing: {search_url}", file=sys.stderr)

                try:
                    # Don't disable_resources on listing page — AJAX links need to load
                    listing_page = session.fetch(search_url, network_idle=True)
                except RuntimeError as e:
                    print(f"[gumtree] BLOCKED — Scrapling could not load listing page: {e}", file=sys.stderr)
                    continue

                if is_blocked(listing_page):
                    print(f"[gumtree] BLOCKED on listing page — Cloudflare not bypassed", file=sys.stderr)
                    continue

                ad_links = extract_ad_links(listing_page)
                print(f"[gumtree] Found {len(ad_links)} ad links", file=sys.stderr)

                if not ad_links:
                    print(f"[gumtree] Found 0 ad links on {search_url}", file=sys.stderr)
                    continue

                for ad_url in ad_links:
                    if len(results) >= max_ads:
                        break
                    if ad_url in seen_urls:
                        continue
                    seen_urls.add(ad_url)

                    # Polite delay: 800–2000ms jitter (mirrors gumtree_scraper.js)
                    time.sleep(0.8 + random.random() * 1.2)

                    print(f"[gumtree] Fetching ad: {ad_url}", file=sys.stderr)

                    try:
                        ad_page = session.fetch(
                            ad_url,
                            network_idle=True,
                            disable_resources=True,  # safe on individual ad pages
                        )
                    except RuntimeError as e:
                        print(f"[gumtree] fetch failed for {ad_url}: {e}", file=sys.stderr)
                        continue

                    ad = parse_ad_page(ad_page, ad_url)
                    if not ad:
                        continue

                    if ad["adid"] and ad["adid"] in seen_adids:
                        continue
                    if ad["adid"]:
                        seen_adids.add(ad["adid"])

                    results.append(ad)
                    print(
                        f"[gumtree] ✓ \"{ad['title']}\" | phone: {ad['phone'] or 'none'} | loc: {ad['location'] or '?'}",
                        file=sys.stderr,
                    )

    except RuntimeError as e:
        err = str(e)
        print(f"[gumtree] BLOCKED — Scrapling could not solve Cloudflare challenge: {err}", file=sys.stderr)
        print(f"[gumtree] Tip: if bigtorig IP is flagged, add a residential proxy via --proxy or env SCRAPLING_PROXY", file=sys.stderr)
        print(json.dumps({"ok": False, "error": err, "count": len(results), "leads": results}))
        sys.exit(1)

    # Write output file
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"[gumtree] Done — {len(results)} ads → {out_path}", file=sys.stderr)

    # Stdout: structured result for shell piping / b2c_run.py integration
    print(json.dumps({"ok": True, "count": len(results), "out": out_path, "leads": results}))


if __name__ == "__main__":
    main()
