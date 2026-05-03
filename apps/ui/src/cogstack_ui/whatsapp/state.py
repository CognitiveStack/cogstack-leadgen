from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from cogstack_ui.config import OUTREACH_STATE_PATH

logger = logging.getLogger(__name__)

_STATE_FILE = Path(OUTREACH_STATE_PATH)

# Guards concurrent writes within this process. Cross-process safety
# (UI + script running simultaneously) is not guaranteed — acceptable
# for Phase 1 where Claire is the sole user.
_write_lock = asyncio.Lock()


# ── Low-level helpers (mirror scripts/whatsapp_outreach.py) ──────────────────
#
# load_state / save_state / already_sent keep the same names and semantics as
# the script so the two code paths are easy to compare side-by-side.


def load_state() -> list[dict]:
    """Read outreach-state.json. Returns [] if the file doesn't exist or is corrupt."""
    if not _STATE_FILE.exists():
        return []
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.exception("Failed to read state file %s", _STATE_FILE)
        return []


def load_state_strict() -> list[dict]:
    """Read outreach-state.json. Returns [] if file doesn't exist (normal fresh state).
    Raises json.JSONDecodeError or OSError if the file exists but cannot be parsed.

    Use this in contexts where a corrupt/unreadable state file must be treated
    as a failure rather than silently treated as empty (e.g. bulk outreach
    eligibility, where a false empty means re-contacting already-sent phones).
    """
    if not _STATE_FILE.exists():
        return []
    return json.loads(_STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: list[dict]) -> None:
    """Write outreach-state.json, creating the parent directory if needed."""
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def already_sent(state: list[dict], phone: str) -> bool:
    """Return True if this normalised phone number has an entry in the state list."""
    return any(e.get("phone") == phone for e in state)


# ── UI-specific helpers ───────────────────────────────────────────────────────


def get_sent_record(state: list[dict], phone: str) -> dict | None:
    """Return the full state entry for a phone number, or None.

    Used to extract sent_at for "Already sent on {date}" display.
    """
    return next((e for e in state if e.get("phone") == phone), None)


async def append_and_save(
    *,
    phone: str,
    display_name: str,
    email: str | None,
    business: str,
    motivation: str,
    notion_page_id: str,
    sent_at: str,
    dry_run: bool = False,
) -> None:
    """Append a sent record to outreach-state.json under an asyncio lock.

    Record shape is identical to scripts/whatsapp_outreach.py so both
    the script and the UI share a single source of truth. The dry_run
    flag is stored for auditability but does not affect the idempotency
    check (already_sent treats dry-run and real sends the same way).
    """
    async with _write_lock:
        state = load_state()
        state.append({
            "phone": phone,
            "display_name": display_name,
            "email": email,
            "interest": business,
            "motivation": motivation,
            "notion_page_id": notion_page_id,
            "sent_at": sent_at,
            "status": "pending",
            "dry_run": dry_run,
        })
        save_state(state)
