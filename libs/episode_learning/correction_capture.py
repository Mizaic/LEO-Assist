"""Normalise audit-trail rows into labelled training events.

Atlas trace:
  DI: DI-8A5FCF4F (12-component, defence-in-depth episode detector)

Reads the :AuditEvent rows produced by the EpisodeManualAttach /
EpisodeManualDetach flow (with the new correction_target field) and
turns them into per-site, per-correction-target CorrectionEvent
records. The output is consumed by scorer_retrain.py.

The capture step is intentionally pure on the input rows so it can
be unit-tested without a live Neo4j session.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

logger = logging.getLogger(__name__)

VALID_TARGETS = frozenset(
    {
        "detector_boundary",
        "sbar_text",
        "coding_decision",
        "canonical_code",
        "other",
    }
)


@dataclass(frozen=True)
class CorrectionEvent:
    """A single, normalised correction extracted from the audit trail."""

    audit_id: str
    event_type: str
    correction_target: str
    site_key: str
    episode_id: str
    patient_id: str
    actor_role: str
    label: int  # +1 = "model was wrong", 0 = "model was right (touched but kept)"
    captured_at: datetime
    context: dict[str, Any] = field(default_factory=dict)


def _safe_load_json(text: Any) -> dict[str, Any]:
    if not text:
        return {}
    if isinstance(text, dict):
        return text
    try:
        loaded = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {}


def _resolve_site_key(before: dict[str, Any], after: dict[str, Any]) -> str:
    """Pick the most informative site key from the before/after snapshots."""
    for snapshot in (after, before):
        for key in ("suspected_site", "site_key", "cancer_type"):
            value = snapshot.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
    return "unknown"


def _resolve_label(event_type: str) -> int:
    """Attach attaches/detaches are both signals that the prior detector
    output was wrong (the reviewer had to touch it). We treat any manual
    edit as label=1; the fine-grained correction_target tells the
    scorer WHAT was wrong. Future revisions can split this further
    (e.g. revert events as label=0)."""
    et = (event_type or "").strip().lower()
    if et in {"episodemanualrevert", "episode_manual_revert"}:
        return 0
    return 1


def _coerce_target(target: Any) -> str:
    if not isinstance(target, str):
        return "other"
    candidate = target.strip().lower()
    if candidate not in VALID_TARGETS:
        return "other"
    return candidate


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def capture_corrections_from_audit(
    audit_rows: Iterable[dict[str, Any]],
) -> list[CorrectionEvent]:
    """Turn raw audit-trail rows into normalised CorrectionEvent objects.

    Each row should be the property map of an :AuditEvent node. Rows
    missing the required keys (audit_id, type, episode_id) are dropped
    with a debug log. The function is deterministic and order-preserving
    on the input.
    """
    events: list[CorrectionEvent] = []
    for raw in audit_rows:
        audit_id = str(raw.get("id") or raw.get("audit_id") or "").strip()
        event_type = str(raw.get("type") or raw.get("event_type") or "").strip()
        episode_id = str(raw.get("episode_id") or "").strip()
        if not (audit_id and event_type and episode_id):
            logger.debug("Dropping audit row missing required keys: %r", raw)
            continue
        before = _safe_load_json(raw.get("before_json"))
        after = _safe_load_json(raw.get("after_json"))
        site_key = _resolve_site_key(before, after)
        correction_target = _coerce_target(raw.get("correction_target"))
        label = _resolve_label(event_type)
        captured_at = _coerce_datetime(
            raw.get("created_at_iso") or raw.get("created_at")
        )
        context = {
            "before": before,
            "after": after,
            "notes": str(raw.get("notes") or ""),
        }
        events.append(
            CorrectionEvent(
                audit_id=audit_id,
                event_type=event_type,
                correction_target=correction_target,
                site_key=site_key,
                episode_id=episode_id,
                patient_id=str(raw.get("patient_id") or ""),
                actor_role=str(raw.get("actor_role") or ""),
                label=label,
                captured_at=captured_at,
                context=context,
            )
        )
    return events
