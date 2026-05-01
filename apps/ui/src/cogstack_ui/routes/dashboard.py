from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from cogstack_ui import config
from cogstack_ui.notion.client import NotionClient
from cogstack_ui.notion.queries import CountResult, count_database
from cogstack_ui.notion.schema import (
    B2CBATCHES_DB_ID,
    B2BLEADS_DB_ID,
    B2CLEADS_DB_ID,
    CLAIREPROSPECTS_DB_ID,
    SOURCES_DB_ID,
)

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(
    directory=Path(__file__).parent.parent / "templates"
)

_DATABASES: list[tuple[str, str]] = [
    ("b2c_leads", B2CLEADS_DB_ID),
    ("b2c_batches", B2CBATCHES_DB_ID),
    ("b2b_leads", B2BLEADS_DB_ID),
    ("sources", SOURCES_DB_ID),
    ("claire_prospects", CLAIREPROSPECTS_DB_ID),
]


async def _safe_count(
    client: NotionClient, key: str, db_id: str
) -> tuple[str, str]:
    """Return (key, display_string). Never raises — logs errors and returns '—'."""
    try:
        result = await count_database(client, db_id)
        return key, result.display()
    except Exception:
        logger.exception("Dashboard count failed for %s (%s)", key, db_id)
        return key, CountResult(error=True).display()


@router.get("/")
async def dashboard(request: Request):
    async with NotionClient(config.NOTION_READONLY_TOKEN) as client:
        pairs = await asyncio.gather(
            *[_safe_count(client, key, db_id) for key, db_id in _DATABASES]
        )

    counts = dict(pairs)
    return templates.TemplateResponse(request, "dashboard.html", {"counts": counts})
