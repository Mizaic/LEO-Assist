"""Safety-critical data quality query tools."""

from __future__ import annotations

from services.neo4j_mcp.tools.query_pack_common import _result, run_patient


def dq_shell_patients(limit: int = 200) -> dict:
    rows = run_patient(
        """
        MATCH (p:Patient)
        WHERE NOT EXISTS { MATCH (p)-[:HAS_ENCOUNTER]->(:Encounter) }
        RETURN toString(p.id) AS patient_id
        ORDER BY patient_id
        LIMIT $limit
        """,
        limit=limit,
    )
    return _result(
        "dq_shell_patients",
        "safety",
        f"Found {len(rows)} shell patients without encounters.",
        rows,
    )


def dq_patients_with_encounters_no_documents(limit: int = 200) -> dict:
    rows = run_patient(
        """
        MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
        WITH p, count(DISTINCT e) AS encounter_count,
             sum(CASE WHEN EXISTS { MATCH (e)-[:DOCUMENTS]->() } THEN 1 ELSE 0 END) AS coded_encounters
        WHERE encounter_count > 0 AND coded_encounters = 0
        RETURN toString(p.id) AS patient_id, encounter_count
        ORDER BY encounter_count DESC, patient_id
        LIMIT $limit
        """,
        limit=limit,
    )
    return _result(
        "dq_patients_with_encounters_no_documents",
        "safety",
        f"Found {len(rows)} patients with encounters but no DOCUMENTS links.",
        rows,
    )


def dq_coding_completeness_by_site_month(min_encounters: int = 25) -> dict:
    rows = run_patient(
        """
        MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
        OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp)
        WITH coalesce(toString(gp.id), 'unknown') AS org_id,
             substring(toString(e.date), 0, 7) AS year_month,
             count(DISTINCT e) AS encounter_total,
             sum(CASE WHEN EXISTS { MATCH (e)-[:DOCUMENTS]->() } THEN 1 ELSE 0 END) AS coded_total
        WHERE encounter_total >= $min_encounters
        RETURN org_id, year_month, encounter_total, coded_total,
               round(100.0 * toFloat(coded_total) / toFloat(encounter_total), 2) AS coverage_pct
        ORDER BY coverage_pct ASC, encounter_total DESC
        """,
        min_encounters=min_encounters,
    )
    return _result(
        "dq_coding_completeness_by_site_month",
        "safety",
        "Calculated encounter coding coverage by org and month.",
        rows,
    )


def dq_assertion_contradictions_same_concept(limit: int = 200) -> dict:
    rows = run_patient(
        """
        MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[d:DOCUMENTS]->(c)
        WITH p, c, collect(DISTINCT
            CASE
              WHEN toLower(toString(d.context)) CONTAINS '"assertion":"present"' THEN 'present'
              WHEN toLower(toString(d.context)) CONTAINS '"assertion":"absent"' THEN 'absent'
              WHEN toLower(toString(d.context)) CONTAINS '"assertion":"refuted"' THEN 'refuted'
              WHEN toLower(toString(d.context)) CONTAINS '"assertion":"possible"' THEN 'possible'
              WHEN toLower(toString(d.context)) CONTAINS '"assertion":"historical"' THEN 'historical'
              ELSE 'unknown'
            END
        ) AS assertions, count(DISTINCT e) AS encounter_count
        WHERE 'present' IN assertions
          AND any(a IN assertions WHERE a IN ['absent', 'refuted', 'possible', 'historical'])
        RETURN toString(p.id) AS patient_id,
               coalesce(toString(c.conceptId), toString(c.id), 'unknown') AS concept_id,
               assertions, encounter_count
        ORDER BY encounter_count DESC, patient_id
        LIMIT $limit
        """,
        limit=limit,
    )
    return _result(
        "dq_assertion_contradictions_same_concept",
        "safety",
        f"Detected {len(rows)} patient-concept assertion contradictions.",
        rows,
    )


