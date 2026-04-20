"""Persist safety-net signals as SafetyNetAlert nodes.

Atlas trace:
  DO: DO-B711D180
  DI: DI-CE0A08E5
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-B711D180")

Writes the output of detect_safety_net_signals to Neo4j so it can be
reviewed from the /safety-netting worklist and acknowledged through
the audit-quality router.

Every node is keyed on alert_id so repeat runs are idempotent.
Each node is linked to its Patient (HAS_SAFETY_NET_ALERT) and, when
the signal is episode-scoped, to its EpisodeOfCare (FOR_EPISODE).

See DI-LEO-AI-127, R-LEO-AI-087, VT-LEO-AI-122.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Iterable

logger = logging.getLogger(__name__)


_Q_UPSERT_ALERT = """
MATCH (p:Patient {id: $patient_id})
MERGE (a:SafetyNetAlert {alert_id: $alert_id})
ON CREATE SET
    a.alert_type   = $alert_type,
    a.severity     = $severity,
    a.description  = $description,
    a.status       = 'open',
    a.actioned     = false,
    a.needs_review = true,
    a.created_at   = datetime(),
    a.source       = 'safety_net_subgraph'
ON MATCH SET
    a.alert_type   = $alert_type,
    a.severity     = $severity,
    a.description  = $description
MERGE (p)-[:HAS_SAFETY_NET_ALERT]->(a)
RETURN a.alert_id AS alert_id
"""

_Q_LINK_EPISODE = """
MATCH (a:SafetyNetAlert {alert_id: $alert_id})
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})
MERGE (a)-[:FOR_EPISODE]->(ep)
"""


def _derive_alert_id(signal: dict[str, Any]) -> str:
    """Deterministic alert_id so repeat runs are idempotent."""
    existing = str(signal.get("alert_id") or "").strip()
    if existing:
        return existing
    key = ":".join(
        [
            str(signal.get("patient_id") or ""),
            str(signal.get("episode_id") or ""),
            str(signal.get("type") or ""),
        ]
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"safety_net:{key}"))


def _normalise_signal(
    patient_id: str,
    signal: dict[str, Any],
) -> dict[str, Any]:
    """Project a raw signal into the parameter dict for _Q_UPSERT_ALERT."""
    alert_id = _derive_alert_id({**signal, "patient_id": patient_id})
    return {
        "patient_id": patient_id,
        "alert_id": alert_id,
        "alert_type": str(signal.get("type") or "safety_net_generic"),
        "severity": str(signal.get("severity") or "warning"),
        "description": str(signal.get("description") or ""),
        "episode_id": str(signal.get("episode_id") or "") or None,
    }


def persist_safety_net_alerts(
    patient_id: str,
    signals: Iterable[dict[str, Any]],
    patient_client: Any,
) -> list[str]:
    """MERGE SafetyNetAlert nodes for the given signals.

    Returns the list of alert_id values that were written (including
    MATCH updates).
    """
    pid = str(patient_id or "").strip()
    if not pid:
        return []
    written: list[str] = []
    for raw in signals or []:
        params = _normalise_signal(pid, raw)
        try:
            rows = patient_client.run(_Q_UPSERT_ALERT, **params) or []
        except Exception as exc:
            logger.error(
                "persist_safety_net_alerts: upsert failed for %s: %s",
                params.get("alert_id"),
                exc,
            )
            continue
        alert_id = ""
        for row in rows:
            alert_id = str(row.get("alert_id") or "")
            break
        if not alert_id:
            continue
        written.append(alert_id)
        episode_id = params.get("episode_id")
        if episode_id:
            try:
                patient_client.run(
                    _Q_LINK_EPISODE,
                    alert_id=alert_id,
                    episode_id=episode_id,
                )
            except Exception as exc:
                logger.error(
                    "persist_safety_net_alerts: FOR_EPISODE link failed "
                    "for alert %s episode %s: %s",
                    alert_id,
                    episode_id,
                    exc,
                )
    logger.info(
        "persist_safety_net_alerts: wrote %d alerts for patient %s",
        len(written),
        pid,
    )
    return written
