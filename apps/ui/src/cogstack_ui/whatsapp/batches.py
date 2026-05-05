from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from cogstack_ui.config import OUTREACH_STATE_PATH
from cogstack_ui.whatsapp.templates import MESSAGE_TEMPLATE

logger = logging.getLogger(__name__)

BATCHES_FILE = Path(OUTREACH_STATE_PATH).parent / "batches.json"


def load_batches() -> list[dict]:
    """Read batches.json. Returns [] if the file doesn't exist or is corrupt."""
    if not BATCHES_FILE.exists():
        return []
    try:
        return json.loads(BATCHES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.exception("Failed to read batches file %s", BATCHES_FILE)
        return []


def append_batch(entry: dict) -> None:
    """Append a batch entry to batches.json using an atomic tmp+replace write."""
    batches = load_batches()
    batches.append(entry)
    BATCHES_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = BATCHES_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(batches, indent=2), encoding="utf-8")
    tmp.replace(BATCHES_FILE)


def get_template_hash() -> str:
    """Return SHA-256 hex digest of MESSAGE_TEMPLATE for drift detection."""
    return hashlib.sha256(MESSAGE_TEMPLATE.encode()).hexdigest()
