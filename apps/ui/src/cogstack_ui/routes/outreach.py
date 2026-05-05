from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from cogstack_ui import config
from cogstack_ui.baileys.client import BaileysClient
from cogstack_ui.notion.client import NotionClient
from cogstack_ui.notion.queries import get_prospect_detail
from cogstack_ui.notion.writes import (
    create_claire_prospect,
    mark_submitted_to_pipeline,
    update_status,
)
from cogstack_ui.utils.phone import normalise_phone
from cogstack_ui.whatsapp.batches import append_batch, get_template_hash
from cogstack_ui.whatsapp.eligibility import is_eligible
from cogstack_ui.whatsapp.state import (
    append_and_save,
    get_sent_record,
    load_state,
    load_state_strict,
)
from cogstack_ui.whatsapp.templates import build_message

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(
    directory=Path(__file__).parent.parent / "templates"
)

_P = "prospects/partials"


# ── WhatsApp Lookup ───────────────────────────────────────────────────────────


@router.post("/prospects/{page_id}/whatsapp-lookup")
async def whatsapp_lookup(
    request: Request,
    page_id: str,
    phone: str = Form(...),
):
    logger.debug("whatsapp-lookup page=%s phone=%s", page_id, phone)
    async with BaileysClient() as client:
        result = await client.lookup(phone)
    return templates.TemplateResponse(
        request,
        f"{_P}/wa_lookup_result.html",
        {"message": result.display(), "error": result.error},
    )


# ── WhatsApp Send — Step A: confirmation panel ────────────────────────────────


@router.post("/prospects/{page_id}/send-confirm")
async def wa_send_confirm(
    request: Request,
    page_id: str,
    phone: str = Form(...),
    name: str = Form(...),
    business: str = Form(""),
):
    canonical = normalise_phone(phone)
    if canonical:
        record = get_sent_record(load_state(), canonical)
        if record:
            return templates.TemplateResponse(
                request,
                f"{_P}/wa_send_result.html",
                {
                    "already": True,
                    "sent_at": record.get("sent_at", ""),
                    "dry_run": record.get("dry_run", False),
                },
            )

    message = build_message(name=name, expressed_interest=business)
    return templates.TemplateResponse(
        request,
        f"{_P}/wa_send_confirm.html",
        {
            "page_id": page_id,
            "phone": phone,
            "name": name,
            "business": business,
            "message": message,
            "dry_run": config.DRY_RUN,
        },
    )


# ── WhatsApp Send — Step B: execute ───────────────────────────────────────────


@router.post("/prospects/{page_id}/send")
async def wa_send(
    request: Request,
    page_id: str,
    phone: str = Form(...),
    name: str = Form(...),
    business: str = Form(""),
):
    logger.info("wa_send page=%s phone=%s dry_run=%s", page_id, phone, config.DRY_RUN)
    canonical = normalise_phone(phone)
    if not canonical:
        return templates.TemplateResponse(
            request,
            f"{_P}/wa_send_result.html",
            {"success": False, "error": f"Cannot parse phone: {phone}"},
        )

    # Idempotency guard — re-check immediately before sending
    record = get_sent_record(load_state(), canonical)
    if record:
        return templates.TemplateResponse(
            request,
            f"{_P}/wa_send_result.html",
            {
                "already": True,
                "sent_at": record.get("sent_at", ""),
                "dry_run": record.get("dry_run", False),
            },
        )

    message = build_message(name=name, expressed_interest=business)

    # Send (BaileysClient honours DRY_RUN internally)
    async with BaileysClient() as baileys:
        send_result = await baileys.send(canonical, message)

    if not send_result.sent:
        return templates.TemplateResponse(
            request,
            f"{_P}/wa_send_result.html",
            {"success": False, "error": send_result.error or "Send failed"},
        )

    # Notion record — proceeds even in dry-run (writes are reversible).
    # If it fails, the message was already sent (or dry-run logged); record
    # in state anyway so idempotency holds on retry.
    notion_page_id = ""
    try:
        async with NotionClient(config.NOTION_WRITE_TOKEN) as notion:
            notion_page_id = await create_claire_prospect(
                notion,
                name=name,
                phone=canonical,
                email=None,
                business=business,
                motivation="",
                message=message,
            )
    except Exception:
        logger.exception("create_claire_prospect failed for %s", canonical)

    sent_at = datetime.now(timezone.utc).isoformat()
    await append_and_save(
        phone=canonical,
        display_name=name,
        email=None,
        business=business,
        motivation="",
        notion_page_id=notion_page_id,
        sent_at=sent_at,
        dry_run=send_result.dry_run,
    )

    return templates.TemplateResponse(
        request,
        f"{_P}/wa_send_result.html",
        {
            "success": True,
            "already": False,
            "sent_at": sent_at,
            "dry_run": send_result.dry_run,
        },
    )


