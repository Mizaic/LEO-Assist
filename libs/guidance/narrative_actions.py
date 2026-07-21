"""Helpers for narrative (non-procedure) guidance actions.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")
"""

from __future__ import annotations

from typing import Any

from libs.terminology.local_concepts import is_narrative_action


def procedure_compliance_actions(actions: list[dict[str, Any]] | None) -> list[dict]:
    """Return only actions that may drive 'was the procedure done?' checks.

    Narrative actions (action_kind=narrative or LEO-ACT-* free-text) are
    display-only and must never be treated as ordered procedures.
    """
    out: list[dict] = []
    for action in actions or []:
        if not isinstance(action, dict):
            continue
        kind = action.get("action_kind")
        if is_narrative_action(kind if isinstance(kind, str) else None):
            continue
        out.append(action)
    return out


def display_action_label(action: dict[str, Any]) -> str:
    """Prefer free-text narrative wording when present."""
    if is_narrative_action(action.get("action_kind")):
        text = (action.get("action_text") or action.get("name") or "").strip()
        return text
    return (action.get("name") or action.get("action_text") or "").strip()
