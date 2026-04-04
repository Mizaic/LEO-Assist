"""Alert escalation logic for the audit quality loop (Loop 1).

Called at the end of audit Phase 4 and via
POST /operations/quality/runs/escalation-check.

Escalation rules
----------------
- Unacknowledged for > 48h  -> escalation_level = 1
- Unacknowledged for > 14d  -> escalation_level = 2, loop1_audit auto-paused,
                               new SafetyNetAlert with alert_type=escalation_auto_pause
- Unacknowledged for > 7d   -> log structured warning (email in future sprint)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_Q_UNACK_ALERTS = """
MATCH (a:SafetyNetAlert)
WHERE (a.alert_type STARTS WITH 'coding_'
    OR a.alert_type = 'audit_cost_cap')
  AND a.acknowledged_at IS NULL
RETURN
    toString(a.alert_id) AS alert_id,
    a.alert_type AS alert_type,
    toString(a.created_at) AS created_at,
    a.escalation_level AS escalation_level
"""

_Q_SET_ESCALATION_LEVEL = """
MATCH (a:SafetyNetAlert {alert_id: $alert_id})
SET a.escalation_level = $level
"""

_Q_PAUSE_LOOP1 = """
MATCH (c:LoopConfig {loop_id: 'loop1_audit'})
SET c.enabled = false, c.updated_by = 'escalation_auto_pause', c.updated_at = datetime()
"""

_Q_CREATE_ESCALATION_ALERT = """
MERGE (a:SafetyNetAlert {alert_id: $alert_id})
ON CREATE SET
    a.alert_type    = 'escalation_auto_pause',
    a.severity      = 'critical',
    a.description   = $description,
    a.escalation_level = 2,
    a.created_at    = datetime()
RETURN a.alert_id AS alert_id
"""

_SECONDS_48H = 48 * 3600
_SECONDS_7D = 7 * 24 * 3600
_SECONDS_14D = 14 * 24 * 3600


def _age_seconds(created_at_str: str | None) -> float:
    if not created_at_str:
        return 0.0
    try:
        dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(tz=timezone.utc) - dt).total_seconds()
    except Exception:
        return 0.0


def run_escalation_check(neo_client) -> dict[str, Any]:
    """Evaluate all unacknowledged alerts and apply escalation rules.

    Returns a summary dict with counts of actions taken.
    """
    counts: dict[str, int] = {
        "escalated_48h": 0,
        "email_due": 0,
        "auto_paused": 0,
        "auto_pause_alerts_created": 0,
    }

    with neo_client.session() as session:
        rows = list(session.run(_Q_UNACK_ALERTS))

    alert_14d_ids: list[str] = []

    for row in rows:
        alert_id = str(row["alert_id"] or "")
        created_at = str(row.get("created_at") or "")
        current_level = int(row.get("escalation_level") or 0)
        age = _age_seconds(created_at)

        if age >= _SECONDS_14D:
            alert_14d_ids.append(alert_id)
            if current_level < 2:
                _set_escalation(neo_client, alert_id, 2)
                counts["escalated_48h"] += 1
        elif age >= _SECONDS_7D:
            logger.warning(
                "audit.alert.escalation_email_due alert_id=%s age_days=%.1f",
                alert_id, age / 86400,
            )
            counts["email_due"] += 1
            if current_level < 1:
                _set_escalation(neo_client, alert_id, 1)
                counts["escalated_48h"] += 1
        elif age >= _SECONDS_48H:
            if current_level < 1:
                _set_escalation(neo_client, alert_id, 1)
                counts["escalated_48h"] += 1

    if alert_14d_ids:
        _pause_loop1(neo_client)
        counts["auto_paused"] = 1
        _create_auto_pause_alert(neo_client, alert_14d_ids)
        counts["auto_pause_alerts_created"] = 1
        logger.warning(
            "audit.escalation_auto_pause: loop1_audit disabled. "
            "Overdue alerts: %s",
            ", ".join(alert_14d_ids[:5]),
        )

    logger.info(
        "Escalation check complete: %s", counts,
    )
    return {"escalation_check": "complete", "counts": counts}


def _set_escalation(neo_client, alert_id: str, level: int) -> None:
    try:
        with neo_client.session() as session:
            session.run(_Q_SET_ESCALATION_LEVEL, alert_id=alert_id, level=level)
        logger.info("Alert %s escalated to level %d", alert_id, level)
    except Exception as exc:
        logger.error("Failed to set escalation level for %s: %s", alert_id, exc)


def _pause_loop1(neo_client) -> None:
    try:
        with neo_client.session() as session:
            session.run(_Q_PAUSE_LOOP1)
        logger.warning("loop1_audit auto-paused by escalation logic")
    except Exception as exc:
        logger.error("Failed to pause loop1_audit: %s", exc)


def _create_auto_pause_alert(
    neo_client, overdue_ids: list[str]
) -> None:
    alert_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"escalation_auto_pause:{','.join(sorted(overdue_ids[:5]))}",
    ))
    description = (
        f"loop1_audit auto-paused: {len(overdue_ids)} alert(s) "
        f"unacknowledged for > 14 days. "
        f"First overdue: {overdue_ids[0]}"
    )
    try:
        with neo_client.session() as session:
            session.run(
                _Q_CREATE_ESCALATION_ALERT,
                alert_id=alert_id,
                description=description,
            )
    except Exception as exc:
        logger.error("Failed to create auto-pause alert: %s", exc)
