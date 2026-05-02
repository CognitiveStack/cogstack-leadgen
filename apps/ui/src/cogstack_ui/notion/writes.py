from __future__ import annotations

import logging
from datetime import datetime, timezone

from cogstack_ui.notion.client import NotionClient
from cogstack_ui.notion.schema import CLAIREPROSPECTS_DB_ID

logger = logging.getLogger(__name__)

# Notion property type for B2C/B2B Status fields is "select" (not "status").
# Verified via GET /databases/{id} — introspect_notion.py cannot distinguish the two.
_STATUS_SENT_TO_CALL_CENTRE = "Sent to Call Centre"


async def update_status(
    client: NotionClient,
    page_id: str,
    db_name: str,
    new_status: str = _STATUS_SENT_TO_CALL_CENTRE,
) -> None:
    """PATCH the Status field on a B2C or B2B Leads page.

    db_name ("B2C" | "B2B") is used only for logging — both DBs share the
    same Status property name and type, so no branching is needed.

    Raises httpx.HTTPStatusError on 4xx/5xx; caller handles.
    Uses a NotionClient initialised with NOTION_WRITE_TOKEN.
    """
    logger.info("update_status page=%s db=%s new=%s", page_id, db_name, new_status)
    await client.patch_page(
        page_id,
        {"Status": {"select": {"name": new_status}}},
    )


async def mark_submitted_to_pipeline(
    client: NotionClient,
    page_id: str,
) -> None:
    """PATCH the Submitted to Pipeline checkbox on a Claire-Prospects page.

    Raises httpx.HTTPStatusError on 4xx/5xx; caller handles.
    Uses a NotionClient initialised with NOTION_WRITE_TOKEN.
    """
    await client.patch_page(
        page_id,
        {"Submitted to Pipeline": {"checkbox": True}},
    )


async def create_claire_prospect(
    client: NotionClient,
    *,
    name: str,
    phone: str,
    email: str | None,
    business: str,
    motivation: str,
    message: str,
) -> str:
    """POST a new page to the Claire-Prospects DB after a WhatsApp send.

    Mirrors scripts/whatsapp_outreach.py::notion_create_record() exactly —
    same property names, same types — so records created here and records
    created by the script are indistinguishable in Notion.

    Returns the new page_id.
    Raises httpx.HTTPStatusError on 4xx/5xx; caller handles.
    Uses a NotionClient initialised with NOTION_WRITE_TOKEN.
    """
    now = datetime.now(timezone.utc).isoformat()

    properties: dict = {
        "Full Name":         {"title": [{"text": {"content": name}}]},
        "Phone":             {"phone_number": phone},
        "Business":          {"rich_text": [{"text": {"content": business[:2000]}}]},
        "Motivation":        {"rich_text": [{"text": {"content": motivation[:2000]}}]},
        "Outreach Message":  {"rich_text": [{"text": {"content": message[:2000]}}]},
        "Outreach Sent At":  {"date": {"start": now}},
        "Response Status":   {"select": {"name": "Pending"}},
        "Submitted to Pipeline": {"checkbox": False},
        "Date Added":        {"date": {"start": now}},
    }
    if email:
        properties["Email"] = {"email": email}

    payload = {
        "parent": {"database_id": CLAIREPROSPECTS_DB_ID},
        "properties": properties,
    }

    page = await client.create_page(payload)
    return page["id"]
