from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

# Repo root: src/cogstack_ui/ → src/ → ui/ → apps/ → repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent


def _env(key: str) -> str:
    """Read one env var from os.environ, then .env — no blanket import."""
    val = os.environ.get(key, "")
    if not val.strip():
        env_file = _REPO_ROOT / ".env"
        if env_file.exists():
            val = dotenv_values(env_file).get(key) or ""
    return val.strip()


NOTION_READONLY_TOKEN: str = _env("NOTION_READONLY_TOKEN")
NOTION_WRITE_TOKEN: str = _env("NOTION_WRITE_TOKEN")
BAILEYS_URL: str = _env("BAILEYS_URL") or "http://baileys:3456"
OUTREACH_STATE_PATH: str = _env("OUTREACH_STATE_PATH") or "/app/logs/outreach-state.json"

# Dry-run mode — default True (safe). Set COGSTACK_DRY_RUN=false in .env to enable real sends.
DRY_RUN: bool = _env("COGSTACK_DRY_RUN").lower() not in ("false", "0", "no")
