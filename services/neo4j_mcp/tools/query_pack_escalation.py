"""Escalation quality and variation query tools.

Atlas trace:
  DO: DO-5F438C17
  DI: DI-5700882E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-5F438C17")
"""

from __future__ import annotations

from services.neo4j_mcp.tools.query_pack_common import _result, run_patient


def dq_escalation_yield_by_rule(min_alerts: int = 20, limit: int = 200) -> dict:
    rows = run_patient(
        """
        MATCH (a:SafetyNetAlert)
        WITH coalesce(toString(a.rule_name), toString(a.type), 'unknown') AS rule_name,
             count(*) AS alert_count,
             sum(CASE WHEN coalesce(a.actioned, false) = true THEN 1 ELSE 0 END) AS actioned_count
        WHERE alert_count >= $min_alerts
        RETURN rule_name, alert_count, actioned_count,
               round(100.0 * toFloat(actioned_count) / toFloat(alert_count), 2) AS action_rate_pct
        ORDER BY action_rate_pct ASC, alert_count DESC
        LIMIT $limit
        """,
        min_alerts=min_alerts,
        limit=limit,
    )
    return _result(
        "dq_escalation_yield_by_rule",
        "escalation",
        "Calculated alert-to-action yield by rule.",
        rows,
    )


def dq_repeat_escalations_no_state_change(repeat_threshold: int = 3, limit: int = 200) -> dict:
    rows = run_patient(
        """
        MATCH (a:SafetyNetAlert)
        WITH coalesce(toString(a.patient_id), 'unknown') AS patient_id,
             coalesce(toString(a.rule_name), toString(a.type), 'unknown') AS rule_name,
             coalesce(toString(a.description), '') AS alert_signature,
             count(*) AS alert_count,
             max(toString(a.created_at)) AS last_seen
        WHERE alert_count >= $repeat_threshold
        RETURN patient_id, rule_name, alert_signature, alert_count, last_seen
        ORDER BY alert_count DESC, last_seen DESC
        LIMIT $limit
        """,
        repeat_threshold=repeat_threshold,
        limit=limit,
    )
    return _result(
        "dq_repeat_escalations_no_state_change",
        "escalation",
        f"Found {len(rows)} repeated escalation signatures above threshold.",
        rows,
    )


def dq_false_positive_proxy_by_rule(min_alerts: int = 15, limit: int = 200) -> dict:
    rows = run_patient(
        """
        MATCH (a:SafetyNetAlert)
        WITH coalesce(toString(a.rule_name), toString(a.type), 'unknown') AS rule_name,
             count(*) AS alert_count,
             sum(CASE WHEN toLower(toString(a.status)) IN ['dismissed', 'ignored', 'rejected'] THEN 1 ELSE 0 END) AS dismissed_count
        WHERE alert_count >= $min_alerts
        RETURN rule_name, alert_count, dismissed_count,
               round(100.0 * toFloat(dismissed_count) / toFloat(alert_count), 2) AS dismissed_rate_pct
        ORDER BY dismissed_rate_pct DESC, alert_count DESC
        LIMIT $limit
        """,
        min_alerts=min_alerts,
        limit=limit,
    )
    return _result(
        "dq_false_positive_proxy_by_rule",
        "escalation",
        "Calculated dismissed/ignored proxy rates by rule.",
        rows,
    )


def dq_escalation_parity_by_site(min_encounters: int = 50, limit: int = 200) -> dict:
    rows = run_patient(
        """
        MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp)
        OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
        OPTIONAL MATCH (a:SafetyNetAlert {patient_id: toString(p.id)})
        WITH toString(gp.id) AS org_id,
             count(DISTINCT e) AS encounter_count,
             count(DISTINCT a) AS alert_count
        WHERE encounter_count >= $min_encounters
        RETURN org_id, encounter_count, alert_count,
               round(100.0 * toFloat(alert_count) / toFloat(encounter_count), 2) AS alerts_per_100_encounters
        ORDER BY alerts_per_100_encounters DESC
        LIMIT $limit
        """,
        min_encounters=min_encounters,
        limit=limit,
    )
    return _result(
        "dq_escalation_parity_by_site",
        "escalation",
        "Calculated escalation rate parity by site.",
        rows,
    )


TOOLS = [
    {
        "name": "dq_escalation_yield_by_rule",
        "description": "Escalation audit: alert-to-action conversion by rule.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_alerts": {"type": "integer", "default": 20},
                "limit": {"type": "integer", "default": 200},
            },
        },
        "fn": dq_escalation_yield_by_rule,
    },
    {
        "name": "dq_repeat_escalations_no_state_change",
        "description": "Escalation audit: repeat alerts for same patient/signature.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repeat_threshold": {"type": "integer", "default": 3},
                "limit": {"type": "integer", "default": 200},
            },
        },
        "fn": dq_repeat_escalations_no_state_change,
    },
    {
        "name": "dq_false_positive_proxy_by_rule",
        "description": "Escalation audit: dismissed/ignored proxy rates by rule.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_alerts": {"type": "integer", "default": 15},
                "limit": {"type": "integer", "default": 200},
            },
        },
        "fn": dq_false_positive_proxy_by_rule,
    },
    {
        "name": "dq_escalation_parity_by_site",
        "description": "Escalation audit: site-level variation in alert rate.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_encounters": {"type": "integer", "default": 50},
                "limit": {"type": "integer", "default": 200},
            },
        },
        "fn": dq_escalation_parity_by_site,
    },
]