# ── Bulk outreach preview ─────────────────────────────────────────────────────

_CAP = 40


@router.post("/outreach/preview")
async def outreach_preview(
    request: Request,
    selected_ids: list[str] = Form(default=[]),
):
    if not selected_ids:
        return RedirectResponse("/prospects", status_code=303)

    if len(selected_ids) > _CAP:
        return HTMLResponse(
            f"<p class='text-red-600 text-sm'>Too many prospects selected "
            f"({len(selected_ids)}). Maximum is {_CAP}.</p>",
            status_code=400,
        )

    # Fail-closed: if state is unreadable, block preview rather than risk blast.
    try:
        sent_phones: set[str] = {
            p
            for e in load_state_strict()
            if e.get("phone")
            for p in (normalise_phone(e["phone"]),)
            if p is not None
        }
    except Exception:
        logger.exception("load_state_strict failed in outreach_preview")
        return HTMLResponse(
            "<p class='text-red-600 text-sm'>Outreach state unreadable — "
            "cannot proceed. Check logs.</p>",
            status_code=500,
        )

    # Fetch all prospect details in parallel — single client, no per-fetch overhead.
    async with NotionClient(config.NOTION_READONLY_TOKEN) as client:
        async def _fetch(page_id: str):
            try:
                return await get_prospect_detail(client, page_id)
            except Exception:
                logger.exception("get_prospect_detail failed for %s", page_id)
                return None

        details = await asyncio.gather(*[_fetch(pid) for pid in selected_ids])

    valid: list[dict] = []
    skipped: list[dict] = []

    for page_id, detail in zip(selected_ids, details):
        if detail is None:
            skipped.append({"page_id": page_id, "name": page_id, "reason": "Not found or Notion error"})
            continue
        eligible, reason = is_eligible(detail.row, sent_phones)
        if not eligible:
            skipped.append({"page_id": page_id, "name": detail.row.name, "reason": reason})
            continue
        expressed_interest = (
            detail.properties.get("Business")
            or detail.properties.get("Company Name")
            or ""
        )
        valid.append({
            "page_id": detail.row.page_id,
            "name": detail.row.name,
            "db_name": detail.row.db_name,
            "phone": detail.row.phone,
            "expressed_interest": expressed_interest,
            "message": build_message(name=detail.row.name, expressed_interest=expressed_interest or ""),
        })

    if not valid:
        return HTMLResponse(
            "<p class='text-amber-600 text-sm'>All selected prospects are ineligible. "
            "Nothing to send.</p>",
        )

    batch_id = str(uuid.uuid4())
    first_message = valid[0]["message"]

    return templates.TemplateResponse(
        request,
        "outreach/preview.html",
        {
            "valid": valid,
            "skipped": skipped,
            "batch_id": batch_id,
            "first_message": first_message,
            "dry_run": config.DRY_RUN,
        },
    )


# ── Bulk outreach batch start ─────────────────────────────────────────────────


