#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "httpx>=0.28.1",
#     "python-dotenv>=1.2.1",
#     "scrapling[fetchers]>=0.4.2",
# ]
# ///
# =============================================================
# scrape.py — B2C scraper
# Gumtree: Scrapling/curl_cffi (bypasses bot detection, extracts phone from DOM)
# HelloPeter: Exa (finds review URLs) + Scrapling DynamicFetcher (renders each review page)
# =============================================================
# Usage:
#   uv run scripts/scrape.py gumtree
#   uv run scripts/scrape.py gumtree --max 30 --out /tmp/leads.json
#   uv run scripts/scrape.py hellopeter
#   uv run scripts/scrape.py hellopeter --max 20
#
# Output: JSON array to stdout (or --out file)
# Schema: { title, description, phone, location, price, adid, url, source,
#            competitor, pain_point, scraped_at }
# =============================================================

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
import os

load_dotenv(Path.home() / ".hermes/.env")

# ── Logging ──────────────────────────────────────────────────

log = logging.getLogger("scraper")


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


# ── Constants ────────────────────────────────────────────────

# NOTE: Gumtree /s-wanted-ads/ category was removed in 2025/2026 — redirects to /s-all-the-ads/.
# NOTE: Search results are JS-rendered but URLs appear in JSON-LD ItemList embedded in the page HTML.
# Strategy: keyword search, extract URLs from JSON-LD, fetch individual ad pages.
# Car listings often include seller phone + mention of tracker need → good identity-first leads.
SEARCH_URLS = [
    # ── Tracker need / installation ──────────────────────────────
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=need+car+tracker",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=tracker+required+insurance",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=insurance+requires+tracker",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=no+tracker+installed",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=tracker+installation+needed",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=need+tracker+installed",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=gps+tracker+needed",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=vehicle+tracker+needed",
    # ── Cars for sale with tracker mention (seller has phone) ────
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=car+tracker+contact",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=tracker+system+for+sale",
    # ── Immobiliser (adjacent high-intent security buyers) ───────
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=immobiliser+needed",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=immobiliser+install+wanted",
    # ── Competitor churn ─────────────────────────────────────────
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=cancel+cartrack",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=cartrack+contract+cancel",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=cancel+netstar+contract",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=cancel+tracker+subscription",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=mix+telematics+cancel",
    # ── Finance / bank tracker requirements (new car buyers) ─────
    # Banks (WesBank, MFC, Standard Bank) require trackers as loan conditions
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=wesbank+tracker+required",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=mfc+tracker+compulsory",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=car+finance+tracker+install",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=bank+requires+tracker",
    # ── Just-bought buyer intent ──────────────────────────────────
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=just+bought+car+need+tracker",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=new+car+tracker+install",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=bought+bakkie+need+tracker",
    # ── Stolen / insurance claim (high urgency) ──────────────────
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=car+stolen+no+tracker",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=vehicle+theft+need+tracker",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=hijacked+need+tracker",
    # ── Bakkie / truck specific (higher-value leads) ─────────────
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=bakkie+tracker+needed",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=hilux+tracker+install",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=truck+gps+tracker",
    # ── Geographic (Gauteng is highest-density market) ───────────
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=tracker+install+gauteng",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=tracker+installation+cape+town",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=gps+tracker+johannesburg",
    # ── Price / value seekers (open to switching) ────────────────
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=cheap+vehicle+tracker+south+africa",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=affordable+car+tracker",
    "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=vehicle+tracking+subscription+cheaper",
]

# HelloPeter — competitor complaint scraping (Tier 1 + Tier 2 signal)
HELLOPETER_TARGETS = [
    {"slug": "cartrack", "competitor": "Cartrack"},
    {"slug": "tracker-connect", "competitor": "Tracker Connect"},
    {"slug": "mix-telematics", "competitor": "MiX Telematics"},
    {"slug": "netstar", "competitor": "Netstar"},
    {"slug": "beame", "competitor": "Beame"},
]
HELLOPETER_BASE = "https://www.hellopeter.com"

