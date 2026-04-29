#!/usr/bin/env python3
# =============================================================
# whatsapp_responses.py — Claire WhatsApp Response Classifier
# Polls the Baileys /inbox, classifies Yes/No/Maybe replies,
# updates Claire-Prospects Notion records, and auto-submits
# Yes responses to the B2C webhook.
# =============================================================
# Usage:
#   uv run python scripts/whatsapp_responses.py
#   uv run python scripts/whatsapp_responses.py --dry-run
#   uv run python scripts/whatsapp_responses.py --whatsapp-url http://127.0.0.1:3456
# =============================================================

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

# ── Logging ──────────────────────────────────────────────────

log = logging.getLogger("whatsapp_responses")


def setup_logging() -> None:
    """Configure console + file logging."""
    log.setLevel(logging.DEBUG)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    log.addHandler(console)

    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    fh = logging.FileHandler(log_dir / f"whatsapp-responses-{today}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    log.addHandler(fh)


# ── Environment ──────────────────────────────────────────────

NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"

B2C_WEBHOOK_URL = os.environ.get("B2C_WEBHOOK_URL")
B2C_WEBHOOK_TOKEN = os.environ.get("B2C_WEBHOOK_TOKEN") or os.environ.get("WEBHOOK_TOKEN")
WHATSAPP_LOOKUP_URL = os.environ.get("WHATSAPP_LOOKUP_URL", "http://127.0.0.1:3456")

PROJECT_ROOT = Path(__file__).parent.parent
STATE_FILE = PROJECT_ROOT / "logs" / "outreach-state.json"
NOTION_CONFIG = PROJECT_ROOT / "notion_config.json"

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 15]
NO_REPLY_HOURS = 48

# ── Classification keyword lists ──────────────────────────────

YES_KEYWORDS = [
    "yes", "ja", "yep", "yeah", "ok", "okay", "sure", "please",
    "call me", "interested", "send quote", "sounds good", "let's go",
]
NO_KEYWORDS = [
    "no", "nee", "not interested", "stop", "don't", "do not", "remove",
    "unsubscribe", "leave me alone", "not looking",
]
MAYBE_KEYWORDS = [
    "maybe", "possibly", "perhaps", "not sure", "depends", "more info",
    "tell me more", "what is", "how much", "what does", "send more",
    "details please",
]


def classify_response(text: str) -> str:
    """Classify a response text as Yes / No / Maybe / Unclear."""
    lower = text.lower()
    for kw in YES_KEYWORDS:
        if kw in lower:
            return "Yes"
    for kw in NO_KEYWORDS:
        if kw in lower:
            return "No"
    for kw in MAYBE_KEYWORDS:
        if kw in lower:
            return "Maybe"
    return "Unclear"


# ── Phone normalisation ───────────────────────────────────────

def normalise_phone(raw: str) -> str | None:
    """Normalise any SA phone format to +27XXXXXXXXX."""
    phone = str(raw).strip().replace(" ", "").replace("-", "")
    if phone.startswith("+27"):
        return phone
    if phone.startswith("27") and len(phone) == 11:
        return f"+{phone}"
    if phone.startswith("0") and len(phone) == 10:
        return f"+27{phone[1:]}"
    # Baileys returns JID without + e.g. "27827712303"
    if re.match(r"^27[6-8]\d{8}$", phone):
        return f"+{phone}"
    return None


# ── State file helpers ────────────────────────────────────────

def load_state() -> list[dict]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return []


