from __future__ import annotations

from dataclasses import dataclass

from cogstack_ui.notion.client import NotionClient

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