@router.post("/outreach/batch/{batch_id}/start")
async def outreach_batch_start(
    request: Request,
    batch_id: str,
    selected_ids: list[str] = Form(default=[]),
    confirm_text: str = Form(default=""),
):
    if not selected_ids:
        return RedirectResponse("/prospects", status_code=303)

    if len(selected_ids) > _CAP:
        return HTMLResponse(
            f"<p class='text-red-600 text-sm'>Too many prospects ({len(selected_ids)}). "
            f"Maximum is {_CAP}.</p>",
            status_code=400,
        )

    # Fresh re-validation — defense in depth.
    try:
        sent_phones: set[str] = {
            p
            for e in load_state_strict()
            if e.get("phone")
            for p in (normalise_phone(e["phone"]),)
            if p is not None
        }
    except Exception:
        logger.exception("load_state_strict failed in outreach_batch_start")
        return HTMLResponse(
            "<p class='text-red-600 text-sm'>Outreach state unreadable — "
            "cannot proceed. Check logs.</p>",
            status_code=500,
        )

    async with NotionClient(config.NOTION_READONLY_TOKEN) as client:
        async def _fetch(page_id: str):
            try:
                return await get_prospect_detail(client, page_id)
            except Exception:
                logger.exception("get_prospect_detail failed for %s in batch_start", page_id)
                return None

        details = await asyncio.gather(*[_fetch(pid) for pid in selected_ids])

    valid_phones: list[str] = []
    for page_id, detail in zip(selected_ids, details):
        if detail is None:
            continue
        eligible, _ = is_eligible(detail.row, sent_phones)
        if not eligible:
            continue
        canonical = normalise_phone(detail.row.phone) if detail.row.phone else None
        if canonical:
            valid_phones.append(canonical)

    if not valid_phones:
        return HTMLResponse(
            "<p class='text-amber-600 text-sm'>All selected prospects are ineligible. "
            "Nothing to queue.</p>",
        )

    if not config.DRY_RUN:
        expected = f"SEND-{len(valid_phones)}"
        if confirm_text != expected:
            return HTMLResponse(
                f"<p class='text-red-600 text-sm'>Confirmation text incorrect. "
                f"Expected <code>{expected}</code>.</p>",
                status_code=400,
            )

    append_batch({
        "batch_id": batch_id,
        "status": "pending",
        "queued": valid_phones,
        "completed": [],
        "skipped": [],
        "failed": [],
        "started_at": None,
        "completed_at": None,
        "dry_run": config.DRY_RUN,
        "template_hash": get_template_hash(),
    })

    logger.info(
        "batch_start batch=%s queued=%d dry_run=%s",
        batch_id, len(valid_phones), config.DRY_RUN,
    )

    return RedirectResponse(f"/outreach/batch/{batch_id}", status_code=303)


# ── Bulk outreach batch view ──────────────────────────────────────────────────


@router.get("/outreach/batch/{batch_id}")
async def outreach_batch_view(request: Request, batch_id: str):
    return templates.TemplateResponse(
        request,
        "outreach/batch_queued.html",
        {"batch_id": batch_id, "dry_run": config.DRY_RUN},
    )


# ── Cartrack — Step A: confirmation panel ─────────────────────────────────────


@router.post("/prospects/{page_id}/cartrack-confirm")
async def cartrack_confirm(
    request: Request,
    page_id: str,
    name: str = Form(...),
    db_name: str = Form(...),
):
    return templates.TemplateResponse(
        request,
        f"{_P}/cartrack_confirm.html",
        {"page_id": page_id, "name": name, "db_name": db_name},
    )


# ── Cartrack — Step B: execute ────────────────────────────────────────────────


@router.post("/prospects/{page_id}/cartrack")
async def cartrack(
    request: Request,
    page_id: str,
    db_name: str = Form(...),
):
    try:
        async with NotionClient(config.NOTION_WRITE_TOKEN) as notion:
            if db_name == "Claire":
                await mark_submitted_to_pipeline(notion, page_id)
            else:
                await update_status(notion, page_id, db_name)
    except Exception:
        logger.exception("cartrack update failed for %s (db=%s)", page_id, db_name)
        return templates.TemplateResponse(
            request,
            f"{_P}/cartrack_result.html",
            {"success": False, "error": "Notion API error"},
        )

    return templates.TemplateResponse(
        request,
        f"{_P}/cartrack_result.html",
        {"success": True},
    )
