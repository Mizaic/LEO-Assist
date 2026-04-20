"""Cypher queries for the CodingDecision audit trail.

Atlas trace:
  DO: DO-C7C1EBA2
  DI: DI-740BE510
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-C7C1EBA2")

Every autonomous-mode coding decision is recorded as a CodingDecision node
so the practice can audit what was coded, flagged, or skipped -- and why.
"""

UPSERT_CODING_DECISION = """
MERGE (d:CodingDecision {decision_id: $decision_id})
ON CREATE SET d.created_at = datetime()
SET d.encounter_id      = $encounter_id,
    d.patient_id_hash   = $patient_id_hash,
    d.entity_text       = $entity_text,
    d.entity_label      = $entity_label,
    d.assertion         = $assertion,
    d.tier              = $tier,
    d.decision          = $decision,
    d.reason            = $reason,
    d.terminology_score = $terminology_score,
    d.consensus_verdict = $consensus_verdict,
    d.model_ids         = $model_ids,
    d.updated_at        = datetime()
RETURN d.decision_id AS decision_id
"""

GET_CODING_DECISIONS_FOR_ENCOUNTER = """
MATCH (d:CodingDecision {encounter_id: $encounter_id})
RETURN d.decision_id      AS decision_id,
       d.entity_text       AS entity_text,
       d.entity_label      AS entity_label,
       d.assertion         AS assertion,
       d.tier              AS tier,
       d.decision          AS decision,
       d.reason            AS reason,
       d.terminology_score AS terminology_score,
       d.consensus_verdict AS consensus_verdict,
       d.model_ids         AS model_ids,
       d.created_at        AS created_at
ORDER BY d.created_at
"""

GET_CODING_DECISION_STATS = """
MATCH (d:CodingDecision)
WHERE d.created_at >= datetime($since)
RETURN d.tier     AS tier,
       d.decision AS decision,
       d.reason   AS reason,
       count(d)   AS cnt
ORDER BY tier, decision, reason
"""

COUNT_AUDIT_FLAGGED = """
MATCH (d:CodingDecision {decision: 'coded_with_flag'})
WHERE d.created_at >= datetime($since)
RETURN count(d) AS flagged
"""
