from __future__ import annotations

import asyncio
import fcntl
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Literal

from cogstack_ui import config
from cogstack_ui.baileys.client import BaileysClient
from cogstack_ui.whatsapp.batches import (
    append_to_batch_list,
    get_batch,
    get_template_hash,
    update_batch,
)
from cogstack_ui.whatsapp.state import already_sent, append_and_save, load_state
from cogstack_ui.whatsapp.templates import build_message

logger = logging.getLogger(__name__)

# Worker singleton lock — separate from batches.lock (which serialises
# batches.json writes). This lock prevents two workers from running
# concurrently. LOCK_NB → fail fast rather than queue.
_BATCH_LOCK_FILE = Path(config.OUTREACH_STATE_PATH).parent / "batch.lock"

# Substrings (case-insensitive) in SendResult.error that trigger
# HARD ABORT of the whole batch — Baileys session or auth failures.
# Permissive on purpose: false-positive aborts one batch and asks
# for manual review; missing a real disconnect silently fails the
# rest of the queue.
_ABORT_ERROR_PATTERNS: tuple[str, ...] = (
    "disconnect",
    "logged out",
    "not connected",
    "session",
    "unauthor",
    "auth fail",
    " 401",   # leading space prevents matching "401k" or addresses
    " 403",
)

# Substrings (case-insensitive) indicating rate-limiting — use longer retry
# backoff (30s) instead of the default 5s.
_RATE_LIMIT_PATTERNS: tuple[str, ...] = ("rate", "limit", "429")


# ── Result types ───────────────────────────────────────────────────────────────


@dataclass
class SendOutcome:
    kind: Literal["sent", "skip", "abort"]
    reason: str | None = None  # populated for skip/abort, None for sent


# ── Lock helpers ───────────────────────────────────────────────────────────────


def _try_acquire_batch_lock() -> IO | None:
    """Try to acquire the worker singleton lock (non-blocking).

    Returns an open file handle if the lock was acquired, or None if
    another worker already holds it. Caller must release via
    _release_batch_lock() when done.
    """
    _BATCH_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    fh = open(_BATCH_LOCK_FILE, "a+")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fh
    except (BlockingIOError, OSError):
        fh.close()
        return None


def _release_batch_lock(fh: IO) -> None:
    fcntl.flock(fh, fcntl.LOCK_UN)
    fh.close()


# ── Send classification + retry ────────────────────────────────────────────────


# TODO(Phase 1.5): split 'failed' bucket into 'failed_transient'
# (5xx-after-retry, connection) vs 'failed_permanent' (4xx — number
# unreachable, malformed, etc). Right now the reason string carries
# this info but the counters conflate the two.
def _classify_send_error(error: str | None) -> str:
    """Return one of: 'abort', '5xx', '4xx', 'connection', 'unknown'."""
    if not error:
        return "unknown"
    e = error.lower()
    if any(p in e for p in _ABORT_ERROR_PATTERNS):
        return "abort"
    if e.startswith("http 5"):
        return "5xx"
    if e.startswith("http 4"):
        return "4xx"
    if "timeout" in e or "connect" in e:
        return "connection"
    return "unknown"


async def _send_with_retry(
    client: BaileysClient,
    phone: str,
    message: str,
    batch_id: str,
) -> SendOutcome:
    """Send one message via Baileys with one retry on 5xx.

    Returns a SendOutcome with kind one of:
      'sent'  — delivered successfully
      'skip'  — transient failure; record in batch.failed and continue
      'abort' — session/auth failure; caller must abort the whole batch
    """
    result = await client.send(phone, message)
    if result.sent:
        return SendOutcome("sent")

    category = _classify_send_error(result.error)

    if category == "abort":
        return SendOutcome("abort", f"baileys session/auth: {result.error}")

    if category == "5xx":
        # Rate-limit signals get a longer backoff.
        e = (result.error or "").lower()
        retry_sleep = 30.0 if any(p in e for p in _RATE_LIMIT_PATTERNS) else 5.0
        logger.info(
            "batch=%s phase=send_retry phone=%s reason=%s sleep=%.0fs",
            batch_id, phone, result.error, retry_sleep,
        )
        await asyncio.sleep(retry_sleep)
        result = await client.send(phone, message)
        if result.sent:
            logger.info(
                "batch=%s phase=send_recovered phone=%s",
                batch_id, phone,
            )
            return SendOutcome("sent")
        category = _classify_send_error(result.error)
        if category == "abort":
            return SendOutcome("abort", f"baileys session/auth on retry: {result.error}")
        return SendOutcome("skip", f"failed after retry: {result.error}")

    # 4xx, connection, unknown — skip this phone, continue batch.
    return SendOutcome("skip", result.error or "unknown error")


# ── Public entry point ─────────────────────────────────────────────────────────


