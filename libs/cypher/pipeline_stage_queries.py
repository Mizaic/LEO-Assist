"""Cypher for durable workflow run and stage persistence.

Atlas trace:
  DO: DO-CE65B1F2
  DI: DI-36F80B95
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-36F80B95")
"""

ENSURE_PIPELINE_RUN_CONSTRAINT = """
CREATE CONSTRAINT pipeline_run_id IF NOT EXISTS
FOR (r:PipelineRun) REQUIRE r.id IS UNIQUE
"""

ENSURE_PIPELINE_RUN_ADMISSION_KEY_CONSTRAINT = """
CREATE CONSTRAINT pipeline_run_admission_key IF NOT EXISTS
FOR (r:PipelineRun) REQUIRE r.admission_key IS UNIQUE
"""

ENSURE_PIPELINE_STAGE_CONSTRAINT = """
CREATE CONSTRAINT pipeline_stage_run_id IF NOT EXISTS
FOR (s:PipelineStageRun) REQUIRE s.id IS UNIQUE
"""

ENSURE_OUTBOX_EVENT_CONSTRAINT = """
CREATE CONSTRAINT pipeline_outbox_event_id IF NOT EXISTS
FOR (o:OutboxEvent) REQUIRE o.id IS UNIQUE
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
    r.admission_key = coalesce($admission_key, r.admission_key),
    r.status = CASE
      WHEN coalesce(r.status, 'running') IN
        ['completed', 'failed', 'cancelled', 'poisoned']
        AND $status = 'running'
      THEN r.status
      ELSE $status
    END,
    r.updated_at = datetime()
WITH r
OPTIONAL MATCH (p:Patient {id: $patient_id})
FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END |
  MERGE (p)-[:HAS_PIPELINE_RUN]->(r)
)
RETURN r.id AS id, r.status AS status
"""

ADMIT_PIPELINE_RUN = """
MERGE (r:PipelineRun {admission_key: $admission_key})
ON CREATE SET
  r.id = $run_id,
  r.created_at = datetime(),
  r.workflow_id = $workflow_id,
  r.plan_definition_id = $plan_definition_id,
  r.patient_id = $patient_id,
  r.encounter_id = $encounter_id,
  r.source = $source,
  r.case_id = $case_id,
  r.parent_run_id = $parent_run_id,
  r.policy_version = $policy_version,
  r.plan_version_id = $plan_version_id,
  r.version_selection_reason = $version_selection_reason,
  r.execution_manifest_json = $execution_manifest_json,
  r.status = 'running',
  r.first_step_enqueued = false,
  r.updated_at = datetime()
ON MATCH SET
  r.updated_at = datetime()
WITH r
OPTIONAL MATCH (p:Patient {id: $patient_id})
FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END |
  MERGE (p)-[:HAS_PIPELINE_RUN]->(r)
)
WITH r
OPTIONAL MATCH (v:PlanDefinitionVersion {id: $plan_version_id})
WHERE $plan_version_id IS NOT NULL AND trim($plan_version_id) <> ''
FOREACH (_ IN CASE WHEN v IS NULL THEN [] ELSE [1] END |
  MERGE (r)-[:USED_WORKFLOW]->(v)
)
RETURN r.id AS run_id,
       r.id = $run_id AS created,
       coalesce(r.first_step_enqueued, false) AS first_step_enqueued,
       r.status AS status
"""

GET_PIPELINE_RUN_EXECUTION_MANIFEST = """
MATCH (r:PipelineRun {id: $run_id})
RETURN coalesce(r.execution_manifest_json, '') AS execution_manifest_json
LIMIT 1
"""

CLAIM_FIRST_STEP_ENQUEUE = """
MATCH (r:PipelineRun {id: $run_id})
WHERE coalesce(r.first_step_enqueued, false) = false
  AND NOT coalesce(r.status, 'running') IN
    ['completed', 'failed', 'cancelled', 'poisoned']
SET r.first_step_enqueued = true,
    r.updated_at = datetime()
RETURN true AS enqueued
UNION
MATCH (r:PipelineRun {id: $run_id})
WHERE coalesce(r.first_step_enqueued, false) = true
RETURN false AS enqueued
"""

# Legacy unconditional start -- prefer CLAIM_PIPELINE_STAGE_RUN.
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

