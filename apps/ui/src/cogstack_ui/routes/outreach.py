from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.templating import Jinja2Templates

from cogstack_ui import config
from cogstack_ui.baileys.client import BaileysClient
from cogstack_ui.notion.client import NotionClient
from cogstack_ui.notion.writes import (
    create_claire_prospect,
    mark_submitted_to_pipeline,
    update_status,
)
from cogstack_ui.utils.phone import normalise_phone
from cogstack_ui.whatsapp.state import (
    append_and_save,
    get_sent_record,
    load_state,
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
