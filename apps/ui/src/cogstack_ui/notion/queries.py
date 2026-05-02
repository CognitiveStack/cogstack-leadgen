from __future__ import annotations

import asyncio
from dataclasses import dataclass

from cogstack_ui.notion.client import NotionClient
from cogstack_ui.notion.schema import (
    B2BLEADS_DB_ID,
    B2CLEADS_DB_ID,
    CLAIREPROSPECTS_DB_ID,
)
from cogstack_ui.utils.phone import normalise_phone

# Hard cap for record counting. Notion's query endpoint returns no total_count
# field, so counts require full pagination. Phase 1 databases are expected to
# be well under 1000 records; if the cap is hit the UI shows "1000+".
# Strategy: POST /databases/{id}/query with page_size=100, accumulate
# len(results) across all pages, stop early if cap is reached.
COUNT_CAP = 1000


@dataclass
class CountResult:
    count: int | None = None
    capped: bool = False
    error: bool = False

    def display(self) -> str:
        if self.error:
            return "—"
        if self.capped:
            return f"{self.count}+"
        return str(self.count)


async def count_database(client: NotionClient, db_id: str) -> CountResult:
    """Return the total record count for a Notion database.

    Paginates POST /databases/{id}/query (page_size=100) and accumulates
    len(results) until has_more=False or COUNT_CAP is reached.
    """
    total = 0
    cursor: str | None = None

    while True:
        payload: dict = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor

        data = await client.query_database(db_id, payload)
        total += len(data.get("results", []))

        if total >= COUNT_CAP:
            return CountResult(count=COUNT_CAP, capped=True)

        if not data.get("has_more", False):
            break

        cursor = data.get("next_cursor")

    return CountResult(count=total)


# ── Per-DB configuration ──────────────────────────────────────────────────────
#
# phone_type "phone_number" → filter uses phone_number.equals
# phone_type "rich_text"    → filter uses rich_text.contains (B2B Public Contact)

_DB_CONFIGS: list[dict] = [
    {
        "db_id": B2CLEADS_DB_ID,
        "db_name": "B2C",
        "name_prop": "Full Name",
        "phone_prop": "Phone",
        "phone_type": "phone_number",
        "status_prop": "Status",
        "date_prop": "Date Added",
    },
    {
        "db_id": B2BLEADS_DB_ID,
        "db_name": "B2B",
        "name_prop": "Company Name",
        "phone_prop": "Public Contact",
        "phone_type": "rich_text",
        "status_prop": "Status",
        "date_prop": "Date Found",
    },
    {
        "db_id": CLAIREPROSPECTS_DB_ID,
        "db_name": "Claire",
        "name_prop": "Full Name",
        "phone_prop": "Phone",
        "phone_type": "phone_number",
        "status_prop": "Response Status",
        "date_prop": "Date Added",
    },
]

# Keyed by DB ID for O(1) lookup in get_prospect_detail()
_DB_ID_TO_CONFIG: dict[str, dict] = {cfg["db_id"]: cfg for cfg in _DB_CONFIGS}


# ── ProspectRow ───────────────────────────────────────────────────────────────


@dataclass
class ProspectRow:
    """Unified prospect summary, hiding per-DB shape differences from route handlers."""

    page_id: str
    db_name: str        # "B2C" | "B2B" | "Claire"
    db_id: str
    name: str
    phone: str | None
    status: str | None
    date_str: str | None    # ISO date from the DB's primary date field
    created_time: str       # Notion metadata timestamp (always present, fallback sort)

    def sort_key(self) -> str:
        # ISO dates and ISO datetimes both sort correctly lexicographically.
        # created_time is always non-empty; date_str may be None.
        return self.date_str or self.created_time


# ── ProspectDetail ────────────────────────────────────────────────────────────


@dataclass
class ProspectDetail:
    """Full prospect page data for the detail view."""

    row: ProspectRow
    properties: dict[str, str | None]   # property name → human-readable value
    notion_url: str                     # "Open in Notion" link


# ── Property extraction helpers ───────────────────────────────────────────────


def _extract_title(prop: dict) -> str:
    return "".join(p.get("plain_text", "") for p in (prop.get("title") or []))


def _extract_rich_text(prop: dict) -> str | None:
    text = "".join(p.get("plain_text", "") for p in (prop.get("rich_text") or []))
    return text or None


def _extract_status_name(prop: dict) -> str | None:
    # Notion "status" type and "select" type both expose a .name field,
    # but under different keys.
    return (
        (prop.get("status") or {}).get("name")
        or (prop.get("select") or {}).get("name")
    )


def _prop_display(prop: dict) -> str | None:
    """Convert any Notion property value to a human-readable string for display."""
    ptype = prop.get("type")
    if ptype == "title":
        return _extract_title(prop) or None
    if ptype == "rich_text":
        return _extract_rich_text(prop)
    if ptype == "phone_number":
        return prop.get("phone_number")
    if ptype == "email":
        return prop.get("email")
    if ptype == "url":
        return prop.get("url")
    if ptype == "select":
        return (prop.get("select") or {}).get("name")
    if ptype == "status":
        return (prop.get("status") or {}).get("name")
    if ptype == "multi_select":
        return ", ".join(o.get("name", "") for o in (prop.get("multi_select") or []))
    if ptype == "date":
        date_val = prop.get("date") or {}
        start = date_val.get("start")
        end = date_val.get("end")
        return f"{start} → {end}" if end else start
    if ptype == "number":
        v = prop.get("number")
        return str(v) if v is not None else None
    if ptype == "checkbox":
        return "Yes" if prop.get("checkbox") else "No"
    if ptype == "relation":
        count = len(prop.get("relation") or [])
        return f"{count} linked" if count else None
    if ptype == "formula":
        fval = prop.get("formula") or {}
        ftype = fval.get("type")
        return str(fval.get(ftype)) if ftype and fval.get(ftype) is not None else None
    if ptype == "people":
        names = [(p.get("name") or "") for p in (prop.get("people") or [])]
        return ", ".join(n for n in names if n) or None
    if ptype == "created_time":
        return prop.get("created_time")
    if ptype == "last_edited_time":
        return prop.get("last_edited_time")
    # rollup and unknown types: skip
    return None


