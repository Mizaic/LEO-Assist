"""EncounterCandidate / ReviewTask / Approval / Change CRUD queries.

Centralised from services/api/app/models/neo4j_schema.py.
"""

UPSERT_CANDIDATE = """
MERGE (c:EncounterCandidate {candidate_id: $candidate_id})
SET c.patient_id = $patient_id,
    c.encounter_id = $encounter_id,
    c.date = $date,
    c.source_hash = $source_hash,
    c.deidentified_hash = $deidentified_hash,
    c.deidentified_text = $deidentified_text,
    c.approval_status = $approval_status,
    c.hard_fail_reasons = $hard_fail_reasons,
    c.warning_reasons = $warning_reasons,
    c.sentences_json = $sentences_json,
    c.llm_usage_json = $llm_usage_json,
    c.extraction_source = $extraction_source,
    c.extraction_model_name = $extraction_model_name,
    c.extraction_model_version = $extraction_model_version,
    c.contract_version = $contract_version,
    c.run_id = $run_id,
    c.updated_at = datetime(),
    c.created_at = coalesce(c.created_at, datetime())
"""

CREATE_REVIEW_TASK = """
MATCH (c:EncounterCandidate {candidate_id: $candidate_id})
MERGE (c)-[:HAS_TASK]->(t:ReviewTask {task_id: $task_id})
ON CREATE SET
    t.priority = $priority,
    t.status = $status,
    t.assigned_reviewer = $assigned_reviewer,
    t.warning_count = $warning_count,
    t.created_at = datetime(),
    t.updated_at = datetime()
ON MATCH SET
    t.priority = $priority,
    t.warning_count = $warning_count,
    t.updated_at = datetime(),
    t.status = CASE WHEN t.status IN ['approved', 'rejected', 'escalated'] THEN t.status ELSE $status END
"""

APPEND_CHANGE = """
MATCH (c:EncounterCandidate {candidate_id: $candidate_id})
CREATE (chg:Change {
    change_id: $change_id,
    event_type: $event_type,
    actor: $actor,
    reason: $reason,
    timestamp: datetime($timestamp),
    before_hash: $before_hash,
    after_hash: $after_hash,
    version_bundle_json: $version_bundle_json
})
CREATE (c)-[:HAS_CHANGE]->(chg)
"""

APPEND_APPROVAL = """
MATCH (c:EncounterCandidate {candidate_id: $candidate_id})-[:HAS_TASK]->(t:ReviewTask {task_id: $task_id})
CREATE (a:Approval {
    approval_id: $approval_id,
    action: $action,
    reviewer: $reviewer,
    reason: $reason,
    status_after: $status_after,
    timestamp: datetime($timestamp),
    before_hash: $before_hash,
    after_hash: $after_hash
})
CREATE (t)-[:HAS_APPROVAL]->(a)
SET t.status = $status_after, t.updated_at = datetime(), c.approval_status = $status_after
"""

LIST_TASKS = """
MATCH (c:EncounterCandidate)-[:HAS_TASK]->(t:ReviewTask)
WHERE ($status IS NULL OR t.status = $status)
  AND ($patient_id IS NULL OR c.patient_id = $patient_id)
WITH c, t
ORDER BY
    CASE WHEN t.status = 'pending' THEN 0 ELSE 1 END ASC,
    t.updated_at DESC
WITH c.patient_id AS patient_id, c.encounter_id AS encounter_id, collect({c: c, t: t})[0] AS latest
WITH latest.c AS c, latest.t AS t
RETURN t.task_id AS task_id,
       c.candidate_id AS candidate_id,
       c.patient_id AS patient_id,
       c.encounter_id AS encounter_id,
       t.priority AS priority,
       t.status AS status,
       t.warning_count AS warning_count,
       t.created_at AS created_at,
       t.updated_at AS updated_at
ORDER BY t.priority DESC, c.date DESC
LIMIT $limit
"""

GET_TASK_DETAIL = """
MATCH (c:EncounterCandidate)-[:HAS_TASK]->(t:ReviewTask {task_id: $task_id})
RETURN t.task_id AS task_id,
       c.candidate_id AS candidate_id,
       c.patient_id AS patient_id,
       c.encounter_id AS encounter_id,
       t.priority AS priority,
       t.status AS status,
       t.warning_count AS warning_count,
       t.created_at AS created_at,
       t.updated_at AS updated_at,
       c AS candidate
"""

GET_AUDIT_TIMELINE = """
MATCH (c:EncounterCandidate {candidate_id: $candidate_id})
OPTIONAL MATCH (c)-[:HAS_CHANGE]->(chg:Change)
OPTIONAL MATCH (c)-[:HAS_TASK]->(:ReviewTask)-[:HAS_APPROVAL]->(a:Approval)
RETURN c.candidate_id AS candidate_id,
       collect(DISTINCT chg) AS changes,
       collect(DISTINCT a) AS approvals
"""

LIST_APPROVED_CANDIDATES = """
MATCH (c:EncounterCandidate)
WHERE c.approval_status = 'approved'
RETURN c
ORDER BY c.patient_id, c.encounter_id
"""

LIST_APPROVED_CANDIDATES_FOR_PATIENT = """
MATCH (c:EncounterCandidate)
WHERE c.approval_status = 'approved' AND c.patient_id = $patient_id
RETURN c
ORDER BY c.encounter_id
"""

# ---------------------------------------------------------------------------
# Gold dataset / extraction scorecard queries
# ---------------------------------------------------------------------------

GET_REVIEW_OUTCOME_COUNTS = """
MATCH (c:EncounterCandidate)-[:HAS_TASK]->(t:ReviewTask)-[:HAS_APPROVAL]->(a:Approval)
WITH c.candidate_id AS candidate_id,
     a.action       AS action,
     a.reviewer     AS reviewer,
     a.timestamp    AS ts
ORDER BY ts DESC
WITH candidate_id, collect({action: action, reviewer: reviewer})[0] AS latest
RETURN latest.action  AS action,
       latest.reviewer AS reviewer,
       count(*)        AS n
"""

GET_CANDIDATES_FOR_SCORECARD = """
MATCH (c:EncounterCandidate)
WHERE c.approval_status IN ['approved', 'rejected', 'escalated']
OPTIONAL MATCH (c)-[:HAS_TASK]->(t:ReviewTask)-[:HAS_APPROVAL]->(a:Approval)
WITH c,
     a.action   AS action,
     a.reviewer AS reviewer,
     a.timestamp AS ts
ORDER BY ts DESC
WITH c, collect({action: action, reviewer: reviewer})[0] AS latest_approval
RETURN c.candidate_id     AS candidate_id,
       c.patient_id       AS patient_id,
       c.approval_status  AS approval_status,
       c.sentences_json   AS sentences_json,
       c.warning_reasons  AS warning_reasons,
       c.date             AS date,
       latest_approval.action   AS last_action,
       latest_approval.reviewer AS reviewer
ORDER BY c.date DESC
"""
