"""Cypher for extraction-quality review tasks and pause unlock.

Atlas trace:
  DI: DI-4A012A59
  DO: DO-E7824FED
"""

CREATE_EXTRACTION_REVIEW_TASK = """
MERGE (t:HITLTask {task_id: $task_id})
ON CREATE SET
    t.task_type = 'extraction_quality_review',
    t.status = 'pending',
    t.priority = 10,
    t.created_at = datetime()
SET
    t.run_id = $run_id,
    t.patient_id = $patient_id,
    t.plan_definition_id = $plan_definition_id,
    t.step_id = $step_id,
    t.next_action_id = $next_action_id,
    t.reason = $reason,
    t.draft_entities_json = $draft_entities_json,
    t.document_quality_json = $document_quality_json,
    t.source_text = $source_text,
    t.updated_at = datetime()
RETURN t.task_id AS task_id
"""

GET_EXTRACTION_REVIEW_TASK = """
MATCH (t:HITLTask {task_id: $task_id})
RETURN t.task_id AS task_id,
       t.task_type AS task_type,
       t.status AS status,
       t.resumed_at AS resumed_at,
       t.run_id AS run_id,
       t.patient_id AS patient_id,
       t.plan_definition_id AS plan_definition_id,
       t.step_id AS step_id,
       t.next_action_id AS next_action_id,
       t.reason AS reason,
       t.draft_entities_json AS draft_entities_json,
       t.document_quality_json AS document_quality_json,
       coalesce(t.source_text, '') AS source_text
"""

RESOLVE_EXTRACTION_REVIEW_TASK = """
MATCH (t:HITLTask {task_id: $task_id})
SET t.status = 'resolved',
    t.resolved_by = $resolved_by,
    t.resumed_at = datetime(),
    t.updated_at = datetime()
RETURN t.task_id AS task_id, t.status AS status
"""

UNLOCK_PAUSED_EXTRACTION_STAGE = """
MATCH (r:PipelineRun {id: $run_id})-[:HAS_STAGE]->(s:PipelineStageRun)
WHERE s.step_id = $step_id AND s.status = 'paused'
SET s.status = 'completed',
    s.output_json = $output_json,
    s.next_action_ids_json = $next_action_ids_json,
    r.status = 'running',
    s.updated_at = datetime()
RETURN s.step_id AS step_id
"""

CANCEL_EXTRACTION_REVIEW_TASK = """
MATCH (t:HITLTask {task_id: $task_id})
WHERE t.status = 'pending'
  AND t.task_type = 'extraction_quality_review'
SET t.status = 'cancelled',
    t.cancel_reason = $reason,
    t.cancelled_by = $cancelled_by,
    t.cancelled_at = datetime(),
    t.updated_at = datetime()
RETURN t.task_id AS task_id, t.status AS status
"""

CANCEL_PAUSED_EXTRACTION_STAGE = """
MATCH (r:PipelineRun {id: $run_id})-[:HAS_STAGE]->(s:PipelineStageRun)
WHERE s.step_id = $step_id AND s.status = 'paused'
SET s.status = 'cancelled',
    r.status = 'cancelled',
    s.updated_at = datetime()
RETURN s.step_id AS step_id
"""

GET_REVIEW_IDENTIFIERS = """
OPTIONAL MATCH (p:Patient {id: $patient_id})
OPTIONAL MATCH (rr:ReferralRequest)-[:FOR_PATIENT]->(p)
WITH p, head(collect(rr)) AS rr
RETURN coalesce(p.nhsNumber, p.nhs_number, '') AS nhs_number,
       coalesce(rr.ubrn, '') AS ubrn
"""

GET_RUN_ORG_SERVICE_IDS = """
MATCH (run:PipelineRun {id: $run_id})-[:FOR]->(rr:ReferralRequest)
OPTIONAL MATCH (rr)-[:REQUESTED_BY]->(org:Organization)
OPTIONAL MATCH (rr)-[:FOR_SERVICE]->(svc)
RETURN coalesce(org.id, '') AS organization_id,
       coalesce(svc.id, '') AS service_id
LIMIT 1
"""
