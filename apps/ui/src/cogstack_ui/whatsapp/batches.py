from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from cogstack_ui.config import OUTREACH_STATE_PATH
from cogstack_ui.whatsapp.templates import MESSAGE_TEMPLATE

logger = logging.getLogger(__name__)

BATCHES_FILE = Path(OUTREACH_STATE_PATH).parent / "batches.json"

# Stable lock file whose inode never changes (unlike batches.json which is
# os.replace'd on every write). All read-modify-write operations acquire
# LOCK_EX on this file so that the lock survives the replace.
BATCHES_LOCK_FILE = BATCHES_FILE.parent / "batches.lock"


# ── Locking ───────────────────────────────────────────────────────────────────


@contextlib.contextmanager
def _batches_lock():
    """Exclusive advisory lock for any batches.json read-modify-write.

    Uses a stable side-file (batches.lock) whose inode never changes,
    so concurrent lockers always serialise against the same inode even
    after batches.json itself is atomically replaced.
    """
    BATCHES_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(BATCHES_LOCK_FILE, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


# ── Low-level I/O helpers ─────────────────────────────────────────────────────


def load_batches() -> list[dict]:
    """Read batches.json. Returns [] if the file doesn't exist or is corrupt.

    Read-only; no lock needed. Callers that need consistency must acquire
    _batches_lock() themselves before calling.
    """
    if not BATCHES_FILE.exists():
        return []
    try:
        return json.loads(BATCHES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.exception("Failed to read batches file %s", BATCHES_FILE)
        return []


def _atomic_write(batches: list[dict]) -> None:
    """Write batches list atomically: write to .tmp → fsync → os.replace.

    Caller must already hold _batches_lock().
    """
    BATCHES_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = BATCHES_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(batches, indent=2))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, BATCHES_FILE)


# ── Public write helpers ──────────────────────────────────────────────────────


def append_batch(entry: dict) -> None:
    """Append a batch entry to batches.json.

    Serialised via _batches_lock so concurrent route handlers don't
    lose each other's entries.
    """
    with _batches_lock():
        batches = load_batches()
        batches.append(entry)
        _atomic_write(batches)


def get_template_hash() -> str:
    """Return SHA-256 hex digest of MESSAGE_TEMPLATE for drift detection."""
    return hashlib.sha256(MESSAGE_TEMPLATE.encode()).hexdigest()


# ── Query helpers (read-only, no lock required) ───────────────────────────────


def get_batch(batch_id: str) -> dict | None:
    """Fetch a single batch by id. Returns None if not found."""
    return next(
        (b for b in load_batches() if b.get("batch_id") == batch_id),
        None,
    )


def aborted_batches() -> list[dict]:
    """All batches with status='aborted'.

    Used by the /prospects banner and /outreach/batches index.
    """
    return [b for b in load_batches() if b.get("status") == "aborted"]


# ── Locked read-modify-write helpers ─────────────────────────────────────────


def append_to_batch_list(batch_id: str, field: str, value) -> None:
    """Append a single value to a list field of a batch atomically.

    The whole read-modify-write happens inside _batches_lock so
    concurrent appends to the same field don't lose entries. This
    is the worker's primary mutation pattern — one phone appended
    to 'completed' / 'skipped' / 'failed' per send result.

    Raises ValueError if batch_id not found, or if the field exists
    and is not a list.
    """
    with _batches_lock():
        batches = load_batches()
        idx = next(
            (i for i, b in enumerate(batches) if b.get("batch_id") == batch_id),
            None,
        )
        if idx is None:
            raise ValueError(f"batch_id {batch_id!r} not found in batches.json")

        current = batches[idx].get(field, [])
        if not isinstance(current, list):
            raise ValueError(
                f"batch field {field!r} is {type(current).__name__}, expected list"
            )

        batches[idx][field] = [*current, value]
        _atomic_write(batches)


def update_batch(batch_id: str, **fields) -> None:
    """Atomic read-modify-write of a single batch entry by id.

    Raises ValueError if batch_id not found.
    Serialised via _batches_lock; data file written via tmp+fsync+os.replace.
    """
    with _batches_lock():
        batches = load_batches()
        idx = next(
            (i for i, b in enumerate(batches) if b.get("batch_id") == batch_id),
            None,
        )
        if idx is None:
            raise ValueError(f"batch_id {batch_id!r} not found in batches.json")
        batches[idx].update(fields)
        _atomic_write(batches)


def mark_running_as_aborted_on_startup(reason: str) -> int:
    """Find any batch with status='running' (orphaned by process restart),
    flip status to 'aborted', set abort_reason and completed_at to now.

    Returns count of batches flipped. Logs each one at WARNING.
    No-op (returns 0) if batches.json doesn't exist.
    """
    if not BATCHES_FILE.exists():
        return 0

    flipped = 0
    with _batches_lock():
        batches = load_batches()
        now = datetime.now(timezone.utc).isoformat()
        for b in batches:
            if b.get("status") == "running":
                b["status"] = "aborted"
                b["abort_reason"] = reason
                b["completed_at"] = now
                flipped += 1
                logger.warning(
                    "startup: aborted orphaned batch batch_id=%s reason=%r",
                    b.get("batch_id"),
                    reason,
                )
        if flipped:
            _atomic_write(batches)

    return flipped