def _page_to_row(page: dict, cfg: dict) -> ProspectRow:
    props = page.get("properties", {})

    name = _extract_title(props.get(cfg["name_prop"]) or {}) or "(no name)"

    phone_raw = props.get(cfg["phone_prop"]) or {}
    if cfg["phone_type"] == "phone_number":
        phone: str | None = phone_raw.get("phone_number")
    else:
        phone = _extract_rich_text(phone_raw)

    date_val = (props.get(cfg["date_prop"]) or {}).get("date") or {}
    date_str: str | None = date_val.get("start")

    status = _extract_status_name(props.get(cfg["status_prop"]) or {})

    return ProspectRow(
        page_id=page["id"],
        db_name=cfg["db_name"],
        db_id=cfg["db_id"],
        name=name,
        phone=phone,
        status=status,
        date_str=date_str,
        created_time=page.get("created_time", ""),
    )


# ── list_prospects ────────────────────────────────────────────────────────────


async def list_prospects(client: NotionClient, limit: int = 50) -> list[ProspectRow]:
    """Return the most recent prospects across all 3 lead DBs, merged and sorted by date desc.

    Fetches up to `limit` records per DB in parallel, then merges and returns
    the top `limit` by date. Phase 1 only covers the first page; cursor-based
    pagination ("Load more") is a Phase 2 concern.
    """

    async def _query_one(cfg: dict) -> list[ProspectRow]:
        payload = {
            "page_size": limit,
            "sorts": [
                {"property": cfg["date_prop"], "direction": "descending"},
                {"timestamp": "created_time", "direction": "descending"},
            ],
        }
        data = await client.query_database(cfg["db_id"], payload)
        return [_page_to_row(p, cfg) for p in data.get("results", [])]

    results = await asyncio.gather(
        *[_query_one(cfg) for cfg in _DB_CONFIGS],
        return_exceptions=True,
    )

    rows: list[ProspectRow] = []
    for r in results:
        if isinstance(r, list):
            rows.extend(r)

    rows.sort(key=lambda r: r.sort_key(), reverse=True)
    return rows[:limit]


# ── find_by_phone ─────────────────────────────────────────────────────────────


async def find_by_phone(client: NotionClient, raw_phone: str) -> list[ProspectRow]:
    """Search all 3 lead DBs for a phone number.

    Normalises input to +27XXXXXXXXX, expands to both +27 and 0 variants,
    queries all DBs with both variants in parallel (6 total queries), then
    deduplicates by page_id.

    B2C and Claire use phone_number.equals; B2B uses rich_text.contains on
    Public Contact (may match email/website alongside phone — acceptable
    Phase 1 limitation).

    Searches both +27XXXXXXXXX and 0XXXXXXXXX variants. Records stored in
    other formats (no-plus "27...", spaced "+27 82 ...", etc.) will not
    match. Acceptable Phase 1 limitation.
    """
    canonical = normalise_phone(raw_phone)
    if canonical is None:
        return []

    # Expand: records may be stored as +27XXXXXXXXX or 0XXXXXXXXX
    local_form = "0" + canonical[3:]
    variants = [canonical, local_form]

    async def _query(cfg: dict, variant: str) -> list[ProspectRow]:
        if cfg["phone_type"] == "phone_number":
            filter_obj = {
                "property": cfg["phone_prop"],
                "phone_number": {"equals": variant},
            }
        else:
            filter_obj = {
                "property": cfg["phone_prop"],
                "rich_text": {"contains": variant},
            }
        data = await client.query_database(
            cfg["db_id"], {"filter": filter_obj, "page_size": 100}
        )
        return [_page_to_row(p, cfg) for p in data.get("results", [])]

    tasks = [_query(cfg, variant) for cfg in _DB_CONFIGS for variant in variants]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    seen: set[str] = set()
    rows: list[ProspectRow] = []
    for r in results:
        if isinstance(r, list):
            for row in r:
                if row.page_id not in seen:
                    seen.add(row.page_id)
                    rows.append(row)

    rows.sort(key=lambda r: r.sort_key(), reverse=True)
    return rows


# ── get_prospect_detail ───────────────────────────────────────────────────────


async def get_prospect_detail(client: NotionClient, page_id: str) -> ProspectDetail | None:
    """Fetch a single prospect page and return a ProspectDetail.

    Detects the source DB from parent.database_id. Returns None if the page
    doesn't belong to one of the 3 prospect DBs (guards against stray IDs).
    """
    page = await client.get_page(page_id)

    raw_db_id = (page.get("parent") or {}).get("database_id", "")
    cfg = _DB_ID_TO_CONFIG.get(raw_db_id)
    if cfg is None:
        return None

    row = _page_to_row(page, cfg)
    notion_url = page.get("url", f"https://notion.so/{page_id.replace('-', '')}")

    display_props = {
        name: _prop_display(val)
        for name, val in page.get("properties", {}).items()
    }

    return ProspectDetail(
        row=row,
        properties=display_props,
        notion_url=notion_url,
    )
