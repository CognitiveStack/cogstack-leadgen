from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

# Repo root: src/cogstack_ui/ → src/ → ui/ → apps/ → repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent


def _env(key: str, default: str = "") -> str:
    """Read one env var from os.environ, then .env.
    Returns default if unset, empty after strip, or missing.
    Strips whitespace from the env value before returning.
    """
    val = os.environ.get(key, "")
    if not val.strip():
        env_file = _REPO_ROOT / ".env"
        if env_file.exists():
            val = dotenv_values(env_file).get(key) or ""
    return val.strip() or default


NOTION_READONLY_TOKEN: str = _env("NOTION_READONLY_TOKEN")
NOTION_WRITE_TOKEN: str = _env("NOTION_WRITE_TOKEN")
BAILEYS_URL: str = _env("BAILEYS_URL") or "http://baileys:3456"
OUTREACH_STATE_PATH: str = _env("OUTREACH_STATE_PATH") or "/app/logs/outreach-state.json"

# Dry-run mode — default True (safe). Set COGSTACK_DRY_RUN=false in .env to enable real sends.
DRY_RUN: bool = _env("COGSTACK_DRY_RUN").lower() not in ("false", "0", "no")

# Jitter between WhatsApp sends (seconds). Configurable; validated at startup.
OUTREACH_JITTER_MIN_S: float = float(_env("OUTREACH_JITTER_MIN_S", "3"))
OUTREACH_JITTER_MAX_S: float = float(_env("OUTREACH_JITTER_MAX_S", "5"))

if OUTREACH_JITTER_MIN_S < 0:
    raise ValueError(
        f"OUTREACH_JITTER_MIN_S must be >= 0, got {OUTREACH_JITTER_MIN_S}"
    )
if OUTREACH_JITTER_MAX_S < OUTREACH_JITTER_MIN_S:
    raise ValueError(
        f"OUTREACH_JITTER_MAX_S ({OUTREACH_JITTER_MAX_S}) must be >= "
        f"OUTREACH_JITTER_MIN_S ({OUTREACH_JITTER_MIN_S})"
    )
