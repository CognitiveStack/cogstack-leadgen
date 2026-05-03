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
from cogstack_ui.whatsapp.eligibility import is_eligible
from cogstack_ui.whatsapp.state import get_sent_record, load_state, load_state_strict

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

    # Eligibility — load state once, build sent_phones set, evaluate per row.
    # Drives checkbox disabled state; Gate 5.2 re-validates server-side on submit.
    # Fail-closed: if state is unreadable, disable ALL selection rather than
    # risk re-contacting phones we've already messaged (40x blast radius).
    state_load_failed = False
    sent_phones: set[str] = set()
    try:
        # Defensive re-normalisation: protects dedup from any historical
        # state.json entries that may not be in canonical form.
        sent_phones = {
            normalise_phone(e["phone"])
            for e in load_state_strict()
            if e.get("phone")
        }
    except Exception:
        logger.exception("load_state failed — disabling selection")
        state_load_failed = True

    if state_load_failed:
        prospect_rows = [(row, False, "State unavailable") for row in rows]
    else:
        prospect_rows = [(row, *is_eligible(row, sent_phones)) for row in rows]

    return templates.TemplateResponse(
        request,
        "prospects/list.html",
        {
            "prospect_rows": prospect_rows,
            "state_load_failed": state_load_failed,
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
