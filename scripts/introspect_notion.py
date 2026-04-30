#!/usr/bin/env python3
"""
Introspect Notion databases and write a typed schema snapshot to
apps/ui/src/cogstack_ui/notion/schema.py.

Usage:
    uv run scripts/introspect_notion.py

Requires:
    NOTION_READONLY_TOKEN in .env (create at notion.so/my-integrations)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

NOTION_API_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"

_REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = _REPO_ROOT / "apps/ui/src/cogstack_ui/notion/schema.py"

# Authoritative DB IDs — source: PRD §6
# Do NOT read from notion_config.json (sources_database_id there is stale/wrong)
DATABASES: dict[str, tuple[str, str]] = {
    "b2c_leads":   ("B2CLeads",   "32089024-cd3d-812e-a6c6-d8e21d9126b3"),
    "b2c_batches": ("B2CBatches", "32089024-cd3d-81a7-8691-ca999aa1494f"),
    "b2b_leads":   ("B2BLeads",   "30b89024-cd3d-810a-bb28-e46825320802"),
    "sources":     ("Sources",    "30b89024-cd3d-81b1-ab3a-c900965b5d64"),
}


# ---------------------------------------------------------------------------
# Token — reads only NOTION_READONLY_TOKEN; no blanket os.environ import
# ---------------------------------------------------------------------------

def get_token() -> str:
    # os.environ first (CI / explicit export), then .env file
    token = os.environ.get("NOTION_READONLY_TOKEN", "")
    if not token.strip():
        env_file = _REPO_ROOT / ".env"
        if env_file.exists():
            token = dotenv_values(env_file).get("NOTION_READONLY_TOKEN") or ""
    if not token.strip():
        print(
            "Error: NOTION_READONLY_TOKEN is not set or is empty.\n"
            "Create a read-only Notion integration at "
            "https://www.notion.so/my-integrations and add it to .env.",
            file=sys.stderr,
        )
        sys.exit(1)
    return token.strip()


# ---------------------------------------------------------------------------
# Notion API
# ---------------------------------------------------------------------------

def fetch_database(client: httpx.Client, db_id: str) -> dict:
    try:
        resp = client.get(f"{NOTION_BASE_URL}/databases/{db_id}")
    except httpx.TimeoutException:
        print(
            f"Error: Request to Notion timed out (database {db_id}). Retry.",
            file=sys.stderr,
        )
        sys.exit(1)

    if resp.status_code == 401:
        print(
            "Error: NOTION_READONLY_TOKEN appears invalid (401 Unauthorized).\n"
            "Verify the token at https://www.notion.so/my-integrations.",
            file=sys.stderr,
        )
        sys.exit(1)

    if resp.status_code == 404:
        print(
            f"Error: Database {db_id} not found, or the integration is not "
            "shared with it.\n"
            "Open the database in Notion → ··· menu → Connections → "
            "Connect to → cogstack-leadgen-readonly.",
            file=sys.stderr,
        )
        sys.exit(1)

    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Schema extraction
# ---------------------------------------------------------------------------

def extract_select_options(prop: dict) -> list[str]:
    prop_type = prop["type"]
    inner = prop.get(prop_type, {})
    return [o["name"] for o in inner.get("options", [])]


def extract_schema(db: dict) -> dict[str, dict]:
    """Return {property_name: {type, options?}} for every property in the DB."""
    result: dict[str, dict] = {}
    for name, prop in db["properties"].items():
        prop_type = prop["type"]
        entry: dict = {"type": prop_type}
        if prop_type in ("select", "multi_select", "status"):
            opts = extract_select_options(prop)
            if opts:
                entry["options"] = opts
        result[name] = entry
    return result


# ---------------------------------------------------------------------------
# Type mapping: Notion property type → Python annotation string
# ---------------------------------------------------------------------------

def _field_name(notion_name: str) -> str:
    """Convert a Notion property name to a valid snake_case Python identifier."""
    s = notion_name.strip()
    for ch in (" ", "-", "/", "(", ")", ".", ",", "'", '"', "?", "!"):
        s = s.replace(ch, "_")
    while "__" in s:
        s = s.replace("__", "_")
    s = s.strip("_").lower()
    if s and s[0].isdigit():
        s = f"_{s}"
    return s or "field"


def _python_type(prop_meta: dict) -> str:
    """Return the Python type annotation string for a Notion property."""
    prop_type = prop_meta["type"]
    opts = prop_meta.get("options", [])

    if prop_type == "title":
        return "str"
    if prop_type in ("rich_text", "url", "email", "phone_number"):
        return "str | None"
    if prop_type == "number":
        return "float | None"
    if prop_type == "checkbox":
        return "bool"
    if prop_type == "date":
        return "str | None"
    if prop_type in ("created_time", "last_edited_time"):
        return "str"
    if prop_type in ("created_by", "last_edited_by"):
        return "str"
    if prop_type == "unique_id":
        return "str | None"
    if prop_type in ("relation", "people", "files"):
        return "list[str]"
    if prop_type in ("formula", "rollup"):
        return "object | None"
    if prop_type in ("select", "status"):
        if opts:
            args = ", ".join(repr(o) for o in opts)
            return f"Literal[{args}] | None"
        return "str | None"
    if prop_type == "multi_select":
        if opts:
            args = ", ".join(repr(o) for o in opts)
            return f"list[Literal[{args}]]"
        return "list[str]"
    return "object | None"


def _default(python_type: str) -> str | None:
    """
    Return the default value expression string.
    Returns None for list types — caller must use Field(default_factory=list).
    """
    if python_type == "str":
        return '""'
    if python_type == "bool":
        return "False"
    if python_type.startswith("list"):
        return None
    return "None"


# ---------------------------------------------------------------------------
# Code generation — one typed Pydantic Properties model per DB
# ---------------------------------------------------------------------------

def generate_module(
    schemas: dict[str, tuple[str, str, dict[str, dict]]]
) -> str:
    """
    Emit schema.py: per-DB Properties model with field-level types and
    Literal[...] annotations for select/status/multi_select options.
    """
    lines: list[str] = [
        '"""',
        "Notion database schema snapshot.",
        "",
        "Auto-generated by scripts/introspect_notion.py — do not edit by hand.",
        "Re-run the script whenever Notion property definitions change.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Literal",
        "",
        "from pydantic import BaseModel, Field",
        "",
        "",
    ]

    db_entries: list[tuple[str, str]] = []  # (db_id_const, label)

    for (label, db_id, schema) in schemas.values():
        db_id_const = f"{label.upper()}_DB_ID"
        db_entries.append((db_id_const, label))

        sep = "# " + "-" * 75
        lines += [
            sep,
            f"# {label}  —  {db_id}",
            sep,
            "",
            f'{db_id_const} = "{db_id}"',
            "",
            f"class {label}Properties(BaseModel):",
            f'    """Typed properties for a {label} Notion page.',
            "",
            "    Field names are snake_case Python identifiers; aliases are the",
            "    original Notion property names used in API responses.",
            '    """',
            '    model_config = {"populate_by_name": True}',
            "",
        ]

        for prop_name in sorted(schema.keys()):
            prop_meta = schema[prop_name]
            py_name = _field_name(prop_name)
            py_type = _python_type(prop_meta)
            default = _default(py_type)

            if default is None:
                lines.append(
                    f"    {py_name}: {py_type} = "
                    f"Field(default_factory=list, alias={prop_name!r})"
                )
            else:
                lines.append(
                    f"    {py_name}: {py_type} = "
                    f"Field({default}, alias={prop_name!r})"
                )

        lines += ["", ""]

    lines += [
        "# " + "-" * 75,
        "# All DB IDs — import this dict in client.py for iteration",
        "# " + "-" * 75,
        "",
        "ALL_DB_IDS: dict[str, str] = {",
    ]
    for db_id_const, label in db_entries:
        lines.append(f'    "{label}": {db_id_const},')
    lines += ["}", ""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    token = get_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_API_VERSION,
    }

    schemas: dict[str, tuple[str, str, dict]] = {}

    with httpx.Client(headers=headers, timeout=30) as client:
        for key, (label, db_id) in DATABASES.items():
            print(f"  Fetching {label} ({db_id}) …", flush=True)
            db = fetch_database(client, db_id)
            schema = extract_schema(db)
            schemas[key] = (label, db_id, schema)
            print(f"    → {len(schema)} properties")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    source = generate_module(schemas)
    OUTPUT_PATH.write_text(source)
    print(f"\nWrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
