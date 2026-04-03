#!/usr/bin/env python3
# =============================================================
# b2c_healthcheck.py — B2C Pipeline Dependency Health Check
# Quick diagnostic to verify all external services are reachable
# before running the B2C pipeline.
# =============================================================
# Usage:
#   uv run python scripts/b2c_healthcheck.py
#   uv run python scripts/b2c_healthcheck.py --whatsapp-url http://127.0.0.1:3457
#
# Exit codes:
#   0 — all critical services healthy
#   1 — one or more critical services unavailable
# =============================================================

import argparse
import json
import os
import sys
from datetime import datetime

import httpx
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────

WHATSAPP_LOOKUP_URL = os.environ.get("WHATSAPP_LOOKUP_URL", "http://127.0.0.1:3456")
B2C_WEBHOOK_URL     = os.environ.get("B2C_WEBHOOK_URL")
B2C_WEBHOOK_TOKEN   = os.environ.get("B2C_WEBHOOK_TOKEN") or os.environ.get("WEBHOOK_TOKEN")
OPENROUTER_API_KEY  = os.environ.get("OPENROUTER_API_KEY")
NOTION_API_KEY      = os.environ.get("NOTION_API_KEY")
B2C_LEADS_DB_ID     = os.environ.get("B2C_LEADS_DB_ID")


# ── Check functions ───────────────────────────────────────────

def check_whatsapp(lookup_url: str) -> tuple[bool, str]:
    """Check the Baileys WhatsApp lookup service (port 3456 or 3457)."""
    try:
        resp = httpx.get(f"{lookup_url}/health", timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status", "unknown")
            connected = data.get("connected", False)
            contacts = data.get("contacts_cached", "?")
            if connected:
                return True, f"connected | {contacts} contacts cached | status={status}"
            return False, f"service up but WhatsApp disconnected | status={status}"
    except httpx.ConnectError:
        return False, f"connection refused at {lookup_url} (service not running?)"
    except httpx.TimeoutException:
        return False, f"timeout connecting to {lookup_url}"
    except Exception as e:
        return False, f"error: {e}"
    return False, "unexpected response"


def check_webhook() -> tuple[bool, str]:
    """Check the n8n B2C webhook is reachable (HEAD request)."""
    if not B2C_WEBHOOK_URL:
        return False, "B2C_WEBHOOK_URL not set in .env"
    if not B2C_WEBHOOK_TOKEN:
        return False, "B2C_WEBHOOK_TOKEN not set in .env"
    try:
        # Send an intentionally invalid payload — n8n will reject it,
        # but a 4xx response proves the webhook is alive and auth works.
        resp = httpx.post(
            B2C_WEBHOOK_URL,
            json={"ping": True},
            headers={"Authorization": f"Bearer {B2C_WEBHOOK_TOKEN}"},
            timeout=10.0,
        )
        if resp.status_code in (200, 400):
            return True, f"reachable (HTTP {resp.status_code})"
        if resp.status_code == 401:
            return False, f"authentication failed (401) — check B2C_WEBHOOK_TOKEN"
        if resp.status_code == 404:
            return False, f"webhook not found (404) — is n8n workflow active?"
        return True, f"reachable (HTTP {resp.status_code})"
    except httpx.ConnectError:
        return False, f"connection refused — is n8n running at {B2C_WEBHOOK_URL}?"
    except httpx.TimeoutException:
        return False, "timeout — n8n may be overloaded"
    except Exception as e:
        return False, f"error: {e}"


def check_openrouter() -> tuple[bool, str]:
    """Check the OpenRouter API key is valid."""
    if not OPENROUTER_API_KEY:
        return False, "OPENROUTER_API_KEY not set in .env"
    try:
        resp = httpx.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            models = resp.json().get("data", [])
            return True, f"authenticated | {len(models)} models available"
        if resp.status_code == 401:
            return False, "invalid API key (401)"
        return False, f"unexpected status {resp.status_code}"
    except httpx.TimeoutException:
        return False, "timeout reaching openrouter.ai"
    except Exception as e:
        return False, f"error: {e}"


def check_notion() -> tuple[bool, str]:
    """Check Notion API key and B2C Leads DB are accessible."""
    if not NOTION_API_KEY:
        return False, "NOTION_API_KEY not set in .env"
    if not B2C_LEADS_DB_ID:
        return False, "B2C_LEADS_DB_ID not set in .env"
    try:
        resp = httpx.get(
            f"https://api.notion.com/v1/databases/{B2C_LEADS_DB_ID}",
            headers={
                "Authorization": f"Bearer {NOTION_API_KEY}",
                "Notion-Version": "2022-06-28",
            },
            timeout=10.0,
        )
        if resp.status_code == 200:
            db = resp.json()
            title_parts = db.get("title", [])
            title = title_parts[0].get("plain_text", "?") if title_parts else "?"
            return True, f"accessible | DB: \"{title}\""
        if resp.status_code == 401:
            return False, "invalid NOTION_API_KEY (401)"
        if resp.status_code == 404:
            return False, "B2C Leads DB not found (404) — check B2C_LEADS_DB_ID"
        return False, f"unexpected status {resp.status_code}"
    except httpx.TimeoutException:
        return False, "timeout reaching api.notion.com"
    except Exception as e:
        return False, f"error: {e}"


# ── CLI ───────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="B2C pipeline health check — verifies all external dependencies"
    )
    parser.add_argument(
        "--whatsapp-url", type=str, default=None,
        help="Override WhatsApp lookup URL (default: from WHATSAPP_LOOKUP_URL env or http://127.0.0.1:3456)"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON (for scripting)"
    )
    return parser.parse_args()


# ── Main ──────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    wa_url = args.whatsapp_url or WHATSAPP_LOOKUP_URL

    checks = [
        # (label, fn, is_critical)
        ("WhatsApp Lookup",    lambda: check_whatsapp(wa_url), True),
        ("n8n B2C Webhook",   check_webhook,                   True),
        ("OpenRouter API",    check_openrouter,                 True),
        ("Notion B2C DB",     check_notion,                     True),
    ]

    results = []
    any_critical_failure = False

    if not args.json:
        print(f"\n{'=' * 60}")
        print(f"  B2C Pipeline Health Check — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  WhatsApp URL: {wa_url}")
        print(f"{'=' * 60}\n")

    for label, fn, critical in checks:
        ok, detail = fn()
        icon = "✅" if ok else ("❌" if critical else "⚠️")
        results.append({"check": label, "ok": ok, "detail": detail, "critical": critical})

        if not ok and critical:
            any_critical_failure = True

        if not args.json:
            print(f"  {icon}  {label}")
            print(f"       {detail}\n")

    if args.json:
        print(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "overall": "ok" if not any_critical_failure else "degraded",
            "checks": results,
        }, indent=2))
    else:
        print(f"{'=' * 60}")
        if any_critical_failure:
            print("  ❌  One or more critical services are UNAVAILABLE")
            print("      Fix the issues above before running b2c_run.py")
        else:
            print("  ✅  All critical services healthy — pipeline ready")
        print(f"{'=' * 60}\n")

    sys.exit(1 if any_critical_failure else 0)


if __name__ == "__main__":
    main()
