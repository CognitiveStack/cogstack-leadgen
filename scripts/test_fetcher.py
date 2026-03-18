#!/usr/bin/env python3
"""Quick test: can Scrapling Fetcher (no Chromium) handle Gumtree?"""
import sys
import time
import re

from scrapling.fetchers import Fetcher

LISTING_URL = "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=need+car+tracker"

# --- Test 1: Listing page ---
print("[test] Fetching listing page...", file=sys.stderr)
t0 = time.time()
page = Fetcher.get(LISTING_URL, stealthy_headers=True, retries=2, timeout=30)
elapsed = time.time() - t0

body = page.body.decode("utf-8", errors="ignore") if isinstance(page.body, bytes) else str(page.body)
ad_links = [h for h in page.css("a::attr(href)").getall() if h and "/a-" in h]
print(f"[test] Listing: {len(body)} bytes, {len(ad_links)} /a- links, {elapsed:.1f}s", file=sys.stderr)

if len(body) < 500:
    print("[test] FAIL — got empty shell (bot blocked)", file=sys.stderr)
    print(body[:500], file=sys.stderr)
    sys.exit(1)

if not ad_links:
    print("[test] WARNING — page loaded but 0 ad links found", file=sys.stderr)
    for sig in ["Access Denied", "cf-challenge", "The request is blocked"]:
        if sig in body:
            print(f"[test] BLOCKED: found '{sig}'", file=sys.stderr)
            sys.exit(1)

# --- Test 2: Individual ad page ---
if ad_links:
    ad_url = ad_links[0]
    if ad_url.startswith("/"):
        ad_url = "https://www.gumtree.co.za" + ad_url
    print(f"\n[test] Fetching ad page: {ad_url}", file=sys.stderr)
    t0 = time.time()
    ad_page = Fetcher.get(ad_url, stealthy_headers=True, retries=2, timeout=30)
    elapsed2 = time.time() - t0

    ad_body = ad_page.body.decode("utf-8", errors="ignore") if isinstance(ad_page.body, bytes) else str(ad_page.body)
    title = ad_page.css("h1::text").get()
    phones = re.findall(r"(?:\+27|27|0)[6-8]\d[\s\-]?\d{3}[\s\-]?\d{4}", ad_body)
    print(f"[test] Ad: {len(ad_body)} bytes, title='{title}', phones={phones[:3]}, {elapsed2:.1f}s", file=sys.stderr)

print(f"\n[test] DONE — Fetcher works! No Chromium needed.", file=sys.stderr)