# Single-flight claim for Service Bus redelivery safety (DI-36F80B95).
# Outcomes: claimed | already_completed | busy | poisoned
CLAIM_PIPELINE_STAGE_RUN = """
MATCH (r:PipelineRun {id: $run_id})
MERGE (s:PipelineStageRun {id: $stage_run_id})
ON CREATE SET s.created_at = datetime(),
              s.status = 'pending',
              s.lease_generation = 0
MERGE (r)-[:HAS_STAGE]->(s)
WITH r, s
CALL {
  WITH r, s
  WITH r, s WHERE s.status = 'completed'
  RETURN 'already_completed' AS outcome,
         s.output_json AS output_json,
         s.next_action_ids_json AS next_action_ids_json,
         coalesce(s.next_published, false) AS next_published,
         coalesce(s.lease_owner, '') AS lease_owner,
         coalesce(s.lease_generation, 0) AS lease_generation
  UNION
  WITH r, s
  WITH r, s WHERE s.status = 'poisoned'
  RETURN 'poisoned' AS outcome,
         null AS output_json,
         null AS next_action_ids_json,
         false AS next_published,
         coalesce(s.lease_owner, '') AS lease_owner,
         coalesce(s.lease_generation, 0) AS lease_generation
  UNION
  WITH r, s
  WITH r, s
  WHERE coalesce(s.status, 'pending') <> 'completed'
    AND coalesce(s.status, 'pending') <> 'poisoned'
    AND (
      coalesce(s.status, 'pending') IN ['pending', 'failed', 'paused']
      OR (
        s.status = 'running'
        AND (
          s.lease_until IS NULL
          OR s.lease_until < datetime()
          OR coalesce(s.lease_owner, '') = $lease_owner
        )
      )
    )
  WITH r, s,
       CASE
         WHEN s.status = 'running'
           AND coalesce(s.lease_owner, '') = $lease_owner
           AND s.lease_until IS NOT NULL
           AND s.lease_until >= datetime()
         THEN coalesce(s.attempt, 1)
         ELSE coalesce(s.attempt, 0) + 1
       END AS next_attempt
  CALL {
    WITH r, s, next_attempt
    WITH r, s, next_attempt WHERE next_attempt > $max_attempts
    SET s.status = 'poisoned',
        s.updated_at = datetime(),
        r.status = 'poisoned',
        r.updated_at = datetime()
    RETURN 'poisoned' AS outcome,
           null AS output_json,
           null AS next_action_ids_json,
           false AS next_published,
           coalesce(s.lease_owner, '') AS lease_owner,
           coalesce(s.lease_generation, 0) AS lease_generation
    UNION
    WITH r, s, next_attempt
    WITH r, s, next_attempt WHERE next_attempt <= $max_attempts
    SET s.status = 'running',
        s.lease_owner = $lease_owner,
        s.lease_generation = CASE
          WHEN s.status = 'running'
            AND coalesce(s.lease_owner, '') = $lease_owner
            AND s.lease_until IS NOT NULL
            AND s.lease_until >= datetime()
          THEN coalesce(s.lease_generation, 1)
          ELSE coalesce(s.lease_generation, 0) + 1
        END,
        s.lease_until = datetime() + duration({seconds: $lease_seconds}),
        s.started_at = coalesce(s.started_at, datetime()),
        s.attempt = next_attempt,
        s.step_id = $step_id,
        s.event_type = $event_type,
        s.input_json = $input_json,
        s.run_id = $run_id,
        s.next_published = false,
        s.updated_at = datetime()
    RETURN 'claimed' AS outcome,
           null AS output_json,
           null AS next_action_ids_json,
           false AS next_published,
           s.lease_owner AS lease_owner,
           s.lease_generation AS lease_generation
  }
  RETURN outcome, output_json, next_action_ids_json, next_published,
         lease_owner, lease_generation
  UNION
  WITH r, s
  WITH r, s WHERE s.status = 'running'
    AND s.lease_until IS NOT NULL
    AND s.lease_until >= datetime()
    AND coalesce(s.lease_owner, '') <> $lease_owner
  RETURN 'busy' AS outcome,
         null AS output_json,
         null AS next_action_ids_json,
         false AS next_published,
         coalesce(s.lease_owner, '') AS lease_owner,
         coalesce(s.lease_generation, 0) AS lease_generation
}
RETURN outcome, output_json, next_action_ids_json, next_published,
       lease_owner, lease_generation
"""

RENEW_PIPELINE_STAGE_LEASE = """
MATCH (s:PipelineStageRun {id: $stage_run_id})
WHERE s.status = 'running'
  AND coalesce(s.lease_owner, '') = $lease_owner
  AND coalesce(s.lease_generation, 0) = $lease_generation
SET s.lease_until = datetime() + duration({seconds: $lease_seconds}),
    s.updated_at = datetime()
RETURN s.id AS id
"""

