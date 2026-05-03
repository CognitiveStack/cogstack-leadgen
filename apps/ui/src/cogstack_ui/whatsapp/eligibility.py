from __future__ import annotations

from cogstack_ui.notion.queries import ProspectRow
from cogstack_ui.utils.phone import normalise_phone


def is_eligible(row: ProspectRow, sent_phones: set[str]) -> tuple[bool, str | None]:
    """Return (eligible, reason_if_not). reason is None when eligible.

    Shared between /prospects list (UI checkbox disable) and
    /outreach/preview (server-side re-validation, Gate 5.2).
    Do not duplicate this logic elsewhere.

    Cross-source dedup: a QA-Approved B2C/B2B row is ineligible if we have
    already messaged that phone via any source. outreach-state.json is the
    global truth regardless of which DB the row came from.
    """
    canonical = normalise_phone(row.phone) if row.phone else None

    if row.db_name in ("B2C", "B2B"):
        if row.status != "QA Approved":
            return False, "Status not QA Approved"
        if canonical and canonical in sent_phones:
            return False, "Already contacted"
        return True, None

    if row.db_name == "Claire":
        if canonical and canonical in sent_phones:
            return False, "Already contacted"
        return True, None

    return False, f"Unknown source: {row.db_name}"
