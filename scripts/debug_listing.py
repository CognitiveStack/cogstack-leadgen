#!/usr/bin/env python3
"""Debug: inspect Gumtree search results page to understand why 0 ad links found."""
import re
import sys

from scrapling.fetchers import StealthySession

url = "https://www.gumtree.co.za/s-all-the-ads/v1b0p1?q=car+tracker"
print(f"Fetching: {url}", file=sys.stderr)

with StealthySession(
    headless=True, solve_cloudflare=True, network_idle=True,
    block_webrtc=True, hide_canvas=True, timeout=90000, retries=2,
) as session:
    page = session.fetch(url, network_idle=True)

body = page.body.decode("utf-8", errors="ignore") if isinstance(page.body, bytes) else str(page.body)
print(f"Body length: {len(body)} bytes", file=sys.stderr)

# Check for /a- links in raw HTML
links = re.findall(r'href="(/a-[^"]*)"', body)
print(f"/a- links in raw HTML: {len(links)}", file=sys.stderr)
for link in links[:10]:
    print(f"  {link}", file=sys.stderr)

# Try Scrapling CSS selector approach
css_links = page.css("a::attr(href)").getall()
print(f"\nTotal <a> hrefs via CSS: {len(css_links)}", file=sys.stderr)
a_links = [h for h in css_links if h and "/a-" in h]
print(f"/a- hrefs via CSS: {len(a_links)}", file=sys.stderr)
for link in a_links[:10]:
    print(f"  {link}", file=sys.stderr)

# Check for common search result patterns
for pattern in ["result-card", "search-result", "listing", "ad-listing", "no results"]:
    count = body.lower().count(pattern)
    if count:
        print(f'Pattern "{pattern}" found {count} times', file=sys.stderr)

# Print first 2000 chars
print(f"\n{'=' * 60}", file=sys.stderr)
print("First 2000 chars of body:", file=sys.stderr)
print(body[:2000], file=sys.stderr)
