#!/usr/bin/env python3
# =============================================================
# whatsapp_outreach.py — Claire WhatsApp Outreach Sender
# Reads unsent leads from ClaireLeads/CarTrackSubmissions.xlsx,
# sends personalised WhatsApp messages via Phone 3 (Baileys),
# and creates records in the Claire-Prospects Notion database.
# =============================================================
# Usage:
#   uv run python scripts/whatsapp_outreach.py
#   uv run python scripts/whatsapp_outreach.py --dry-run
#   uv run python scripts/whatsapp_outreach.py --max 5
#   uv run python scripts/whatsapp_outreach.py --whatsapp-url http://127.0.0.1:3456
# =============================================================

import argparse
import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import openpyxl
from dotenv import load_dotenv

load_dotenv()

# ── Logging ──────────────────────────────────────────────────

log = logging.getLogger("whatsapp_outreach")


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
    fh = logging.FileHandler(log_dir / f"whatsapp-outreach-{today}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    log.addHandler(fh)


# ── Environment ──────────────────────────────────────────────

NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"

WHATSAPP_LOOKUP_URL = os.environ.get("WHATSAPP_LOOKUP_URL", "http://127.0.0.1:3456")

PROJECT_ROOT = Path(__file__).parent.parent
EXCEL_PATH = PROJECT_ROOT / "ClaireLeads" / "CarTrackSubmissions.xlsx"
STATE_FILE = PROJECT_ROOT / "logs" / "outreach-state.json"
NOTION_CONFIG = PROJECT_ROOT / "notion_config.json"

# ── Phone normalisation ───────────────────────────────────────

PHONE_RE = re.compile(r"(?:\+27|27|0)[6-8]\d[\s\-]?\d{3}[\s\-]?\d{4}")


def normalise_phone(raw) -> str | None:
    """Normalise any SA phone format to +27XXXXXXXXX.

    Handles openpyxl reading phone as integer (drops leading zero).
    """
    if raw is None:
        return None
    # Handle integer from openpyxl (e.g., 827712303 → "0827712303")
    if isinstance(raw, (int, float)):
        raw = str(int(raw)).zfill(10)
    phone = str(raw).strip().replace(" ", "").replace("-", "")
    if phone.startswith("+27"):
        return phone
    if phone.startswith("27") and len(phone) == 11:
        return f"+{phone}"
    if phone.startswith("0") and len(phone) == 10:
        return f"+27{phone[1:]}"
    log.warning("Unrecognised phone format: %r", raw)
    return None


# ── Message template ─────────────────────────────────────────

MESSAGE_TEMPLATE = """\
Hi {name}! 👋

{business_line}

We offer competitive vehicle GPS tracking from *R99/month*, installation included. \
Can we give you a free quote?

Reply *YES* to be called, *NO* if not interested, or *MAYBE* if you'd like more info first. 😊"""


def build_message(name: str, expressed_interest: str, motivation: str) -> str:
    """Compose outreach message from lead data."""
    interest = (expressed_interest or "").strip()
    if interest:
        business_line = f"Do you have vehicle tracking for your {interest.rstrip('.')}?"
    else:
        business_line = "Do you have vehicle tracking for your business vehicles?"
    return MESSAGE_TEMPLATE.format(name=name, business_line=business_line)


# ── WhatsApp helpers ─────────────────────────────────────────

def whatsapp_lookup(phone: str, lookup_url: str) -> str | None:
    """Look up WhatsApp profile name. Returns name or None."""
    for attempt in range(2):
        try:
            resp = httpx.post(
                f"{lookup_url}/lookup",
                json={"phone": phone},
                timeout=15.0,
            )
            data = resp.json()
            if data.get("exists") and data.get("name"):
                return data["name"]
            log.debug("WA lookup %s: exists=%s name=%s", phone, data.get("exists"), data.get("name"))
            return None
        except httpx.TimeoutException:
            if attempt == 0:
                log.debug("WA lookup timeout for %s, retrying in 3s...", phone)
                time.sleep(3)
                continue
            log.warning("WA lookup timeout for %s after retry", phone)
        except httpx.HTTPError as e:
            log.warning("WA lookup HTTP error for %s: %s", phone, e)
            break
    return None


def send_whatsapp(phone: str, message: str, lookup_url: str) -> bool:
    """Send a WhatsApp message via Baileys /send endpoint. Returns True on success."""
    try:
        resp = httpx.post(
            f"{lookup_url}/send",
            json={"phone": phone, "message": message},
            timeout=90.0,  # server adds 30–60s jitter before sending
        )
        data = resp.json()
        if data.get("sent"):
            log.info("Sent to %s", phone)
            return True
        log.warning("Send failed for %s: %s", phone, data.get("error", "unknown"))
        return False
    except httpx.HTTPError as e:
        log.warning("Send HTTP error for %s: %s", phone, e)
        return False


# ── Notion helpers ────────────────────────────────────────────

def notion_create_record(
    client: httpx.Client,
    db_id: str,
    display_name: str,
    phone: str,
    email: str | None,
    business: str,
    motivation: str,
    message: str,
) -> str | None:
    """Create a Claire-Prospects Notion page. Returns page_id or None."""
    now = datetime.now(timezone.utc).isoformat()
    properties: dict = {
        "Full Name":    {"title": [{"text": {"content": display_name}}]},
        "Phone":        {"phone_number": phone},
        "Business":     {"rich_text": [{"text": {"content": business[:2000]}}]},
        "Motivation":   {"rich_text": [{"text": {"content": motivation[:2000]}}]},
        "Outreach Message": {"rich_text": [{"text": {"content": message[:2000]}}]},
        "Outreach Sent At": {"date": {"start": now}},
        "Response Status":  {"select": {"name": "Pending"}},
        "Submitted to Pipeline": {"checkbox": False},
        "Date Added":   {"date": {"start": now}},
    }
    if email:
        properties["Email"] = {"email": email}

    payload = {
        "parent": {"database_id": db_id},
        "properties": properties,
    }

    resp = client.post(f"{NOTION_BASE_URL}/pages", json=payload)
    if resp.status_code == 200:
        page_id = resp.json()["id"]
        log.debug("Created Notion record %s for %s", page_id, phone)
        return page_id
    log.error("Notion create failed %d: %s", resp.status_code, resp.text[:300])
    return None


# ── State file helpers ────────────────────────────────────────

def load_state() -> list[dict]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return []


def save_state(state: list[dict]) -> None:
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def already_sent(state: list[dict], phone: str) -> bool:
    return any(e["phone"] == phone for e in state)


# ── Excel reader ──────────────────────────────────────────────

def _clean(val) -> str:
    return str(val).strip() if val else ""


def read_leads(excel_path: Path) -> list[dict]:
    """Read unsent leads from an Excel file.

    Auto-detects two formats by column count:
      Format A (16+ cols) — CarTrackSubmissions.xlsx:
        C=name, D=phone, E=email, F=interest, G=motivation, P=status
        Skip if status == 'sent'
      Format B (10 cols) — CarTrackSubmission2.xlsx:
        A=source/business, B=name, C=phone, D=email, E=interest, F=motivation, G=status
        Skip if status == 'sent' or 'sent'
    """
    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    ws = wb.active
    if ws is None:
        wb.close()
        return []

    leads = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue  # skip header
        row = list(row)
        if not any(row):
            continue

        # Auto-detect format by column count
        if len(row) >= 16:
            # Format A: CarTrackSubmissions.xlsx
            name     = _clean(row[2])
            phone    = row[3]
            email    = _clean(row[4])
            interest = _clean(row[5])
            motiv    = _clean(row[6])
            status   = _clean(row[15]).lower()
            business = name
        else:
            # Format B: CarTrackSubmission2.xlsx
            business = _clean(row[0])
            name     = _clean(row[1])
            phone    = row[2]
            email    = _clean(row[3])
            interest = ""  # generic placeholder — use business name instead
            motiv    = _clean(row[5])
            status   = _clean(row[6]).lower()

        if status in ("sent", ""):
            continue

        norm_phone = normalise_phone(phone)
        if not norm_phone:
            log.warning("Row %d: unparseable phone %r — skipped", i + 1, phone)
            continue

        leads.append({
            "name": name or business or "there",
            "business": business,
            "phone": norm_phone,
            "email": email if email.lower() not in ("none", "n/a", "") else None,
            "interest": interest,
            "motivation": motiv,
        })

    wb.close()
    return leads


# ── CLI ───────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Send WhatsApp outreach messages to unsent leads")
    p.add_argument("--dry-run", action="store_true", help="Print composed messages, no sends or Notion writes")
    p.add_argument("--max", type=int, default=None, metavar="N", help="Process at most N leads")
    p.add_argument("--whatsapp-url", default=WHATSAPP_LOOKUP_URL, metavar="URL", help="Baileys service URL")
    p.add_argument("--file", type=Path, default=EXCEL_PATH, metavar="PATH", help="Excel file to read leads from")
    return p.parse_args()


# ── Main ──────────────────────────────────────────────────────

def main():
    setup_logging()
    args = parse_args()

    # Load config
    if not NOTION_CONFIG.exists():
        log.error("notion_config.json not found. Run create_claire_prospects_db.py first.")
        sys.exit(1)
    config = json.loads(NOTION_CONFIG.read_text())
    claire_db_id = config.get("claire_prospects_db_id")
    if not claire_db_id:
        log.error("claire_prospects_db_id missing from notion_config.json. Run create_claire_prospects_db.py first.")
        sys.exit(1)

    if not NOTION_API_KEY:
        log.error("NOTION_API_KEY not set in .env")
        sys.exit(1)

    notion_headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }

    # Read Excel
    excel_path = args.file
    if not excel_path.exists():
        log.error("Excel file not found: %s", excel_path)
        sys.exit(1)

    log.info("Reading leads from %s", excel_path)
    leads = read_leads(excel_path)
    log.info("Found %d unsent leads", len(leads))

    # Load state (skip already-sent numbers)
    state = load_state()
    sent_count = 0
    skipped_count = 0
    error_count = 0

    if args.dry_run:
        log.info("DRY-RUN mode — no sends or Notion writes")

    with httpx.Client(headers=notion_headers, timeout=30.0) as notion:
        for lead in leads:
            if args.max is not None and sent_count >= args.max:
                break

            phone = lead["phone"]

            # Skip if already in state file (idempotency)
            if already_sent(state, phone):
                log.debug("Already sent to %s — skipping", phone)
                skipped_count += 1
                continue

            # WhatsApp name lookup
            wa_name = whatsapp_lookup(phone, args.whatsapp_url)
            display_name = wa_name or lead["name"] or "there"

            # Build message
            message = build_message(display_name, lead["interest"], lead["motivation"])

            if args.dry_run:
                print(f"\n--- {display_name} ({phone}) ---")
                print(message)
                sent_count += 1
                continue

            # Send message
            ok = send_whatsapp(phone, message, args.whatsapp_url)
            if not ok:
                log.warning("Message not sent to %s — skipping Notion record", phone)
                error_count += 1
                continue

            # Create Notion record — use business name as context if interest is generic
            notion_business = lead.get("business") or lead["interest"]
            page_id = notion_create_record(
                notion, claire_db_id,
                display_name, phone,
                lead["email"], notion_business, lead["motivation"],
                message,
            )
            if not page_id:
                log.error("Notion record creation failed for %s", phone)
                error_count += 1
                continue

            # Append to state file
            state.append({
                "phone": phone,
                "display_name": display_name,
                "email": lead["email"],
                "interest": notion_business,
                "motivation": lead["motivation"],
                "notion_page_id": page_id,
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "status": "pending",
            })
            save_state(state)
            sent_count += 1
            log.info("✅ %s (%s) — Notion: %s", display_name, phone, page_id)

            # Rate limit: 3–5s jitter between sends
            time.sleep(3 + random.random() * 2)

    summary = {
        "ok": error_count == 0,
        "sent": sent_count,
        "skipped": skipped_count,
        "errors": error_count,
        "dry_run": args.dry_run,
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