def save_state(state: list[dict]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Notion helpers ────────────────────────────────────────────

def notion_update_record(
    client: httpx.Client,
    page_id: str,
    classification: str,
    response_text: str,
    responded_at: str,
    submitted: bool = False,
) -> bool:
    """PATCH a Claire-Prospects Notion page with response data."""
    properties: dict = {
        "Response":        {"rich_text": [{"text": {"content": response_text[:2000]}}]},
        "Response Status": {"select": {"name": classification}},
        "Response At":     {"date": {"start": responded_at}},
    }
    if submitted:
        properties["Submitted to Pipeline"] = {"checkbox": True}

    resp = client.patch(f"{NOTION_BASE_URL}/pages/{page_id}", json={"properties": properties})
    if resp.status_code == 200:
        log.debug("Updated Notion page %s → %s", page_id, classification)
        return True
    log.error("Notion update failed %d: %s", resp.status_code, resp.text[:300])
    return False


# ── Webhook POST ──────────────────────────────────────────────

def post_to_webhook(lead: dict, batch_id: str) -> bool:
    """POST a single Yes lead to the B2C webhook. Returns True on success."""
    if not B2C_WEBHOOK_URL:
        log.error("B2C_WEBHOOK_URL not set in .env")
        return False
    if not B2C_WEBHOOK_TOKEN:
        log.error("B2C_WEBHOOK_TOKEN not set in .env")
        return False

    responded_at = lead.get("responded_at", datetime.now(timezone.utc).isoformat())
    interest = lead.get("interest", "")
    motivation = lead.get("motivation", "")
    name = lead.get("display_name", "there")
    phone = lead["phone"]
    email = lead.get("email")

    payload = {
        "batch_id": batch_id,
        "segment": "B2C",
        "leads": [{
            "full_name": name,
            "phone": phone,
            "email": email,
            "province": None,
            "city": None,
            "intent_signal": (
                f"Responded YES to WhatsApp outreach. "
                f"Business: {interest}. Motivation: {motivation}."
            ),
            "intent_source": "WhatsApp Outreach",
            "intent_source_url": f"https://wa.me/{phone.replace('+', '')}",
            "intent_date": responded_at[:10],
            "vehicle_make_model": None,
            "vehicle_year": None,
            "call_script_opener": (
                f"Hi {name}, you replied YES to our WhatsApp message about vehicle tracking — great! "
                f"We'd love to get you a quick quote. When is a good time to call?"
            ),
            "data_confidence": "High",
            "sources_used": "CarTrackSubmissions Excel + WhatsApp outreach (Phone 3)",
            "intent_strength": 9,
            "urgency_score": 8,
        }],
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
                return True
            if response.status_code >= 500:
                delay = RETRY_DELAYS[attempt]
                log.warning("Webhook 5xx, retrying in %ds", delay)
                time.sleep(delay)
                continue
            log.error("Webhook error %d: %s", response.status_code, response.text[:300])
            return False
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            delay = RETRY_DELAYS[attempt]
            log.warning("Webhook request failed: %s, retrying in %ds", e, delay)
            time.sleep(delay)

    log.error("Webhook POST failed after %d retries", MAX_RETRIES)
    return False


# ── CLI ───────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Classify WhatsApp responses and update Notion")
    p.add_argument("--dry-run", action="store_true", help="Classify but don't update Notion or POST to webhook")
    p.add_argument("--whatsapp-url", default=WHATSAPP_LOOKUP_URL, metavar="URL", help="Baileys service URL")
    return p.parse_args()


# ── Main ──────────────────────────────────────────────────────

def main():
    setup_logging()
    args = parse_args()

    # Load config
    if not NOTION_CONFIG.exists():
        log.error("notion_config.json not found")
        sys.exit(1)
    config = json.loads(NOTION_CONFIG.read_text())
    claire_db_id = config.get("claire_prospects_db_id")
    if not claire_db_id:
        log.error("claire_prospects_db_id missing from notion_config.json")
        sys.exit(1)

    if not NOTION_API_KEY:
        log.error("NOTION_API_KEY not set in .env")
        sys.exit(1)

    notion_headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }

    # Load state
    state = load_state()
    pending = {e["phone"]: e for e in state if e.get("status") == "pending"}
    log.info("Loaded %d pending leads", len(pending))

    # Fetch inbox — save raw before processing (crash safety)
    log.info("Fetching inbox from %s", args.whatsapp_url)
    try:
        resp = httpx.get(f"{args.whatsapp_url}/inbox", timeout=15.0)
        inbox = resp.json().get("messages", [])
    except Exception as e:
        log.error("Failed to fetch inbox: %s", e)
        sys.exit(1)

    log.info("Inbox: %d messages", len(inbox))

    # Save raw inbox for crash recovery
    if inbox:
        log_dir = PROJECT_ROOT / "logs"
        log_dir.mkdir(exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        raw_path = log_dir / f"inbox-raw-{today}.json"
        existing = json.loads(raw_path.read_text()) if raw_path.exists() else []
        existing.extend(inbox)
        raw_path.write_text(json.dumps(existing, indent=2))
        log.debug("Raw inbox saved to %s", raw_path)

    # Track per-phone to handle duplicate replies (only process first)
    already_processed: set[str] = set()

    counts = {"processed": 0, "yes": 0, "no": 0, "maybe": 0, "unclear": 0, "submitted": 0, "expired": 0}

    with httpx.Client(headers=notion_headers, timeout=30.0) as notion:

        # ── Process inbound messages ──────────────────────────
        for msg in inbox:
            raw_from = msg.get("phone") or msg.get("from", "")
            norm_phone = normalise_phone(raw_from)
            if not norm_phone:
                log.warning("Unrecognised sender: %r", raw_from)
                continue

            if norm_phone in already_processed:
                log.debug("Duplicate reply from %s — ignoring", norm_phone)
                continue

            lead = pending.get(norm_phone)
            if not lead:
                log.debug("Unknown sender %s — not in pending list", norm_phone)
                continue

            already_processed.add(norm_phone)
            text = msg.get("text", "")
            classification = classify_response(text)
            responded_at = msg.get("timestamp") or msg.get("ts") or datetime.now(timezone.utc).isoformat()

            log.info("%s replied: %r → %s", norm_phone, text[:60], classification)
            counts["processed"] += 1

            if classification == "Unclear":
                counts["unclear"] += 1
                log.info("Unclear response from %s — leaving pending", norm_phone)
                continue

            counts[classification.lower()] += 1

            submitted = False
            batch_id = f"outreach-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

            if classification == "Yes" and not args.dry_run:
                lead_with_ts = {**lead, "responded_at": responded_at}
                ok = post_to_webhook(lead_with_ts, batch_id)
                if ok:
                    submitted = True
                    counts["submitted"] += 1
                    log.info("✅ %s submitted to B2C webhook", norm_phone)
                else:
                    log.error("Webhook submission failed for %s", norm_phone)
            elif classification == "Yes" and args.dry_run:
                log.info("[DRY-RUN] Would submit %s to B2C webhook", norm_phone)

            if not args.dry_run:
                notion_update_record(
                    notion,
                    lead["notion_page_id"],
                    classification,
                    text,
                    responded_at,
                    submitted=submitted,
                )
                # Update state
                for entry in state:
                    if entry["phone"] == norm_phone:
                        entry["status"] = classification.lower()
                        entry["responded_at"] = responded_at
                        entry["response_text"] = text
                        break
                save_state(state)
            else:
                log.info("[DRY-RUN] Would update Notion %s → %s", lead["notion_page_id"], classification)

        # ── Expire 48h no-replies ─────────────────────────────
        cutoff = datetime.now(timezone.utc) - timedelta(hours=NO_REPLY_HOURS)
        for entry in state:
            if entry.get("status") != "pending":
                continue
            sent_at_str = entry.get("sent_at", "")
            try:
                sent_at = datetime.fromisoformat(sent_at_str)
                if sent_at.tzinfo is None:
                    sent_at = sent_at.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue

            if sent_at < cutoff:
                log.info("Expiring no-reply: %s (sent %s)", entry["phone"], sent_at_str)
                counts["expired"] += 1
                if not args.dry_run:
                    notion_update_record(
                        notion,
                        entry["notion_page_id"],
                        "No Reply",
                        "",
                        datetime.now(timezone.utc).isoformat(),
                    )
                    entry["status"] = "no_reply"
                    save_state(state)
                else:
                    log.info("[DRY-RUN] Would mark %s as No Reply", entry["phone"])

    print(json.dumps(counts))


if __name__ == "__main__":
    main()
