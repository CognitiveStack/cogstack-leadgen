#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "httpx>=0.28.1",
#     "python-dotenv>=1.2.1",
# ]
# ///
# =============================================================
# enrich.py — Exa phone lookup for "Pending Enrichment" leads
# =============================================================
# Reads classified leads JSON from stdin (or --input file).
# For each lead with status="Pending Enrichment", fires an Exa
# search to find a phone number for the named individual.
# Upgrades matched leads to status="Pending QA".
# Outputs all leads (both buckets) to stdout for submit.py.
#
# Usage:
#   uv run scripts/enrich.py                   # stdin → stdout
#   uv run scripts/enrich.py --input leads.json
#   uv run scripts/enrich.py --dry-run         # log matches, no mutation
# =============================================================

import argparse
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

log = logging.getLogger("enricher")


def setup_logging(log_dir: Path) -> None:
    log.setLevel(logging.DEBUG)
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("[%(name)s] %(levelname)s: %(message)s"))
    log.addHandler(console)
    log_dir.mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    fh = logging.FileHandler(log_dir / f"enricher-{today}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    log.addHandler(fh)


# ── Credentials ──────────────────────────────────────────────

EXA_API_KEY = os.environ.get("EXA_API_KEY")
EXA_URL = "https://api.exa.ai/search"

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 15]

# SA phone regex — E.164 and local formats
PHONE_RE = re.compile(
    r"(?:\+27|0027|0)[\s\-]?(?:6[0-9]|7[0-9]|8[0-9])[\s\-]?\d{3}[\s\-]?\d{4}"
)


def normalise_phone(raw: str) -> str | None:
    digits = re.sub(r"[\s\-]", "", raw)
    if digits.startswith("0027"):
        digits = "+" + digits[2:]
    elif digits.startswith("0"):
        digits = "+27" + digits[1:]
    elif digits.startswith("27") and not digits.startswith("+"):
        digits = "+" + digits
    if re.fullmatch(r"\+27\d{9}", digits):
        return digits
    return None


def build_exa_query(lead: dict) -> str:
    """Build a MAX-context Exa query to surface a phone for a named individual."""
    full_name = lead.get("full_name", "")
    # Use first + last word of name (avoids middle initials messing up the query)
    parts = full_name.split()
    first_name = parts[0] if parts else full_name
    last_name = parts[-1] if len(parts) > 1 else ""

    competitor = lead.get("competitor") or ""
    pain_point = lead.get("pain_point") or ""
    # Pull a short detail from intent_signal as context anchor
    intent = lead.get("intent_signal") or ""
    detail = " ".join(intent.split()[:10])  # first 10 words

    parts_q = [f'"{first_name}"']
    if last_name and last_name != first_name:
        parts_q.append(f'"{last_name}"')
    if competitor:
        parts_q.append(f'"{competitor}"')
    if detail:
        parts_q.append(f'"{detail}"')
    parts_q.append("South Africa phone contact")

    return " ".join(parts_q)


def exa_search_phone(query: str, client: httpx.Client) -> str | None:
    """Run Exa search and extract the first SA phone number found in results."""
    if not EXA_API_KEY:
        log.warning("EXA_API_KEY not set — skipping enrichment")
        return None

    payload = {
        "query": query,
        "numResults": 5,
        "type": "neural",
        "useAutoprompt": True,
        "contents": {"text": True},
    }
    headers = {"x-api-key": EXA_API_KEY, "Content-Type": "application/json"}

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.post(EXA_URL, json=payload, headers=headers, timeout=30.0)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", RETRY_DELAYS[attempt]))
                log.warning("Exa rate limit, retry in %ds", wait)
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                time.sleep(RETRY_DELAYS[attempt])
                continue
            resp.raise_for_status()
            results = resp.json().get("results", [])
            for result in results:
                text = result.get("text", "") or ""
                for m in PHONE_RE.finditer(text):
                    phone = normalise_phone(m.group(0))
                    if phone:
                        log.debug("Phone found in result: %s (url: %s)", phone, result.get("url", "")[:80])
                        return phone
            return None
        except httpx.HTTPError as e:
            log.warning("Exa request failed: %s", e)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS[attempt])

    return None


# ── Main ──────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exa phone enrichment for Pending Enrichment leads")
    parser.add_argument("--input", type=str, default=None, help="Input JSON file (default: stdin)")
    parser.add_argument("--dry-run", action="store_true", help="Log matches but don't mutate leads")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    log_dir = Path.home() / "vault/projects/cogstack-leadgen/logs"
    setup_logging(log_dir)

    if args.input:
        with open(args.input, encoding="utf-8") as f:
            leads = json.load(f)
    else:
        try:
            leads = json.load(sys.stdin)
        except json.JSONDecodeError as e:
            log.error("Failed to parse stdin as JSON: %s", e)
            sys.exit(1)

    if not isinstance(leads, list):
        log.error("Expected JSON array, got %s", type(leads).__name__)
        sys.exit(1)

    pending = [l for l in leads if l.get("status") == "Pending Enrichment"]
    log.info("Leads in: %d | Pending Enrichment: %d", len(leads), len(pending))

    if not pending:
        log.info("Nothing to enrich — passing through unchanged")
        print(json.dumps(leads, indent=2, ensure_ascii=False))
        return

    if not EXA_API_KEY:
        log.warning("EXA_API_KEY not set — skipping enrichment, passing leads through as-is")
        print(json.dumps(leads, indent=2, ensure_ascii=False))
        return

    enriched = 0
    with httpx.Client() as client:
        for lead in pending:
            query = build_exa_query(lead)
            log.info('Enriching "%s" → %s', lead.get("full_name", "?"), query[:120])
            time.sleep(0.5)  # polite delay

            phone = exa_search_phone(query, client)
            if phone:
                log.info("  ✓ Found phone: %s", phone)
                enriched += 1
                if not args.dry_run:
                    lead["phone"] = phone
                    lead["status"] = "Pending QA"
                    lead["data_confidence"] = "Medium"  # enriched, not directly scraped
                    lead["sources_used"] = lead.get("sources_used", "") + " + Exa enrichment"
            else:
                log.info("  ✗ No phone found — keeping Pending Enrichment")

    log.info("Enrichment done — %d/%d leads upgraded to Pending QA", enriched, len(pending))
    print(json.dumps(leads, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
