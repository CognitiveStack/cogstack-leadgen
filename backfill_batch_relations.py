"""
Backfill Batch Relations
========================
Links existing Notion leads to their correct Batch record by matching
each lead's creation time to the closest batch run date.

Usage:
    uv run backfill_batch_relations.py
"""

import os
import httpx
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

NOTION_API_KEY = os.environ["NOTION_API_KEY"]
LEADS_DB_ID = os.environ["LEADS_DB_ID"]
BATCHES_DB_ID = os.environ["BATCHES_DB_ID"]
HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


def get_all_pages(db_id: str, extra_body: dict = {}) -> list:
    """Paginate through all results in a Notion database."""
    results = []
    cursor = None
    while True:
        body = {"page_size": 100, **extra_body}
        if cursor:
            body["start_cursor"] = cursor
        r = httpx.post(
            f"https://api.notion.com/v1/databases/{db_id}/query",
            headers=HEADERS,
            json=body,
        )
        r.raise_for_status()
        data = r.json()
        results.extend(data["results"])
        if not data.get("has_more"):
            break
        cursor = data["next_cursor"]
    return results


def parse_dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def main():
    print("Fetching all batches...")
    raw_batches = get_all_pages(BATCHES_DB_ID)

    # Only keep real Hugo batches (skip test batches and malformed ones)
    batches = []
    for b in raw_batches:
        batch_id = b["properties"]["Batch ID"]["title"]
        if not batch_id:
            continue
        bid = batch_id[0]["plain_text"]
        run_date = b["properties"].get("Run Date", {}).get("date", {})
        if not run_date or not run_date.get("start"):
            continue
        batches.append({
            "id": b["id"],
            "batch_id": bid,
            "run_date": parse_dt(run_date["start"]),
        })

    batches.sort(key=lambda x: x["run_date"])
    print(f"Found {len(batches)} batches with run dates:")
    for b in batches:
        print(f"  {b['batch_id']} — {b['run_date'].strftime('%Y-%m-%d %H:%M')} UTC")

    print("\nFetching all leads...")
    # Only leads with empty Batch relation
    raw_leads = get_all_pages(LEADS_DB_ID)

    leads_to_update = []
    for lead in raw_leads:
        batch_rel = lead["properties"].get("Batch", {}).get("relation", [])
        if batch_rel:
            continue  # already linked
        name = lead["properties"]["Company Name"]["title"]
        name = name[0]["plain_text"] if name else "(unnamed)"
        created = parse_dt(lead["created_time"])
        leads_to_update.append({
            "id": lead["id"],
            "name": name,
            "created": created,
        })

    print(f"Found {len(leads_to_update)} leads without a Batch link.\n")

    if not leads_to_update:
        print("Nothing to backfill.")
        return

    # Match each lead to the closest batch by run date (nearest before or after)
    def closest_batch(lead_created: datetime) -> dict:
        return min(batches, key=lambda b: abs((b["run_date"] - lead_created).total_seconds()))

    updated = 0
    skipped = 0
    for lead in leads_to_update:
        batch = closest_batch(lead["created"])
        diff_minutes = abs((batch["run_date"] - lead["created"]).total_seconds()) / 60

        # Skip if closest batch is more than 60 minutes away — ambiguous
        if diff_minutes > 60:
            print(f"  SKIP  {lead['name']} — closest batch {batch['batch_id']} is {diff_minutes:.0f}m away")
            skipped += 1
            continue

        r = httpx.patch(
            f"https://api.notion.com/v1/pages/{lead['id']}",
            headers=HEADERS,
            json={"properties": {"Batch": {"relation": [{"id": batch["id"]}]}}},
        )
        r.raise_for_status()
        print(f"  LINKED {lead['name']} → {batch['batch_id']} ({diff_minutes:.0f}m apart)")
        updated += 1

    print(f"\nDone. {updated} linked, {skipped} skipped (ambiguous timing).")


if __name__ == "__main__":
    main()
