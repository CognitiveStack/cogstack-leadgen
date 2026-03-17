#!/usr/bin/env python3
"""
Quick diagnostic: dump Gumtree ad page HTML structure so we can fix CSS selectors.
Run on bigtorig: uv run python scripts/gumtree_html_debug.py

Fetches the 'iTrace' ad (known tracker-related) and prints:
  - All data-q attributes found
  - All elements likely containing description text
  - Raw HTML around title, description, location, phone
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from scrapling.fetchers import StealthySession
except ImportError:
    print("scrapling not installed — run: uv pip install 'scrapling[fetchers]>=0.4.2'")
    sys.exit(1)

# Use the iTrace ad — tracker-related, known to load successfully
AD_URL = "https://www.gumtree.co.za/a-electronics-it-services/other/itrace-cloud-based-automotive-gps-and-sars-logbook-tracker/10013522458531010861954709"


def main():
    print(f"Fetching: {AD_URL}\n")

    with StealthySession(
        headless=True,
        solve_cloudflare=True,
        network_idle=True,
        block_webrtc=True,
        hide_canvas=True,
        timeout=90000,
        retries=2,
    ) as session:
        page = session.fetch(AD_URL, network_idle=True, disable_resources=True)

    body = page.body.decode("utf-8", errors="ignore") if isinstance(page.body, bytes) else str(page.body)
    print(f"Body length: {len(body)} bytes\n")

    # ── 1. All data-q attributes ─────────────────────────────────
    print("=" * 60)
    print("data-q attributes found:")
    print("=" * 60)
    for m in re.finditer(r'data-q="([^"]+)"', body):
        print(f"  data-q=\"{m.group(1)}\"")

    # ── 2. data-q="ad-description" surrounding HTML ──────────────
    print("\n" + "=" * 60)
    print("HTML around data-q=\"ad-description\" (±500 chars):")
    print("=" * 60)
    idx = body.find('data-q="ad-description"')
    if idx == -1:
        print("  *** NOT FOUND ***")
    else:
        print(body[max(0, idx - 200):idx + 500])

    # ── 3. data-q="ad-location" surrounding HTML ─────────────────
    print("\n" + "=" * 60)
    print("HTML around data-q=\"ad-location\" (±300 chars):")
    print("=" * 60)
    idx = body.find('data-q="ad-location"')
    if idx == -1:
        print("  *** NOT FOUND ***")
    else:
        print(body[max(0, idx - 100):idx + 300])

    # ── 4. data-q="ad-price" ─────────────────────────────────────
    print("\n" + "=" * 60)
    print("HTML around data-q=\"ad-price\" (±300 chars):")
    print("=" * 60)
    idx = body.find('data-q="ad-price"')
    if idx == -1:
        print("  *** NOT FOUND ***")
    else:
        print(body[max(0, idx - 100):idx + 300])

    # ── 5. Tel links ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Tel: links in page:")
    print("=" * 60)
    for m in re.finditer(r'href="tel:[^"]+"', body):
        print(f"  {m.group(0)}")

    # ── 6. data-phone ─────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("data-phone attributes:")
    print("=" * 60)
    for m in re.finditer(r'data-phone="[^"]+"', body):
        print(f"  {m.group(0)}")

    # ── 7. Phone number pattern hits in first 5000 chars ─────────
    print("\n" + "=" * 60)
    print("SA phone numbers in first 5000 chars of body:")
    print("=" * 60)
    phone_re = re.compile(r"(?:\+27|27|0)[6-8]\d[\s\-]?\d{3}[\s\-]?\d{4}")
    for m in phone_re.finditer(body[:5000]):
        start = max(0, m.start() - 80)
        end = min(len(body), m.end() + 80)
        print(f"  MATCH: {m.group(0)!r}")
        print(f"  CONTEXT: ...{body[start:end]}...")
        print()

    # ── 8. Meta description tag ──────────────────────────────────
    print("\n" + "=" * 60)
    print("meta[name=\"description\"] content:")
    print("=" * 60)
    m = re.search(r'<meta name="description" content="([^"]+)"', body)
    if m:
        print(f"  {m.group(1)}")
    else:
        print("  *** NOT FOUND ***")

    # ── 9. JSON-LD structured data ───────────────────────────────
    print("\n" + "=" * 60)
    print("JSON-LD script blocks (schema.org data):")
    print("=" * 60)
    for m in re.finditer(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', body, re.DOTALL):
        print(m.group(1)[:800])
        print("---")

    # ── 10. Find +27756035177 anywhere in body ───────────────────
    print("\n" + "=" * 60)
    print("Search for +27756035177 in full body:")
    print("=" * 60)
    idx = body.find("27756035177")
    if idx == -1:
        print("  NOT FOUND in body")
    else:
        print(f"  Found at position {idx}")
        print(f"  Context: ...{body[max(0,idx-150):idx+150]}...")

    # ── 11. All SA phone numbers in full body (first 10 matches) ─
    print("\n" + "=" * 60)
    print("All SA phone numbers in full body (first 10 unique matches):")
    print("=" * 60)
    phone_re2 = re.compile(r"(?:\+27|27|0)[6-8]\d[\s\-]?\d{3}[\s\-]?\d{4}")
    seen_phones = {}
    for m in phone_re2.finditer(body):
        num = re.sub(r"[\s\-]", "", m.group(0))
        if num not in seen_phones:
            seen_phones[num] = m.start()
            ctx_start = max(0, m.start() - 100)
            ctx_end = min(len(body), m.end() + 100)
            print(f"  pos={m.start():7d}  {m.group(0)!r:25s}  → normalised: {num}")
            print(f"    context: ...{body[ctx_start:ctx_end]}...")
            print()
        if len(seen_phones) >= 10:
            break

    # ── 12. Body slice 5000-8000 ─────────────────────────────────
    print("\n" + "=" * 60)
    print("Body chars 5000–8000 (looking for content structure):")
    print("=" * 60)
    print(body[5000:8000])


if __name__ == "__main__":
    main()