COMPLETE_PIPELINE_STAGE_RUN = """
MATCH (r:PipelineRun {id: $run_id})
MATCH (s:PipelineStageRun {id: $stage_run_id})
CALL {
  WITH r, s
  WITH r, s
  WHERE s.status = 'running'
    AND coalesce(s.lease_owner, '') = $lease_owner
    AND coalesce(s.lease_generation, 0) = $lease_generation
  SET s.status = $status,
      s.output_json = $output_json,
      s.output_refs_json = $output_refs_json,
      s.errors_json = $errors_json,
      s.warnings_json = $warnings_json,
      s.metrics_json = $metrics_json,
      s.next_action_ids_json = $next_action_ids_json,
      s.next_published = $next_published,
      s.completed_by = $lease_owner,
      s.lease_owner = null,
      s.lease_until = null,
      s.completed_at = datetime(),
      s.updated_at = datetime(),
      r.status = $run_status,
      r.assessment_id = coalesce($assessment_id, r.assessment_id),
      r.updated_at = datetime()
  WITH r, s
  UNWIND $outbox_events AS evt
  MERGE (o:OutboxEvent {id: evt.id})
  ON CREATE SET o.created_at = datetime()
  SET o.run_id = $run_id,
      o.stage_run_id = $stage_run_id,
      o.target_action_id = evt.target_action_id,
      o.edge_version = evt.edge_version,
      o.message_id = evt.message_id,
      o.queue_name = evt.queue_name,
      o.body_json = evt.body_json,
      o.status = coalesce(evt.status, 'pending'),
      o.updated_at = datetime()
  MERGE (s)-[:HAS_OUTBOX_EVENT]->(o)
  WITH 'completed' AS outcome, count(o) AS outbox_created
  RETURN outcome, outbox_created
  UNION
  WITH r, s
  WITH r, s
  WHERE NOT (
    s.status = 'running'
    AND coalesce(s.lease_owner, '') = $lease_owner
    AND coalesce(s.lease_generation, 0) = $lease_generation
  )
  RETURN 'stale_lease' AS outcome, 0 AS outbox_created
}
RETURN outcome, outbox_created
"""

GET_PENDING_OUTBOX_FOR_STAGE = """
MATCH (s:PipelineStageRun {id: $stage_run_id})-[:HAS_OUTBOX_EVENT]->(o:OutboxEvent)
WHERE o.status = 'pending'
RETURN o.id AS id,
       o.message_id AS message_id,
       o.queue_name AS queue_name,
       o.body_json AS body_json
ORDER BY o.target_action_id ASC
"""

MARK_OUTBOX_EVENT_SENT = """
MATCH (o:OutboxEvent {id: $outbox_id})
SET o.status = 'sent',
    o.sent_at = datetime(),
    o.updated_at = datetime()
RETURN o.id AS id
"""

HAS_PENDING_OUTBOX_FOR_STAGE = """
MATCH (s:PipelineStageRun {id: $stage_run_id})-[:HAS_OUTBOX_EVENT]->(o:OutboxEvent)
WHERE o.status = 'pending'
RETURN count(o) > 0 AS has_pending
LIMIT 1
"""

MARK_STAGE_NEXT_PUBLISHED = """
MATCH (s:PipelineStageRun {id: $stage_run_id})
SET s.next_published = true,
    s.updated_at = datetime()
RETURN s.id AS id
"""

GET_SUCCESSOR_STAGE_STATUSES = """
MATCH (r:PipelineRun {id: $run_id})-[:HAS_STAGE]->(s:PipelineStageRun)
WHERE s.step_id IN $step_ids
RETURN s.step_id AS step_id, s.status AS status
"""

HAS_ANY_OUTBOX_FOR_STAGE = """
MATCH (s:PipelineStageRun {id: $stage_run_id})-[:HAS_OUTBOX_EVENT]->(o:OutboxEvent)
RETURN count(o) > 0 AS has_outbox
LIMIT 1
"""

GET_SENT_OUTBOX_FOR_STAGE = """
MATCH (s:PipelineStageRun {id: $stage_run_id})-[:HAS_OUTBOX_EVENT]->(o:OutboxEvent)
WHERE o.status = 'sent'
RETURN o.id AS id,
       o.target_action_id AS target_action_id,
       o.edge_version AS edge_version,
       toString(o.sent_at) AS sent_at
ORDER BY o.sent_at DESC
"""

