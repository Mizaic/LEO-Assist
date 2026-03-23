"""Cypher queries for exclusion detector audit persistence.

Persists per-encounter ExclusionResult audit trails and patient-level
episode status from the exclusion detector fail-safe path.
"""

# Persist an ExclusionResult on the EpisodeOfCare node
UPSERT_EPISODE_EXCLUSION_RESULT = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})
SET ep.exclusion_outcome          = $outcome,
    ep.exclusion_confidence       = $confidence,
    ep.exclusion_method           = $detection_method,
    ep.exclusion_referral_date    = $referral_date,
    ep.exclusion_window_end       = $window_end,
    ep.exclusion_encounters_scanned = $encounters_scanned,
    ep.exclusion_encounters_skipped = $encounters_skipped,
    ep.exclusion_run_at           = datetime(),
    ep.updated_at                 = datetime()
"""

# Persist a per-encounter audit node linked to the episode
CREATE_ENCOUNTER_EXCLUSION_AUDIT = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})
MERGE (a:ExclusionAudit {
    episode_id: $episode_id,
    encounter_id: $encounter_id
})
SET a.outcome           = $outcome,
    a.confidence        = $confidence,
    a.detection_method  = $detection_method,
    a.model_a_outcome   = $model_a_outcome,
    a.model_b_outcome   = $model_b_outcome,
    a.evidence_text     = $evidence_text,
    a.reasoning         = $reasoning,
    a.encounter_date    = $encounter_date,
    a.updated_at        = datetime(),
    a.created_at        = coalesce(a.created_at, datetime())
MERGE (ep)-[:HAS_EXCLUSION_AUDIT]->(a)
"""

# Route conflicting exclusion result to HITL queue
CREATE_EXCLUSION_HITL_TASK = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})
MERGE (t:HITLTask {task_id: $task_id})
ON CREATE SET
    t.task_type    = 'exclusion_conflict',
    t.episode_id   = $episode_id,
    t.patient_id   = $patient_id,
    t.status       = 'pending',
    t.priority     = 80,
    t.reason       = $reason,
    t.created_at   = datetime(),
    t.updated_at   = datetime()
ON MATCH SET
    t.status       = CASE WHEN t.status IN ['resolved', 'dismissed'] THEN t.status ELSE 'pending' END,
    t.updated_at   = datetime()
MERGE (ep)-[:HAS_HITL_TASK]->(t)
"""

# List pending HITL tasks by type
LIST_HITL_TASKS_BY_TYPE = """
MATCH (t:HITLTask)
WHERE ($task_type IS NULL OR t.task_type = $task_type)
  AND ($status IS NULL OR t.status = $status)
RETURN t.task_id    AS task_id,
       t.task_type  AS task_type,
       t.episode_id AS episode_id,
       t.patient_id AS patient_id,
       t.status     AS status,
       t.priority   AS priority,
       t.reason     AS reason,
       t.created_at AS created_at,
       t.updated_at AS updated_at
ORDER BY t.priority DESC, t.created_at DESC
LIMIT $limit
"""

# Resolve a HITL task
RESOLVE_HITL_TASK = """
MATCH (t:HITLTask {task_id: $task_id})
SET t.status       = $status,
    t.resolved_by  = $resolved_by,
    t.resolution   = $resolution,
    t.updated_at   = datetime()
RETURN t.task_id AS task_id, t.status AS status
"""

# Delete all HITL tasks (e.g. queue reset from old pipeline)
DELETE_ALL_HITL_TASKS = """
MATCH (t:HITLTask)
DETACH DELETE t
"""
