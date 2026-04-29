#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "httpx>=0.28.1",
#     "python-dotenv>=1.2.1",
# ]
# ///
# =============================================================
# submit.py — POST classified B2C leads to n8n webhook
# =============================================================
# Usage:
#   uv run scripts/submit.py                         # reads from stdin
#   uv run scripts/submit.py --input classified.json
#   uv run scripts/submit.py --dry-run               # prints payload, no POST
#   uv run scripts/submit.py --source gumtree        # sets batch_id source label
#
# Output: {"submitted": N, "batch_id": "BATCH-YYYY-MM-DD-GUMTREE-B2C"}
# =============================================================

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path.home() / ".hermes/.env")

# ── Logging ──────────────────────────────────────────────────

log = logging.getLogger("submit")


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

N8N_B2C_WEBHOOK_URL = os.environ.get("N8N_B2C_WEBHOOK_URL")
N8N_B2C_BEARER_TOKEN = os.environ.get("N8N_B2C_BEARER_TOKEN")

# ── Retry constants ──────────────────────────────────────────

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 15]


# ── Webhook POST ─────────────────────────────────────────────

def post_batch(envelope: dict) -> dict | None:
    """POST the B2C batch to the n8n webhook. Retry on 5xx, fail fast on 4xx."""
    if not N8N_B2C_WEBHOOK_URL:
        log.error("N8N_B2C_WEBHOOK_URL not set in ~/.hermes/.env")
        return None
    if not N8N_B2C_BEARER_TOKEN:
        log.error("N8N_B2C_BEARER_TOKEN not set in ~/.hermes/.env")
        return None

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {N8N_B2C_BEARER_TOKEN}",
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = httpx.post(N8N_B2C_WEBHOOK_URL, json=envelope, headers=headers, timeout=60.0)
            log.info("Webhook response: %d", resp.status_code)
            if resp.status_code == 200:
                try:
                    return resp.json()
                except Exception:
                    return {"status": "ok", "raw": resp.text[:200]}
            if resp.status_code >= 500:
                delay = RETRY_DELAYS[attempt]
                log.warning("Webhook server error %d, retrying in %ds (%d/%d)", resp.status_code, delay, attempt + 1, MAX_RETRIES)
                time.sleep(delay)
                continue
            # 4xx — don't retry
            log.error("Webhook error %d: %s", resp.status_code, resp.text[:500])
            return None
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            delay = RETRY_DELAYS[attempt]
            log.warning("Webhook request failed: %s, retrying in %ds (%d/%d)", e, delay, attempt + 1, MAX_RETRIES)
            if attempt < MAX_RETRIES - 1:
                time.sleep(delay)

    log.error("Webhook POST failed after %d retries", MAX_RETRIES)
    return None


# ── Main ──────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="POST classified B2C leads to n8n webhook"
    )
    parser.add_argument("--input", type=str, default=None, help="Input classified JSON file (default: stdin)")
    parser.add_argument("--dry-run", action="store_true", help="Print payload to stderr, no POST")
    parser.add_argument("--source", type=str, default="GUMTREE", help="Source label for batch_id (default: GUMTREE)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    log_dir = Path.home() / "vault/projects/cogstack-leadgen/logs"
    setup_logging(log_dir, "submit")

    # Load input
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

    source_label = args.source.upper()
    batch_id = f"BATCH-{datetime.now().strftime('%Y-%m-%d')}-{source_label}-B2C"
    envelope = {
        "batch_id": batch_id,
        "segment": "B2C",
        "leads": leads,
    }

    log.info("Batch: %s | %d leads", batch_id, len(leads))

    if args.dry_run:
        log.info("--dry-run: payload below (no POST)")
        print(json.dumps(envelope, indent=2, ensure_ascii=False), file=sys.stderr)
        result = {"submitted": len(leads), "batch_id": batch_id, "dry_run": True}
        print(json.dumps(result))
        return

    if not leads:
        log.info("No leads to submit — POSTing empty batch")

    webhook_result = post_batch(envelope)
    if webhook_result is not None:
        log.info("Webhook accepted: %s", json.dumps(webhook_result)[:200])
        result = {"submitted": len(leads), "batch_id": batch_id}
    else:
        log.error("Webhook POST failed")
        result = {"submitted": 0, "batch_id": batch_id, "error": "webhook POST failed"}
        print(json.dumps(result))
        sys.exit(1)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