# Gumtree URL path segments that NEVER contain useful leads.
# NOTE: /a-cars-bakkies/ is NOT blocked — car listings include seller phone + name,
# and descriptions often mention tracker needs (insurance requirement, no tracker installed).
_BLOCKED_CATEGORIES = [
    "/a-heavy-trucks-buses/",
    "/a-other-pets/",
    "/a-removals-storage/",
    "/a-property-",
    "/a-wearable-technology/",
    # Electronics / car accessories: seller ads only (businesses selling GPS units)
    "/a-electronics-it-services/",
    "/a-other-replacement-car-part/",
    "/a-car-interior-accessories/",
    "/a-accessories-styling/",
    "/a-auto-electrical-parts/",
    "/a-car-exterior-accessories/",
    "/a-auto-electrical/",
    "/a-cleaning-services/",
    "/a-car-parks-storage/",
    "/a-courses-training/",
    "/a-office-space-",
    "/a-industrial-properties-",
    "/a-solar-",
    "/a-recruitment-",
]

# Gumtree-owned numbers injected site-wide (not seller phones)
_GUMTREE_NUMBERS = {"+27756035177", "27756035177", "0870220222", "+27870220222"}

PHONE_RE = re.compile(r"(?:\+27|27|0)[6-8]\d[\s\-]?\d{3}[\s\-]?\d{4}")

GUMTREE_BASE = "https://www.gumtree.co.za"

# ── Retry constants ──────────────────────────────────────────
MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 15]

# ── Firecrawl (used only if EXA_API_KEY not set) ─────────────
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY")
FIRECRAWL_BASE = "https://api.firecrawl.dev/v1"

# ── Exa (for HelloPeter review URL discovery) ─────────────────
EXA_API_KEY = os.environ.get("EXA_API_KEY")
EXA_URL = "https://api.exa.ai/search"

# HelloPeter Exa queries — one per competitor, targeting complaint/churn reviews
HELLOPETER_EXA_QUERIES = [
    ("site:hellopeter.com/cartrack/reviews unhappy cancel complaint", "Cartrack"),
    ("site:hellopeter.com/tracker-connect/reviews unhappy cancel complaint", "Tracker Connect"),
    ("site:hellopeter.com/netstar/reviews unhappy complaint switch", "Netstar"),
    ("site:hellopeter.com/mix-telematics/reviews unhappy cancel complaint", "MiX Telematics"),
    ("site:hellopeter.com/beame/reviews unhappy cancel complaint", "Beame"),
]


# ── Helpers — copied from gumtree_scrapling.py ───────────────

def extract_phone(text: str | None) -> str | None:
    """Extract and normalise a SA phone number from text."""
    if not text:
        return None
    match = PHONE_RE.search(text)
    if not match:
        return None
    number = re.sub(r"[\s\-]", "", match.group(0))
    if number.startswith("0"):
        number = "+27" + number[1:]
    elif number.startswith("27") and not number.startswith("+"):
        number = "+" + number
    # Filter Gumtree's own numbers
    if number in _GUMTREE_NUMBERS:
        return None
    return number


def extract_ad_links_from_jsonld(body_text: str) -> list[str]:
    """
    Extract ad URLs from JSON-LD ItemList embedded in Gumtree search page HTML.
    Gumtree renders search results in a schema.org ItemList block — more reliable
    than parsing <a> tags (which only contain featured/boosted ads).
    """
    import json as _json
    urls = []
    for m in re.finditer(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        body_text,
        re.DOTALL,
    ):
        try:
            data = _json.loads(m.group(1))
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "ItemList":
                    for elem in item.get("itemListElement", []):
                        url = elem.get("url", "")
                        if url:
                            urls.append(url)
        except Exception:
            pass
    return urls


def _filter_ad_links(urls: list[str]) -> list[str]:
    """Filter a list of Gumtree ad URLs: strip query params, dedupe, apply blocklist."""
    seen = set()
    result = []
    for href in urls:
        if not href:
            continue
        if href.startswith("/"):
            href = GUMTREE_BASE + href
        href = href.split("?")[0]
        if "/a-" not in href:
            continue
        if "/s-user/" in href or "/s-my-gumtree/" in href:
            continue
        if not href.startswith(GUMTREE_BASE):
            continue
        if any(cat in href for cat in _BLOCKED_CATEGORIES):
            continue
        if "-jobs/" in href:
            continue
        if href not in seen:
            seen.add(href)
            result.append(href)
    return result


