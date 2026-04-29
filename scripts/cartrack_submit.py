#!/usr/bin/env python3
# =============================================================
# cartrack_submit.py — Submit Yes / No-Reply leads to Cartrack CRM
# Reads outreach-state.json, finds leads with status 'yes' or
# 'no_reply' (after 7 days), and POSTs them to the Cartrack
# JSON-RPC endpoint.
# =============================================================
# Usage:
#   uv run python scripts/cartrack_submit.py --dry-run   # preview, no POST
#   uv run python scripts/cartrack_submit.py             # live submit
#   uv run python scripts/cartrack_submit.py --yes-only  # skip no-reply
# =============================================================

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

# ── Logging ──────────────────────────────────────────────────

log = logging.getLogger("cartrack_submit")


def setup_logging() -> None:
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
    fh = logging.FileHandler(log_dir / f"cartrack-submit-{today}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    log.addHandler(fh)


# ── Constants ─────────────────────────────────────────────────

CARTRACK_URL = "https://ctcrm.cartrack.co.za/jsonrpc/crm_hook.php"
CARTRACK_TOKEN = "611d6f1a-04a1-42eb-889f-c3ff8a29bf45"
INSTANCE_UID = "793c83c2-f829-464c-ad82-a157cf85bf34"
CAMPAIGN_UID = "af7b2cbb-29a4-446b-b4fd-0199a060d9ad"
EXTERNAL_SYSTEM_UID = "B2C - 9PointPlanWA"
EXTERNAL_SOURCE_ID = "10001"

NO_REPLY_DAYS = 7  # submit no-reply leads after 7 days

PROJECT_ROOT = Path(__file__).parent.parent
STATE_FILE = PROJECT_ROOT / "logs" / "outreach-state.json"


# ── Phone format ──────────────────────────────────────────────

def to_local_phone(phone: str) -> str:
    """Convert +27XXXXXXXXX → 0XXXXXXXXX for Cartrack payload."""
    if phone.startswith("+27"):
        return "0" + phone[3:]
    return phone


# ── Payload builder ───────────────────────────────────────────

def build_payload(lead: dict) -> dict:
    """Build Cartrack CRM createLead payload from state entry."""
    name = lead.get("display_name", "").split()[0] or lead.get("display_name", "Unknown")
    phone = to_local_phone(lead["phone"])
    raw_email = lead.get("email") or ""
    email = "" if str(raw_email).lower() in ("n/a", "none", "null") else raw_email
    interest = lead.get("interest", "")
    motivation = lead.get("motivation", "")
    status = lead.get("status", "")
    responded_at = lead.get("responded_at", lead.get("sent_at", ""))
    response_text = lead.get("response_text", "")

    lead_in_date = datetime.now(timezone.utc).strftime("%-d-%B-%Y %H:%M:%S")

    if status == "yes":
        context = f"WhatsApp outreach YES response. Reply: '{response_text}'."
    else:
        context = "No reply after 7 days of WhatsApp outreach."

    remark = (
        f"Source: {interest} (outreach {responded_at[:10] if responded_at else 'unknown'}) "
        f"{context} Motivation: {motivation}."
    ).strip()

    return {
        "token": CARTRACK_TOKEN,
        "method": "createLead",
        "external_system_uid": EXTERNAL_SYSTEM_UID,
        "external_source_id": EXTERNAL_SOURCE_ID,
        "name": name,
        "phone": phone,
        "lead_in_date": lead_in_date,
        "instance_uid": INSTANCE_UID,
        "campaign_uid": CAMPAIGN_UID,
        "email": email,
        "remark_message": remark[:500],
        "meta": {
            "additional_partner_field1": "Suburb",
            "additional_partner_field2": "",
        },
    }


# ── HTTP submit ───────────────────────────────────────────────

def submit_lead(payload: dict) -> bool:
    """POST a single lead to Cartrack CRM. Returns True on success."""
    for attempt in range(3):
        try:
            resp = httpx.post(
                CARTRACK_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30.0,
            )
            log.debug("Cartrack response %d: %s", resp.status_code, resp.text[:200])
            if resp.status_code == 200:
                log.info("✅ Submitted %s (%s)", payload["name"], payload["phone"])
                return True
            if resp.status_code >= 500:
                time.sleep([2, 5, 15][attempt])
                continue
            log.error("Cartrack error %d: %s", resp.status_code, resp.text[:300])
            return False
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            log.warning("Request failed: %s, retrying...", e)
            time.sleep([2, 5, 15][attempt])
    log.error("Failed after 3 retries for %s", payload["phone"])
    return False


# ── State helpers ─────────────────────────────────────────────

def load_state() -> list[dict]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return []


def save_state(state: list[dict]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── CLI ───────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Submit Yes/No-Reply leads to Cartrack CRM")
    p.add_argument("--dry-run", action="store_true", help="Preview payloads, no POST")
    p.add_argument("--yes-only", action="store_true", help="Submit Yes responses only, skip no-reply")
    return p.parse_args()


# ── Main ──────────────────────────────────────────────────────

def main():
    setup_logging()
    args = parse_args()

    state = load_state()
    if not state:
        log.error("No state file found at %s", STATE_FILE)
        sys.exit(1)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=NO_REPLY_DAYS)

    to_submit = []
    for entry in state:
        if entry.get("cartrack_submitted"):
            continue

        status = entry.get("status", "")

        if status == "yes":
            to_submit.append(entry)

        elif status == "no_reply" and not args.yes_only:
            # Double-check 7-day cutoff
            sent_at_str = entry.get("sent_at", "")
            try:
                sent_at = datetime.fromisoformat(sent_at_str)
                if sent_at.tzinfo is None:
                    sent_at = sent_at.replace(tzinfo=timezone.utc)
                if sent_at < cutoff:
                    to_submit.append(entry)
            except (ValueError, TypeError):
                pass

    log.info("Found %d leads to submit (%d yes, %d no-reply)",
             len(to_submit),
             sum(1 for e in to_submit if e.get("status") == "yes"),
             sum(1 for e in to_submit if e.get("status") == "no_reply"))

    if not to_submit:
        log.info("Nothing to submit.")
        print(json.dumps({"ok": True, "submitted": 0}))
        return

    submitted, errors = 0, 0

    for entry in to_submit:
        payload = build_payload(entry)

        if args.dry_run:
            print(f"\n--- {entry.get('display_name')} ({entry['phone']}) [{entry.get('status')}] ---")
            print(json.dumps(payload, indent=2))
            submitted += 1
            continue

        ok = submit_lead(payload)
        if ok:
            entry["cartrack_submitted"] = True
            entry["cartrack_submitted_at"] = now.isoformat()
            save_state(state)
            submitted += 1
        else:
            errors += 1

        time.sleep(1)  # brief pause between submissions

    print(json.dumps({"ok": errors == 0, "submitted": submitted, "errors": errors, "dry_run": args.dry_run}))


if __name__ == "__main__":
    main()