async def run_batch(batch_id: str) -> None:
    """Run a queued batch: send (or DRY_RUN log) one message per phone.

    Designed to be called via FastAPI BackgroundTasks. Wraps the entire
    execution in try/except so an unhandled exception marks the batch
    aborted and always releases the singleton lock.
    """
    # 1. Acquire worker singleton lock (non-blocking, runs in thread to avoid
    #    blocking the event loop on file open).
    lock_fh = await asyncio.to_thread(_try_acquire_batch_lock)

    if lock_fh is None:
        logger.warning(
            "batch=%s phase=lock result=busy — another batch already running",
            batch_id,
        )
        try:
            await asyncio.to_thread(
                update_batch, batch_id,
                status="aborted",
                abort_reason="another batch already running",
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception:
            logger.exception("batch=%s phase=lock failed to mark aborted", batch_id)
        return

    # Lock acquired — run under try/except to guarantee release.
    try:
        await _run_batch_locked(batch_id)
    except Exception as exc:
        logger.exception("batch=%s phase=unhandled result=abort", batch_id)
        try:
            await asyncio.to_thread(
                update_batch, batch_id,
                status="aborted",
                abort_reason=f"unhandled: {type(exc).__name__}",
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception:
            logger.exception(
                "batch=%s failed to mark aborted after unhandled exc", batch_id
            )
    finally:
        await asyncio.to_thread(_release_batch_lock, lock_fh)


# ── Inner execution (lock already held) ───────────────────────────────────────


async def _run_batch_locked(batch_id: str) -> None:
    """Execute the batch; caller has already acquired batch.lock."""

    # 2. Load batch, validate status.
    batch = await asyncio.to_thread(get_batch, batch_id)
    if batch is None:
        logger.error("batch=%s phase=load result=not_found", batch_id)
        return
    if batch.get("status") != "pending":
        logger.error(
            "batch=%s phase=load result=wrong_status status=%s",
            batch_id, batch.get("status"),
        )
        return

    # 3. Template hash — abort if MESSAGE_TEMPLATE has drifted since queueing.
    live_hash = get_template_hash()
    queued_hash = batch.get("template_hash", "")
    if live_hash != queued_hash:
        logger.error(
            "batch=%s phase=hash result=drift live=%.8s queued=%.8s",
            batch_id, live_hash, queued_hash,
        )
        await asyncio.to_thread(
            update_batch, batch_id,
            status="aborted",
            abort_reason="template drift",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        return

    # 4. Mark running.
    started_at = datetime.now(timezone.utc).isoformat()
    await asyncio.to_thread(
        update_batch, batch_id,
        status="running",
        started_at=started_at,
    )

    queued: list[dict] = batch.get("queued", [])
    logger.info(
        "batch=%s phase=start phones=%d dry_run=%s jitter=[%.1f,%.1f]s",
        batch_id, len(queued), config.DRY_RUN,
        config.OUTREACH_JITTER_MIN_S, config.OUTREACH_JITTER_MAX_S,
    )

    # 5. Per-phone loop — BaileysClient opened once for the whole batch.
    async with BaileysClient() as client:
        for item in queued:
            phone: str = item["phone"]
            name: str = item.get("name", "")
            business: str = item.get("business", "")

            # 5a. Re-load state (NOT strict — missing file is normal at batch start).
            state = load_state()

            # 5b. Mid-batch idempotency check.
            if already_sent(state, phone):
                logger.info(
                    "batch=%s phase=dedup result=skip phone=%s",
                    batch_id, phone,
                )
                await asyncio.to_thread(append_to_batch_list, batch_id, "skipped", phone)
                continue

            # 5c. Jitter — asyncio.sleep never blocks the event loop.
            jitter = random.uniform(
                config.OUTREACH_JITTER_MIN_S,
                config.OUTREACH_JITTER_MAX_S,
            )
            logger.debug(
                "batch=%s phase=jitter sleep=%.2fs phone=%s",
                batch_id, jitter, phone,
            )
            await asyncio.sleep(jitter)

            # 5d. Build message.
            message = build_message(name=name, expressed_interest=business)

            # 5e / 5f. DRY_RUN path or real send.
            if config.DRY_RUN:
                logger.info(
                    "[DRY_RUN] batch=%s phase=send result=dry_run phone=%s message=%r",
                    batch_id, phone, message,
                )
                sent_at = datetime.now(timezone.utc).isoformat()
                await append_and_save(
                    phone=phone,
                    display_name=name,
                    email=None,
                    business=business,
                    motivation="",
                    notion_page_id="",
                    sent_at=sent_at,
                    dry_run=True,
                )
                await asyncio.to_thread(append_to_batch_list, batch_id, "completed", phone)
                logger.info(
                    "batch=%s phase=recorded phone=%s dry_run=True",
                    batch_id, phone,
                )
            else:
                outcome = await _send_with_retry(client, phone, message, batch_id)

                if outcome.kind == "sent":
                    sent_at = datetime.now(timezone.utc).isoformat()
                    await append_and_save(
                        phone=phone,
                        display_name=name,
                        email=None,
                        business=business,
                        motivation="",
                        notion_page_id="",
                        sent_at=sent_at,
                        dry_run=False,
                    )
                    await asyncio.to_thread(append_to_batch_list, batch_id, "completed", phone)
                    logger.info(
                        "batch=%s phase=recorded phone=%s dry_run=False",
                        batch_id, phone,
                    )

                elif outcome.kind == "skip":
                    await asyncio.to_thread(append_to_batch_list, batch_id, "failed", phone)
                    logger.warning(
                        "batch=%s phase=send_failed phone=%s reason=%s",
                        batch_id, phone, outcome.reason,
                    )

                elif outcome.kind == "abort":
                    await asyncio.to_thread(
                        update_batch, batch_id,
                        status="aborted",
                        abort_reason=outcome.reason,
                        completed_at=datetime.now(timezone.utc).isoformat(),
                    )
                    logger.error(
                        "batch=%s phase=batch_aborted reason=%s",
                        batch_id, outcome.reason,
                    )
                    return  # exit _run_batch_locked — lock release in run_batch finally

    # 6. Mark done (only reached if loop completed without abort).
    completed_at = datetime.now(timezone.utc).isoformat()
    await asyncio.to_thread(
        update_batch, batch_id,
        status="done",
        completed_at=completed_at,
    )
    logger.info("batch=%s phase=done completed_at=%s", batch_id, completed_at)
