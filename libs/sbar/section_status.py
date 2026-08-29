"""Honest SBAR section and integrity statuses.

Atlas:
  DI: DI-979BDE66, DI-075775FF, DI-B7A69F26
  DO: DO-E2BF30E7
  VT: VT-D9EC5652
"""

from __future__ import annotations


def section_status(*, text: str, error: str | None) -> str:
    """Return failed, skipped, or completed for one SBAR section."""
    if str(error or "").strip():
        return "failed"
    if str(text or "").strip():
        return "completed"
    return "skipped"


def integrity_status_for(
    *,
    audit_blockers: list[str] | None = None,
    preflight_failed: bool = False,
) -> str:
    """Return failed when a safety check did not pass."""
    blockers = [str(item or "").strip() for item in audit_blockers or []]
    if preflight_failed or any(blockers):
        return "failed"
    return "passed"