def url_hash(url: str) -> str:
    """Generate a stable 12-char dedup key from a URL."""
    return hashlib.md5(url.encode()).hexdigest()[:12]


def extract_adid(url: str) -> str | None:
    """Extract adid from URL — last numeric segment or /a-xxx/DIGITS pattern."""
    m = re.search(r"/a-[^/]+/(\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"/(\d{7,12})$", url)
    if m:
        return m.group(1)
    # Fall back to last segment if numeric
    parts = [p for p in url.rstrip("/").split("/") if p]
    if parts and re.match(r"^\d+$", parts[-1]):
        return parts[-1]
    return None


BLOCK_SIGNALS = ["The request is blocked", "Access Denied", "cf-challenge"]
# NOTE: "Someone beat you to it" is NOT in BLOCK_SIGNALS — Gumtree embeds this overlay HTML
# on every ad page as a hidden modal. It's only a real block if the body is < 5000 bytes
# (i.e., the overlay IS the entire page with no ad content behind it).


def _extract_location_from_jsonld(body_text: str) -> str | None:
    """Parse JSON-LD Place schema embedded in Gumtree page HTML."""
    import json as _json
    for m in re.finditer(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        body_text,
        re.DOTALL,
    ):
        try:
            data = _json.loads(m.group(1))
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "Place":
                    addr = item.get("address", {})
                    locality = addr.get("addressLocality", "")
                    region = addr.get("addressRegion", "")
                    parts = [p for p in [locality, region] if p and p.lower() != "other"]
                    if parts:
                        return ", ".join(parts)
        except Exception:
            pass
    return None


def is_blocked_page(body_text: str) -> bool:
    if len(body_text) < 500:
        return True
    if any(sig in body_text for sig in BLOCK_SIGNALS):
        return True
    # "Someone beat you to it" is only a real block when it IS the whole page (no real ad content)
    if "Someone beat you to it" in body_text and len(body_text) < 5000:
        return True
    return False


def parse_ad_page_scrapling(page, url: str) -> dict | None:
    """Extract lead fields from a Gumtree ad page using Scrapling CSS selectors."""
    try:
        body_text = page.body.decode("utf-8", errors="ignore") if isinstance(page.body, bytes) else str(page.body)
    except Exception:
        body_text = ""

    if is_blocked_page(body_text):
        log.debug("Block page detected: %s", url)
        return None

    # Title
    title = page.css("h1::text").get()
    if title:
        title = title.strip()

    # Description — try multiple selectors (car listings use .description-content)
    description = None
    for sel in [
        ".description-content::text",
        ".description-content *::text",
        '[data-q="ad-description"] *::text',
        ".description *::text",
        ".vip-ad-description *::text",
        ".ad-description *::text",
        "#revip-description .description-container *::text",
    ]:
        parts = page.css(sel).getall()
        if parts:
            description = " ".join(t.strip() for t in parts if t.strip())
            if description and len(description) > 20:
                break
    if not description:
        description = page.css('meta[name="description"]::attr(content)').get()
        if description:
            description = description.strip()

    # Poster name — shown in listing header on Gumtree
    poster_name = None
    for sel in [
        '[data-q="seller-name"]::text',
        ".seller-name::text",
        ".seller-details .name::text",
        '[data-q="advertiser-name"]::text',
    ]:
        name_val = page.css(sel).get()
        if name_val and name_val.strip():
            poster_name = name_val.strip()
            break
    # Fallback: look for "Ad posted by <Name>" pattern in body
    if not poster_name:
        m = re.search(r"(?i)(?:ad\s+)?posted\s+by\s*[:\-]?\s*([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)", body_text)
        if m:
            poster_name = m.group(1).strip()

    # Location — JSON-LD is most reliable
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
        p = page.css(sel).get()
        if p and p.strip():
            price = p.strip()
            break

    # Phone — priority: tel: links → data-phone attr → regex in description → body scan
    # Body scan is limited to 100KB and skips matches inside data-adid= (false positives).
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
        # Scan main ad content only (stop at 100KB to avoid related-ads sidebar adid false positives)
        body_section = body_text[5000:100000]
        for phone_match in PHONE_RE.finditer(body_section):
            start = phone_match.start()
            context_before = body_section[max(0, start - 20):start]
            # Skip if inside a data-adid attribute (digits from adid look like phone numbers)
            if 'data-adid="' in context_before or 'adid=' in context_before.lower():
                continue
            phone = extract_phone(phone_match.group(0))
            if phone:
                break

    # Filter Gumtree's own numbers
    if phone in _GUMTREE_NUMBERS:
        phone = None

    adid = extract_adid(url)

    return {
        "title": title,
        "description": description,
        "phone": phone,
        "location": location,
        "price": price,
        "adid": adid,
        "url": url,
        "source": "Gumtree",
        "competitor": None,
        "pain_point": None,
        "name": poster_name,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def parse_ad_markdown(markdown: str, url: str) -> dict:
    """Extract lead fields from Firecrawl markdown of an individual ad page."""
    lines = markdown.strip().splitlines()

    # Title: first non-empty H1 or first non-empty line
    title = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            break
        if stripped and not title:
            title = stripped

    # Description: concatenate non-heading, non-empty lines (skip first few nav lines)
    desc_lines = []
    in_desc = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            in_desc = True
            continue
        if in_desc and stripped:
            desc_lines.append(stripped)
            if len(" ".join(desc_lines)) > 2000:
                break
    description = " ".join(desc_lines[:50]) if desc_lines else markdown[:500]

    # Location — three strategies in priority order:
    # 1. Firecrawl markdown puts location on the line AFTER "Location:" as markdown links:
    #    "Location:"
    #    "[Other](url), [Cape Town](url)"
    # 2. "Location:" label with inline content on the same line (older format)
    # 3. URL path segment — Gumtree ad URLs: /a-category/city-slug/title/adid
    location = None

    # Strategy 1 & 2: find "Location:" line then extract from next line or same line
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.search(r"(?i)^location\s*:?\s*$", stripped):
            # Content is on the next non-empty line as markdown links
            for j in range(i + 1, min(i + 4, len(lines))):
                next_line = lines[j].strip()
                if not next_line:
                    continue
                # Extract all markdown link texts: [City](url)
                link_texts = re.findall(r"\[([^\]]+)\]\(https?://[^)]+\)", next_line)
                # Filter out "Other" (Gumtree placeholder) and keep real city/region names
                meaningful = [t for t in link_texts if t.lower() not in ("other", "all categories", "all ads")]
                if meaningful:
                    location = ", ".join(meaningful)
                break
            if location:
                break
        elif re.search(r"(?i)location\s*[:\|]", stripped):
            # Inline: "Location: Cape Town" or "Location | Cape Town"
            loc = re.sub(r"(?i)location\s*[:\|]\s*", "", stripped).strip()
            # Strip any markdown links, keep text
            loc = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", loc)
            loc = loc.strip(" ,")
            if loc and loc.lower() not in ("", "other"):
                location = loc
            break

    # Strategy 3: extract from URL path if still no location
    # Gumtree ad URL structure: /a-{category}/{city-slug}/{title}/{adid}
    # e.g. /a-all-the-ads/johannesburg/need-tracker/123
    if not location:
        url_parts = [p for p in url.replace("https://www.gumtree.co.za", "").split("/") if p]
        # url_parts[0] = "a-category", url_parts[1] = city-slug (if not numeric/title)
        if len(url_parts) >= 3:
            city_slug = url_parts[1]
            # Skip if it looks like a title (contains many words) or is "other"
            if city_slug.lower() not in ("other", "v1b0p1") and "-" in city_slug and len(city_slug) < 40:
                # Convert slug to title case: "cape-town" → "Cape Town"
                city_name = city_slug.replace("-", " ").title()
                # Sanity check: must look like a SA city name, not a category
                if not any(kw in city_slug for kw in ("electronics", "services", "cars", "property", "jobs", "bakkies", "trucks")):
                    location = city_name

    # Price — look for R digit pattern
    price = None
    price_m = re.search(r"R\s*[\d,]+", markdown)
    if price_m:
        price = price_m.group(0).replace(" ", "")

    # Phone — search description and full markdown
    phone = extract_phone(description)
    if not phone:
        phone = extract_phone(markdown)

    adid = extract_adid(url)

    return {
        "title": title,
        "description": description,
        "phone": phone,
        "location": location,
        "price": price,
        "adid": adid,
        "url": url,
        "source": "Gumtree",
        "competitor": None,
        "pain_point": None,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


# ── HelloPeter helpers ───────────────────────────────────────

def extract_review_links(links: list[str], slug: str) -> list[str]:
    """Filter a list of URLs to individual HelloPeter review detail links."""
    seen: set[str] = set()
    result: list[str] = []
    for href in links:
        if not href:
            continue
        if not href.startswith("http"):
            href = HELLOPETER_BASE + href
        # Must be a review detail page (not the listing page itself)
        if f"/{slug}/reviews/" not in href:
            continue
        # Strip query params for dedup
        href = href.split("?")[0]
        if href not in seen:
            seen.add(href)
            result.append(href)
    return result


def parse_hellopeter_markdown(markdown: str, url: str, competitor: str) -> dict:
    """Extract lead fields from a scraped HelloPeter review page."""
    lines = [l.strip() for l in markdown.splitlines() if l.strip()]

    # Title: first H1 or first heading-like line
    title = f"Complaint about {competitor}"
    for line in lines:
        if line.startswith("# "):
            candidate = line[2:].strip()
            if len(candidate) > 5:
                title = candidate
                break

    # Reviewer name — look for "by <Name>" or "Reviewed by" patterns
    reviewer_name = None
    name_patterns = [
        re.compile(r"(?i)(?:reviewed?\s+by|by|from)\s*[:\-]?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]\.?)?)", re.MULTILINE),
        re.compile(r"(?i)([A-Z][a-z]+\s+[A-Z]\.)\s+(?:from|in|at)\s+\w", re.MULTILINE),
    ]
    for pattern in name_patterns:
        m = pattern.search(markdown)
        if m:
            reviewer_name = m.group(1).strip()
            break

    # Location — look for "from <City>" pattern in review text
    location = None
    loc_m = re.search(r"(?i)\bfrom\s+([A-Z][a-zA-Z\s]{2,20})(?:\s*[,\.]|\s+\w)", markdown)
    if loc_m:
        candidate = loc_m.group(1).strip()
        # Only accept plausible SA city names (not common words)
        if candidate.lower() not in ("the", "a", "this", "that", "my", "your", "his", "her"):
            location = candidate

    # Description: extract review body (longer text block, skip nav/metadata)
    desc_lines = []
    for line in lines:
        if len(line) > 30 and not line.startswith("#") and not line.startswith("[") and not line.startswith("|"):
            desc_lines.append(line)
            if len(" ".join(desc_lines)) > 2000:
                break

    description = " ".join(desc_lines[:40]) if desc_lines else markdown[:500]
    pain_point = description[:500]

    return {
        "title": title,
        "description": description,
        "phone": None,
        "location": location,
        "price": None,
        "adid": url_hash(url),
        "url": url,
        "source": "HelloPeter",
        "competitor": competitor,
        "pain_point": pain_point,
        "reviewer_name": reviewer_name,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Firecrawl API calls ──────────────────────────────────────

def firecrawl_scrape_links(url: str, client: httpx.Client) -> list[str]:
    """Scrape a Gumtree listing page and return the links."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.post(
                f"{FIRECRAWL_BASE}/scrape",
                json={"url": url, "formats": ["links"]},
                timeout=60.0,
            )
            if resp.status_code == 402:
                log.error("Firecrawl credits exhausted (HTTP 402) — aborting")
                sys.exit(1)
            if resp.status_code >= 500:
                delay = RETRY_DELAYS[attempt]
                log.warning("Firecrawl server error %d, retry in %ds", resp.status_code, delay)
                time.sleep(delay)
                continue
            resp.raise_for_status()
            data = resp.json()
            if data.get("error") and "blocked" in str(data.get("error", "")).lower():
                log.error("Firecrawl returned blocked error: %s", data.get("error"))
                sys.exit(1)
            links = data.get("data", {}).get("links", [])
            return links
        except httpx.HTTPStatusError as e:
            log.warning("Firecrawl scrape failed: %s", e)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS[attempt])
        except httpx.HTTPError as e:
            log.warning("Firecrawl request error: %s, retry in %ds", e, RETRY_DELAYS[attempt])
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS[attempt])
    return []


def firecrawl_batch_scrape(urls: list[str], client: httpx.Client) -> list[dict]:
    """Batch-scrape ad pages via Firecrawl, poll until complete."""
    if not urls:
        return []

    # Submit batch
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.post(
                f"{FIRECRAWL_BASE}/batch/scrape",
                json={"urls": urls, "formats": ["markdown"]},
                timeout=60.0,
            )
            if resp.status_code == 402:
                log.error("Firecrawl credits exhausted (HTTP 402) — aborting")
                sys.exit(1)
            resp.raise_for_status()
            batch_data = resp.json()
            break
        except httpx.HTTPError as e:
            log.warning("Firecrawl batch submit failed: %s", e)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS[attempt])
            else:
                return []
    else:
        return []

    batch_id = batch_data.get("id")
    if not batch_id:
        log.error("Firecrawl batch response missing 'id': %s", batch_data)
        return []

    log.info("Firecrawl batch submitted: %s (%d URLs)", batch_id, len(urls))

    # Poll until complete
    poll_url = f"{FIRECRAWL_BASE}/batch/scrape/{batch_id}"
    max_polls = 60  # 60 × 5s = 5min max
    for poll in range(max_polls):
        time.sleep(5)
        try:
            resp = client.get(poll_url, timeout=30.0)
            resp.raise_for_status()
            poll_data = resp.json()
            status = poll_data.get("status")
            log.debug("Batch poll %d/%d: status=%s", poll + 1, max_polls, status)
            if status == "completed":
                return poll_data.get("data", [])
            if status in ("failed", "cancelled"):
                log.error("Firecrawl batch %s: %s", batch_id, status)
                return []
        except httpx.HTTPError as e:
            log.warning("Batch poll failed: %s", e)

    log.error("Firecrawl batch %s timed out after %ds", batch_id, max_polls * 5)
    return []


# ── Main ──────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape B2C leads via Firecrawl (Gumtree buyer-intent ads, HelloPeter complaints)"
    )
    parser.add_argument("source", choices=["gumtree", "hellopeter"], help="Source to scrape")
    parser.add_argument("--max", type=int, default=15, dest="max_ads", help="Max ads to collect (default: 15)")
    parser.add_argument("--out", type=str, default=None, help="Output JSON file path (default: stdout)")
    return parser.parse_args()


def run_gumtree(args: argparse.Namespace, _client: httpx.Client) -> list[dict]:
    """Scrapling-based Gumtree scraper (curl_cffi, bypasses bot detection).
    Phase 1: collect ad links from search pages.
    Phase 2: fetch each ad page, extract phone + name from DOM.
    Identity-first: logs phone hit rate for monitoring.
    """
    try:
        from scrapling.fetchers import Fetcher
    except ImportError:
        log.error("scrapling not installed — run: uv add 'scrapling[fetchers]>=0.4.2'")
        return []

    import random

    results: list[dict] = []
    seen_adids: set[str] = set()
    seen_urls: set[str] = set()
    all_ad_urls: list[str] = []

    # Phase 1: collect ad links from search pages
    for search_url in SEARCH_URLS:
        if len(all_ad_urls) >= args.max_ads * 4:
            break
        log.info("Fetching listing: %s", search_url)
        try:
            listing_page = Fetcher.get(search_url, stealthy_headers=True, retries=3, timeout=30)
        except Exception as e:
            log.warning("Listing fetch failed: %s", e)
            continue

        try:
            body_text = listing_page.body.decode("utf-8", errors="ignore") if isinstance(listing_page.body, bytes) else str(listing_page.body)
        except Exception:
            body_text = ""

        if is_blocked_page(body_text):
            log.warning("Blocked on listing page: %s", search_url)
            continue

        # Extract ad URLs from JSON-LD ItemList (search results are embedded there, not in <a> tags)
        jsonld_urls = extract_ad_links_from_jsonld(body_text)
        ad_links = _filter_ad_links(jsonld_urls)
        log.info("Found %d ad links from listing (JSON-LD)", len(ad_links))

        for link in ad_links:
            adid = extract_adid(link)
            if adid and adid in seen_adids:
                continue
            if link not in seen_urls:
                seen_urls.add(link)
                if adid:
                    seen_adids.add(adid)
                all_ad_urls.append(link)

    if not all_ad_urls:
        log.warning("No Gumtree ad links collected")
        return []

    to_fetch = all_ad_urls[:args.max_ads]
    log.info("Fetching %d Gumtree ad pages via Scrapling", len(to_fetch))

    # Phase 2: fetch each ad page individually with polite delay
    phones_found = 0
    for ad_url in to_fetch:
        time.sleep(0.5 + random.random() * 0.7)
        log.debug("Fetching ad: %s", ad_url)
        try:
            ad_page = Fetcher.get(ad_url, stealthy_headers=True, retries=3, timeout=30)
        except Exception as e:
            log.warning("Ad fetch failed for %s: %s", ad_url, e)
            continue

        lead = parse_ad_page_scrapling(ad_page, ad_url)
        if not lead:
            continue

        if lead.get("phone"):
            phones_found += 1

        results.append(lead)
        log.info(
            '✓ "%s" | phone: %s | name: %s | loc: %s',
            (lead.get("title") or "?")[:55],
            lead.get("phone") or "none",
            lead.get("name") or "?",
            lead.get("location") or "?",
        )

    log.info("Gumtree done — %d leads, %d with phone (%.0f%%)",
             len(results), phones_found,
             100 * phones_found / len(results) if results else 0)
    return results


def _exa_find_hellopeter_urls(client: httpx.Client, max_per_competitor: int = 6) -> list[tuple[str, str]]:
    """
    Use Exa to find recent HelloPeter review URLs for each competitor.
    Returns list of (url, competitor) tuples.
    HelloPeter's review listing page is a React SPA — Exa indexes the static review pages.
    """
    if not EXA_API_KEY:
        log.warning("EXA_API_KEY not set — cannot discover HelloPeter review URLs")
        return []

    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    for query, competitor in HELLOPETER_EXA_QUERIES:
        log.info("Exa: searching HelloPeter reviews for %s", competitor)
        try:
            resp = client.post(
                EXA_URL,
                headers={"x-api-key": EXA_API_KEY, "Content-Type": "application/json"},
                json={
                    "query": query,
                    "numResults": max_per_competitor,
                    "type": "neural",
                    "useAutoprompt": True,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            for r in resp.json().get("results", []):
                url = r.get("url", "")
                if url and "/reviews/" in url and url not in seen:
                    seen.add(url)
                    results.append((url, competitor))
                    log.debug("  Found: %s", url)
        except Exception as e:
            log.warning("Exa search failed for %s: %s", competitor, e)
        time.sleep(0.5)

    log.info("Exa found %d HelloPeter review URLs total", len(results))
    return results


def _parse_hellopeter_dynamic(url: str, competitor: str) -> dict | None:
    """
    Fetch a HelloPeter review page with DynamicFetcher (Playwright/Patchright)
    and extract reviewer name, review text, location.
    Individual review pages are React SPA — require JS execution.
    """
    try:
        from scrapling.fetchers import DynamicFetcher
    except ImportError:
        log.error("scrapling not installed")
        return None

    try:
        # network_idle=False + wait_for review content = much faster than network_idle=True
        # (network_idle waits for all analytics/ads to finish loading — ~40s per page)
        page = DynamicFetcher.fetch(
            url,
            headless=True,
            network_idle=False,
            wait_for='[itemprop="reviewBody"]',
            timeout=20000,
        )
    except Exception as e:
        log.warning("DynamicFetcher failed for %s: %s", url, e)
        return None

    body = page.body.decode("utf-8", errors="ignore") if isinstance(page.body, bytes) else str(page.body)
    if len(body) < 1000:
        log.debug("Thin page for %s — skipping", url)
        return None

    # Reviewer name — first [itemprop="name"] is the reviewer, others are the business/review title
    names = page.css('[itemprop="name"]::text').getall()
    reviewer_name = names[0].strip() if names else None

    # Review body
    review_parts = page.css('[itemprop="reviewBody"]::text').getall()
    description = " ".join(t.strip() for t in review_parts if t.strip()) if review_parts else None

    # Review title (h1)
    title = page.css("h1::text").get()
    if title:
        title = title.strip()

    # Location — HelloPeter doesn't always expose it; check meta or structured data
    location = None
    for sel in ['[itemprop="addressLocality"]::text', '[class*="location"]::text']:
        loc = page.css(sel).get()
        if loc and loc.strip():
            location = loc.strip()
            break

    # Pain point — infer from title keywords
    pain_point = None
    if title:
        t = title.lower()
        if any(k in t for k in ("cancel", "cancellation")):
            pain_point = "wants to cancel"
        elif any(k in t for k in ("switch", "alternative")):
            pain_point = "looking to switch"
        elif any(k in t for k in ("bad service", "poor service", "no service")):
            pain_point = "poor service"
        elif "stolen" in t or "hijack" in t:
            pain_point = "vehicle theft"

    log.info('✓ HelloPeter: %s | reviewer: %s | loc: %s', competitor, reviewer_name or "?", location or "?")

    return {
        "title": title or f"HelloPeter review — {competitor}",
        "description": description or "",
        "phone": None,  # HelloPeter never shows reviewer phones publicly
        "location": location,
        "price": None,
        "adid": re.sub(r"[^a-z0-9]", "", url.lower())[-16:],
        "url": url,
        "source": "HelloPeter",
        "competitor": competitor,
        "pain_point": pain_point,
        "reviewer_name": reviewer_name,
        "name": reviewer_name,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def run_hellopeter(args: argparse.Namespace, client: httpx.Client) -> list[dict]:
    """
    HelloPeter scraper — two phases:
    1. Exa discovers recent review URLs (listing page is JS-heavy, Exa indexes the static pages)
    2. DynamicFetcher (Playwright) renders each individual review page to extract name + text
    """
    # Phase 1: discover review URLs via Exa
    all_review_urls = _exa_find_hellopeter_urls(client, max_per_competitor=max(6, args.max_ads // 5))

    if not all_review_urls:
        log.warning("No HelloPeter review URLs found — EXA_API_KEY may be missing")
        return []

    to_fetch = all_review_urls[:args.max_ads]
    log.info("Fetching %d HelloPeter review pages via DynamicFetcher", len(to_fetch))

    # Phase 2: render and parse each review page
    results: list[dict] = []
    for url, competitor in to_fetch:
        lead = _parse_hellopeter_dynamic(url, competitor)
        if lead:
            results.append(lead)
        time.sleep(1.0)  # polite delay between Playwright fetches

    return results


def main() -> None:
    args = parse_args()

    log_dir = Path.home() / "vault/projects/cogstack-leadgen/logs"
    setup_logging(log_dir, "scraper")

    # Firecrawl is only needed for Gumtree (batch scrape); HelloPeter now uses Exa + DynamicFetcher
    if args.source == "gumtree" and not FIRECRAWL_API_KEY:
        log.warning("FIRECRAWL_API_KEY not set — Gumtree batch scrape may fail")

    headers = {}
    if FIRECRAWL_API_KEY:
        headers = {
            "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
            "Content-Type": "application/json",
        }

    with httpx.Client(headers=headers) as client:
        if args.source == "gumtree":
            results = run_gumtree(args, client)
        else:
            results = run_hellopeter(args, client)

    log.info("Done — %d leads", len(results))

    output = json.dumps(results, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(output, encoding="utf-8")
        log.info("Written to %s", args.out)
    else:
        print(output)


if __name__ == "__main__":
    main()
