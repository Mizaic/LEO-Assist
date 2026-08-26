"""Platform-admin emergency override of two-person process gates.

Atlas trace:
  DI: DI-B00BD595
  DO: DO-19364787
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-B00BD595")
"""

from __future__ import annotations

from fastapi import HTTPException

from libs.audit.security_log import emit_break_glass

REASON_MIN = 10
REASON_MAX = 500
SELF_APPROVE_DETAIL = "A different person must publish this draft"


def _clean(value: str) -> str:
    return (value or "").strip().lower()


def _valid_reason(reason: str) -> str:
    cleaned = (reason or "").strip()
    if REASON_MIN <= len(cleaned) <= REASON_MAX:
        return cleaned
    return ""


def require_second_person(
    *,
    author: str,
    actor: str,
    is_platform_admin: bool,
    reason: str,
    gate: str,
    resource_id: str,
) -> None:
    """Allow a different person, or a platform admin with a written reason.

    Writes an append-only audit record when the emergency path is used.
    Raises HTTP 403 when the two-person gate still applies.
    """
    who = _clean(actor)
    wrote = _clean(author)
    if wrote != who:
        return
    cleaned = _valid_reason(reason)
    if is_platform_admin and cleaned:
        emit_break_glass(
            email=who,
            gate=gate,
            reason=cleaned,
            resource_id=resource_id,
            outcome="allowed",
        )
        return
    raise HTTPException(status_code=403, detail=SELF_APPROVE_DETAIL)
