from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from cogstack_ui.config import BAILEYS_URL, DRY_RUN

logger = logging.getLogger(__name__)

# Baileys /send adds 30–60 s internal jitter before delivery; allow headroom.
_SEND_TIMEOUT = 90.0
_LOOKUP_TIMEOUT = 15.0


# ── Result dataclasses ────────────────────────────────────────────────────────


@dataclass
class LookupResult:
    exists: bool = False
    name: str | None = None
    error: bool = False

    def display(self) -> str:
        """Human-readable string for HTMX rendering."""
        if self.error:
            return "Lookup failed (Baileys unreachable)"
        if not self.exists:
            return "WhatsApp: number not on WhatsApp"
        if self.name:
            return f"WhatsApp: {self.name}"
        return "WhatsApp: registered, no public name"


@dataclass
class SendResult:
    sent: bool = False
    error: str | None = None
    dry_run: bool = False


# ── BaileysClient ─────────────────────────────────────────────────────────────


class BaileysClient:
    """Async wrapper for the Baileys WhatsApp service.

    Usage::

        async with BaileysClient() as client:
            result = await client.lookup("+27821234567")
            ok = await client.send("+27821234567", "Hello!")

    base_url defaults to config.BAILEYS_URL (env BAILEYS_URL or http://baileys:3456).
    """

    def __init__(self, base_url: str = BAILEYS_URL) -> None:
        self._base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> BaileysClient:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=_SEND_TIMEOUT,
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._client is not None:
            await self._client.aclose()

    # ── lookup ────────────────────────────────────────────────────────────────

    async def lookup(self, phone: str) -> LookupResult:
        """Query Baileys /lookup for the WhatsApp display name of a number.

        Always performs the real HTTP call regardless of DRY_RUN — lookup
        is read-only and has no side effects.
        """
        assert self._client is not None, "Use BaileysClient as an async context manager"
        try:
            resp = await self._client.post(
                "/lookup",
                json={"phone": phone},
                timeout=_LOOKUP_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            return LookupResult(
                exists=bool(data.get("exists")),
                name=data.get("name") or None,
            )
        except httpx.TimeoutException:
            logger.warning("Baileys lookup timeout for %s", phone)
            return LookupResult(error=True)
        except httpx.HTTPStatusError as exc:
            logger.warning("Baileys lookup HTTP %d for %s", exc.response.status_code, phone)
            return LookupResult(error=True)
        except httpx.HTTPError as exc:
            logger.warning("Baileys lookup error for %s: %s", phone, exc)
            return LookupResult(error=True)

    # ── send ──────────────────────────────────────────────────────────────────

    async def send(self, phone: str, message: str) -> SendResult:
        """Send a WhatsApp message via Baileys /send.

        When config.DRY_RUN is True, logs the message and returns a mock
        success without making any HTTP call. DRY_RUN is the default during
        development; set COGSTACK_DRY_RUN=false in .env for real sends.
        """
        assert self._client is not None, "Use BaileysClient as an async context manager"

        if DRY_RUN:
            logger.info(
                "DRY RUN: would send to %s:\n%s",
                phone,
                message,
            )
            return SendResult(sent=True, dry_run=True)

        try:
            resp = await self._client.post(
                "/send",
                json={"phone": phone, "message": message},
                timeout=_SEND_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("sent"):
                logger.info("Sent WA message to %s", phone)
                return SendResult(sent=True)
            error_msg = data.get("error", "unknown")
            logger.warning("Baileys send rejected for %s: %s", phone, error_msg)
            return SendResult(sent=False, error=error_msg)
        except httpx.TimeoutException:
            logger.warning("Baileys send timeout for %s", phone)
            return SendResult(sent=False, error="timeout")
        except httpx.HTTPStatusError as exc:
            logger.warning("Baileys send HTTP %d for %s", exc.response.status_code, phone)
            return SendResult(sent=False, error=f"HTTP {exc.response.status_code}")
        except httpx.HTTPError as exc:
            logger.warning("Baileys send error for %s: %s", phone, exc)
            return SendResult(sent=False, error=str(exc))
