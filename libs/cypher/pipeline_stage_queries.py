"""Cypher for durable workflow run and stage persistence."""

ENSURE_PIPELINE_RUN_CONSTRAINT = """
CREATE CONSTRAINT pipeline_run_id IF NOT EXISTS
FOR (r:PipelineRun) REQUIRE r.id IS UNIQUE
"""

ENSURE_PIPELINE_STAGE_CONSTRAINT = """
CREATE CONSTRAINT pipeline_stage_run_id IF NOT EXISTS
FOR (s:PipelineStageRun) REQUIRE s.id IS UNIQUE
"""

UPSERT_PIPELINE_RUN = """
MERGE (r:PipelineRun {id: $run_id})
ON CREATE SET r.created_at = datetime()
SET r.workflow_id = $workflow_id,
    r.plan_definition_id = $plan_definition_id,
    r.patient_id = $patient_id,
    r.encounter_id = $encounter_id,
    r.source = $source,
    r.case_id = $case_id,
    r.parent_run_id = $parent_run_id,
    r.status = $status,
    r.updated_at = datetime()
WITH r
OPTIONAL MATCH (p:Patient {id: $patient_id})
FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END |
  MERGE (p)-[:HAS_PIPELINE_RUN]->(r)
)
RETURN r.id AS id
"""

START_PIPELINE_STAGE_RUN = """
MATCH (r:PipelineRun {id: $run_id})
MERGE (s:PipelineStageRun {id: $stage_run_id})
ON CREATE SET s.created_at = datetime(),
              s.started_at = datetime()
SET s.run_id = $run_id,
    s.step_id = $step_id,
    s.event_type = $event_type,
    s.status = 'running',
    s.attempt = $attempt,
    s.input_json = $input_json,
    s.updated_at = datetime()
MERGE (r)-[:HAS_STAGE]->(s)
RETURN s.id AS id
"""

COMPLETE_PIPELINE_STAGE_RUN = """
MATCH (r:PipelineRun {id: $run_id})
MATCH (s:PipelineStageRun {id: $stage_run_id})
SET s.status = $status,
    s.output_json = $output_json,
    s.output_refs_json = $output_refs_json,
    s.errors_json = $errors_json,
    s.warnings_json = $warnings_json,
    s.metrics_json = $metrics_json,
    s.completed_at = datetime(),
    s.updated_at = datetime(),
    r.status = $run_status,
    r.assessment_id = coalesce($assessment_id, r.assessment_id),
    r.updated_at = datetime()
RETURN s.id AS id
"""

GET_PIPELINE_STAGE_OUTPUTS = """
MATCH (:PipelineRun {id: $run_id})-[:HAS_STAGE]->(s:PipelineStageRun)
WHERE s.status = 'completed'
RETURN s.step_id AS step_id,
       s.event_type AS event_type,
       s.output_json AS output_json,
       s.output_refs_json AS output_refs_json,
       s.completed_at AS completed_at
ORDER BY s.completed_at ASC
"""

GET_PIPELINE_STAGE_OUTPUT = """
MATCH (:PipelineRun {id: $run_id})-[:HAS_STAGE]->(s:PipelineStageRun)
WHERE s.step_id = $step_id
RETURN s.output_json AS output_json,
       s.output_refs_json AS output_refs_json,
       s.status AS status
ORDER BY s.completed_at DESC
LIMIT 1
"""

WRITE_PIPELINE_RUN_COMPLETION = """
MATCH (r:PipelineRun {id: $run_id})
SET r.completion_event_json = $completion_event_json,
    r.completed_at = datetime(),
    r.updated_at = datetime()
RETURN r.id AS id
"""
