from __future__ import annotations

import httpx

NOTION_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"


class NotionClient:
    """Thin async wrapper around the Notion REST API.

    Usage::

        async with NotionClient(token) as client:
            data = await client.query_database(db_id, {"page_size": 1})
    """

    def __init__(self, token: str) -> None:
        self._token = token
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> NotionClient:
        self._client = httpx.AsyncClient(
            base_url=NOTION_BASE_URL,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def query_database(self, db_id: str, payload: dict) -> dict:
        assert self._client is not None, "Use NotionClient as an async context manager"
        resp = await self._client.post(f"/databases/{db_id}/query", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def get_page(self, page_id: str) -> dict:
        assert self._client is not None, "Use NotionClient as an async context manager"
        resp = await self._client.get(f"/pages/{page_id}")
        resp.raise_for_status()
        return resp.json()

    async def patch_page(self, page_id: str, properties: dict) -> dict:
        assert self._client is not None, "Use NotionClient as an async context manager"
        resp = await self._client.patch(
            f"/pages/{page_id}", json={"properties": properties}
        )
        resp.raise_for_status()
        return resp.json()

    async def create_page(self, payload: dict) -> dict:
        assert self._client is not None, "Use NotionClient as an async context manager"
        resp = await self._client.post("/pages", json=payload)
        resp.raise_for_status()
        return resp.json()
