#!/usr/bin/env python3
"""
Scrapling / Gumtree bypass validation test
===========================================
Fetches ONE Gumtree listing page and ONE individual ad to verify that
Scrapling's StealthyFetcher bypasses Cloudflare's bot protection.

Run BEFORE a full scrape to confirm the bypass is working:
    uv run test_gumtree_scrapling.py

PASS: real listing HTML returned, ad links found, ad page parsed
FAIL: 98-byte JS shell, "The request is blocked", or 0 ad links found

This costs only ~2 browser page loads (no Notion writes).
"""

import sys
from pathlib import Path

# Make scripts/ importable from repo root
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

try:
    from gumtree_scrapling import (
        SEARCH_URLS,
        extract_ad_links,
        is_blocked,
        parse_ad_page,
    )
except ImportError as e:
    print(f"❌ Could not import gumtree_scrapling: {e}")
    sys.exit(1)

try:
    from scrapling.fetchers import StealthySession
except ImportError:
    print(
        "❌ scrapling not installed.\n"
        "   Run: uv pip install 'scrapling[fetchers]>=0.4.2'\n"
        "   Then: uv run scrapling install"
    )
    sys.exit(1)


TEST_URL = SEARCH_URLS[0]  # car-tracker wanted ads
PASS = True


def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print("─" * 60)


def main() -> None:
    global PASS

    print("=" * 60)
    print("  Gumtree Scrapling bypass test")
    print(f"  Target: {TEST_URL}")
    print("=" * 60)

    section("Step 1: Fetch listing page (Cloudflare challenge)")
    print(f"[test] Opening StealthySession (solve_cloudflare=True) ...")

    listing_page = None
    ad_links = []

    try:
        with StealthySession(
            headless=True,
            solve_cloudflare=True,
            network_idle=True,
            block_webrtc=True,
            hide_canvas=True,
            timeout=90000,
            retries=2,
        ) as session:

            listing_page = session.fetch(TEST_URL, network_idle=True)

            # ── Listing page diagnosis ──
            try:
                body_text = listing_page.body.decode("utf-8", errors="ignore") if isinstance(listing_page.body, bytes) else str(listing_page.body)
            except Exception:
                body_text = ""

            body_len = len(body_text)
            print(f"[test] Response body length: {body_len} bytes")
            print(f"[test] First 500 chars:\n{body_text[:500]}\n")

            if body_len < 500:
                print("❌ FAIL — body is too short (likely a JS shell, Cloudflare not bypassed)")
                PASS = False
            else:
                blocked = is_blocked(listing_page)
                if blocked:
                    print("❌ FAIL — block signal detected in page body")
                    PASS = False
                else:
                    print("✅ Listing page looks real (no block signals, body > 500 bytes)")

            section("Step 2: Extract ad links from listing page")
            ad_links = extract_ad_links(listing_page)
            print(f"[test] Ad links found: {len(ad_links)}")
            for link in ad_links[:5]:
                print(f"         {link}")
            if len(ad_links) > 5:
                print(f"         ... and {len(ad_links) - 5} more")

            if not ad_links:
                print("❌ FAIL — no ad links extracted (listings may not have rendered)")
                PASS = False
            else:
                print(f"✅ {len(ad_links)} ad links extracted")

            if ad_links:
                section("Step 3: Fetch first individual ad page")
                first_ad_url = ad_links[0]
                print(f"[test] Fetching: {first_ad_url}")

                ad_page = session.fetch(first_ad_url, network_idle=True, disable_resources=True)
                ad = parse_ad_page(ad_page, first_ad_url)

                if not ad:
                    print("❌ FAIL — ad page blocked or parse returned None")
                    PASS = False
                else:
                    print(f"\n[test] Parsed ad:")
                    print(f"  title:       {ad['title']}")
                    print(f"  description: {(ad['description'] or '')[:120]}...")
                    print(f"  phone:       {ad['phone'] or '(none found)'}")
                    print(f"  location:    {ad['location']}")
                    print(f"  price:       {ad['price']}")
                    print(f"  adid:        {ad['adid']}")
                    print(f"  url:         {ad['url']}")

                    if ad["phone"]:
                        print(f"\n✅ Phone number extracted: {ad['phone']} — Gumtree bypass WORKING")
                    else:
                        print(f"\n⚠️  Ad parsed but no phone found on this specific listing.")
                        print(f"    This may be normal for some ads — try a larger --max run.")

                    print(f"\n✅ Ad page parsed successfully")

    except RuntimeError as e:
        print(f"❌ FAIL — RuntimeError: {e}")
        print("   Scrapling could not bypass Cloudflare.")
        print("   If bigtorig IP is flagged at IP level, add a residential proxy.")
        PASS = False

    section("Result")
    if PASS:
        print("✅ PASS — Scrapling bypasses Gumtree's bot protection")
        print("   Ready to run full scrape:")
        print("   uv run python scripts/gumtree_scrapling.py --max 15")
    else:
        print("❌ FAIL — Scrapling did not bypass Gumtree's bot protection")
        print("   Next steps:")
        print("   1. Try headless=False to debug visually")
        print("   2. Add a residential proxy (proxy= arg)")
        print("   3. Consider ScraperAPI trial (5,000 free credits)")

    print()
    sys.exit(0 if PASS else 1)


if __name__ == "__main__":
    main()