def dq_high_risk_low_confidence_codes(min_confidence: float = 0.7, limit: int = 200) -> dict:
    rows = run_patient(
        """
        MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[d:DOCUMENTS]->(c)
        WHERE coalesce(d.confidence, 1.0) < $min_confidence
          AND (
            toLower(coalesce(c.semanticTag, c.semantic_tag, '')) IN ['disease', 'disorder', 'clinicalfinding', 'finding']
            OR toLower(coalesce(c.name, c.fsn, '')) CONTAINS 'cancer'
            OR toLower(coalesce(c.name, c.fsn, '')) CONTAINS 'malignan'
          )
        RETURN toString(p.id) AS patient_id,
               toString(e.id) AS encounter_id,
               coalesce(toString(c.conceptId), toString(c.id), 'unknown') AS concept_id,
               coalesce(c.name, c.fsn, 'unknown') AS term,
               coalesce(c.semanticTag, c.semantic_tag, 'unknown') AS semantic_tag,
               toFloat(d.confidence) AS confidence
        ORDER BY confidence ASC
        LIMIT $limit
        """,
        min_confidence=min_confidence,
        limit=limit,
    )
    return _result(
        "dq_high_risk_low_confidence_codes",
        "safety",
        f"Found {len(rows)} high-risk low-confidence coding links.",
        rows,
    )


def dq_stale_unactioned_safety_alerts(stale_days: int = 14, limit: int = 500) -> dict:
    rows = run_patient(
        """
        MATCH (a:SafetyNetAlert)
        WHERE coalesce(a.actioned, false) = false
          AND duration.between(datetime(substring(toString(a.created_at), 0, 19)), datetime()).days >= $stale_days
        RETURN coalesce(toString(a.id), toString(a.alert_id), 'unknown') AS alert_id,
               coalesce(toString(a.patient_id), 'unknown') AS patient_id,
               coalesce(toString(a.rule_name), toString(a.type), 'unknown') AS rule_name,
               toString(a.created_at) AS created_at,
               duration.between(datetime(substring(toString(a.created_at), 0, 19)), datetime()).days AS age_days
        ORDER BY age_days DESC
        LIMIT $limit
        """,
        stale_days=stale_days,
        limit=limit,
    )
    return _result(
        "dq_stale_unactioned_safety_alerts",
        "safety",
        f"Found {len(rows)} stale unactioned safety-net alerts.",
        rows,
    )


TOOLS = [
    {
        "name": "dq_shell_patients",
        "description": "Safety audit: list shell patients with no encounters.",
        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 200}}},
        "fn": dq_shell_patients,
    },
    {
        "name": "dq_patients_with_encounters_no_documents",
        "description": "Safety audit: patients with encounters but no DOCUMENTS links.",
        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 200}}},
        "fn": dq_patients_with_encounters_no_documents,
    },
    {
        "name": "dq_coding_completeness_by_site_month",
        "description": "Safety audit: coding coverage by org and month.",
        "inputSchema": {"type": "object", "properties": {"min_encounters": {"type": "integer", "default": 25}}},
        "fn": dq_coding_completeness_by_site_month,
    },
    {
        "name": "dq_assertion_contradictions_same_concept",
        "description": "Safety audit: detect present-vs-nonpresent concept contradictions.",
        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 200}}},
        "fn": dq_assertion_contradictions_same_concept,
    },
    {
        "name": "dq_high_risk_low_confidence_codes",
        "description": "Safety audit: high-risk concepts coded below confidence threshold.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_confidence": {"type": "number", "default": 0.7},
                "limit": {"type": "integer", "default": 200},
            },
        },
        "fn": dq_high_risk_low_confidence_codes,
    },
    {
        "name": "dq_stale_unactioned_safety_alerts",
        "description": "Safety audit: stale unactioned safety-net alerts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "stale_days": {"type": "integer", "default": 14},
                "limit": {"type": "integer", "default": 500},
            },
        },
        "fn": dq_stale_unactioned_safety_alerts,
    },
]

