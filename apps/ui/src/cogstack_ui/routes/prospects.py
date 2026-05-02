from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates

from cogstack_ui import config
from cogstack_ui.notion.client import NotionClient
from cogstack_ui.notion.queries import (
    find_by_phone,
    get_prospect_detail,
    list_prospects,
)
from cogstack_ui.utils.phone import normalise_phone
from cogstack_ui.whatsapp.state import get_sent_record, load_state

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(
    directory=Path(__file__).parent.parent / "templates"
)


@router.get("/prospects")
async def prospects_list(request: Request, q: str | None = None):
    rows = []
    phone_error: str | None = None
    canonical_phone: str | None = None

    if q and q.strip():
        q = q.strip()
        canonical_phone = normalise_phone(q)
        if canonical_phone is None:
            phone_error = f"Could not parse '{q}' as a SA phone number"
        else:
            try:
                async with NotionClient(config.NOTION_READONLY_TOKEN) as client:
                    rows = await find_by_phone(client, q)
            except Exception:
                logger.exception("find_by_phone failed for %r", q)
                phone_error = "Search failed — Notion API error"
    else:
        q = ""
        try:
            async with NotionClient(config.NOTION_READONLY_TOKEN) as client:
                rows = await list_prospects(client)
        except Exception:
            logger.exception("list_prospects failed")

    return templates.TemplateResponse(
        request,
        "prospects/list.html",
        {
            "rows": rows,
            "q": q,
            "phone_error": phone_error,
            "canonical_phone": canonical_phone,
        },
    )


@router.get("/prospects/{page_id}")
async def prospect_detail(request: Request, page_id: str):
    try:
        async with NotionClient(config.NOTION_READONLY_TOKEN) as client:
            detail = await get_prospect_detail(client, page_id)
    except Exception:
        logger.exception("get_prospect_detail failed for %r", page_id)
        raise HTTPException(status_code=502, detail="Notion API error")

    if detail is None:
        raise HTTPException(status_code=404, detail="Prospect not found")

    # Outreach state — check shared outreach-state.json for idempotency display
    canonical_phone = normalise_phone(detail.row.phone or "") if detail.row.phone else None
    outreach_record = get_sent_record(load_state(), canonical_phone) if canonical_phone else None

    # Cartrack state — read from Notion properties already fetched above
    if detail.row.db_name == "Claire":
        cartrack_done = detail.properties.get("Submitted to Pipeline") == "Yes"
    else:
        cartrack_done = detail.properties.get("Status") == "Sent to Call Centre"

    return templates.TemplateResponse(
        request,
        "prospects/detail.html",
        {
            "detail": detail,
            "outreach_record": outreach_record,
            "cartrack_done": cartrack_done,
        },
    )
