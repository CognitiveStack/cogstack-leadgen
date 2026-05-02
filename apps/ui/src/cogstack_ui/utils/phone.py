from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def normalise_phone(raw: object) -> str | None:
    """Normalise any SA phone format to +27XXXXXXXXX.

    Handles integer input (e.g. from numeric storage) by zero-padding to 10 digits.
    Returns None for unrecognised formats and logs a warning.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        raw = str(int(raw)).zfill(10)
    phone = str(raw).strip().replace(" ", "").replace("-", "")
    if phone.startswith("+27"):
        return phone
    if phone.startswith("27") and len(phone) == 11:
        return f"+{phone}"
    if phone.startswith("0") and len(phone) == 10:
        return f"+27{phone[1:]}"
    log.warning("Unrecognised phone format: %r", raw)
    return None