COUNT_OUTBOX_FOR_STAGE = """
MATCH (s:PipelineStageRun {id: $stage_run_id})-[:HAS_OUTBOX_EVENT]->(o:OutboxEvent)
RETURN count(o) AS outbox_count
"""

GET_STUCK_COMPLETED_STAGE_FOR_RUN = """
MATCH (pr:PipelineRun {id: $run_id})
WHERE pr.status = 'running'
OPTIONAL MATCH (pr)-[:HAS_STAGE]->(active:PipelineStageRun)
WHERE active.status = 'running'
   OR (
     coalesce(active.lease_owner, '') <> ''
     AND active.lease_until IS NOT NULL
     AND active.lease_until > datetime()
   )
WITH pr, count(active) AS active_n
WHERE active_n = 0
OPTIONAL MATCH (pr)-[:HAS_STAGE]->(s:PipelineStageRun)
WHERE s.status = 'completed'
WITH pr, s
ORDER BY coalesce(s.completed_at, s.updated_at, s.created_at) DESC
WITH pr, collect(s)[0] AS last
WHERE last IS NOT NULL
  AND coalesce(last.next_action_ids_json, '') <> ''
  AND coalesce(last.next_action_ids_json, '') <> '[]'
RETURN last.id AS stage_run_id,
       last.step_id AS step_id,
       last.next_action_ids_json AS next_action_ids_json,
       coalesce(last.next_published, false) AS next_published,
       pr.patient_id AS patient_id,
       pr.plan_definition_id AS plan_definition_id,
       pr.encounter_id AS encounter_id,
       pr.case_id AS case_id,
       coalesce(pr.first_step_enqueued, false) AS first_step_enqueued
LIMIT 1
"""

GET_ZERO_STAGE_RUNNING_RUN = """
MATCH (pr:PipelineRun {id: $run_id})
WHERE pr.status = 'running'
OPTIONAL MATCH (pr)-[:HAS_STAGE]->(s:PipelineStageRun)
WITH pr, count(s) AS stage_n
WHERE stage_n = 0
RETURN pr.id AS run_id,
       pr.patient_id AS patient_id,
       pr.plan_definition_id AS plan_definition_id,
       pr.encounter_id AS encounter_id,
       pr.case_id AS case_id,
       coalesce(pr.first_step_enqueued, false) AS first_step_enqueued
LIMIT 1
"""

CLEAR_FIRST_STEP_ENQUEUE = """
MATCH (r:PipelineRun {id: $run_id})
WHERE coalesce(r.first_step_enqueued, false) = true
  AND NOT coalesce(r.status, 'running') IN
    ['completed', 'failed', 'cancelled', 'poisoned']
  AND NOT EXISTS { (r)-[:HAS_STAGE]->(:PipelineStageRun) }
SET r.first_step_enqueued = false,
    r.updated_at = datetime()
RETURN r.id AS id
"""

ENSURE_PIPELINE_STAGE_OUTBOX = """
MATCH (s:PipelineStageRun {id: $stage_run_id})
WHERE s.status = 'completed'
WITH s
UNWIND $outbox_events AS evt
MERGE (o:OutboxEvent {id: evt.id})
ON CREATE SET o.created_at = datetime(),
              o.run_id = $run_id,
              o.stage_run_id = $stage_run_id,
              o.target_action_id = evt.target_action_id,
              o.edge_version = evt.edge_version,
              o.message_id = evt.message_id,
              o.queue_name = evt.queue_name,
              o.body_json = evt.body_json,
              o.status = 'pending',
              o.updated_at = datetime()
MERGE (s)-[:HAS_OUTBOX_EVENT]->(o)
RETURN sum(CASE WHEN o.status = 'pending' AND o.sent_at IS NULL THEN 1 ELSE 0 END)
       AS outbox_ensured
"""

# Live stage checklist for Validation Lab run sheet (DI-2289D095).
# worker_id: live lease_owner while running, else durable completed_by.
LIST_PIPELINE_STAGE_RUNS = """
MATCH (:PipelineRun {id: $run_id})-[:HAS_STAGE]->(s:PipelineStageRun)
RETURN s.step_id AS step_id,
       s.event_type AS event_type,
       coalesce(s.status, 'pending') AS status,
       coalesce(s.lease_owner, s.completed_by, '') AS worker_id,
       toString(s.started_at) AS started_at,
       toString(s.completed_at) AS completed_at
ORDER BY coalesce(s.started_at, s.created_at) ASC
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
