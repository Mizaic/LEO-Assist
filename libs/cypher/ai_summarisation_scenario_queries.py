"""Cypher for AI summarisation scenario run history."""

AI_SUMMARISATION_SCENARIO_CONSTRAINTS = [
    "CREATE CONSTRAINT ai_sbar_scenario_run_id IF NOT EXISTS "
    "FOR (r:AiSummarisationScenarioRun) REQUIRE r.run_id IS UNIQUE",
    "CREATE INDEX ai_sbar_scenario_run_status IF NOT EXISTS "
    "FOR (r:AiSummarisationScenarioRun) ON (r.status)",
    "CREATE INDEX ai_sbar_scenario_run_triggered IF NOT EXISTS "
    "FOR (r:AiSummarisationScenarioRun) ON (r.triggered_at)",
]

CREATE_SCENARIO_RUN = """
MERGE (r:AiSummarisationScenarioRun {run_id: $run_id})
SET r.status = $status,
    r.case_ids_json = $case_ids_json,
    r.child_runs_json = $child_runs_json,
    r.guideline_id = $guideline_id,
    r.completeness_domain = $completeness_domain,
    r.completeness_subdomain = $completeness_subdomain,
    r.plan_definition_id = $plan_definition_id,
    r.triggered_by = $triggered_by,
    r.triggered_at = $triggered_at,
    r.updated_at = $triggered_at
RETURN r.run_id AS run_id
"""

UPDATE_SCENARIO_RUN_STATUS = """
MATCH (r:AiSummarisationScenarioRun {run_id: $run_id})
SET r.status = $status,
    r.completed_count = $completed_count,
    r.failed_count = $failed_count,
    r.running_count = $running_count,
    r.updated_at = $updated_at
FOREACH (_ IN CASE WHEN $completed_at IS NULL THEN [] ELSE [1] END |
  SET r.completed_at = $completed_at
)
RETURN r.run_id AS run_id
"""

LIST_SCENARIO_RUNS = """
MATCH (r:AiSummarisationScenarioRun)
RETURN r.run_id AS run_id,
       r.status AS status,
       r.case_ids_json AS case_ids_json,
       r.child_runs_json AS child_runs_json,
       r.guideline_id AS guideline_id,
       r.completeness_domain AS completeness_domain,
       r.completeness_subdomain AS completeness_subdomain,
       r.plan_definition_id AS plan_definition_id,
       r.triggered_by AS triggered_by,
       r.triggered_at AS triggered_at,
       r.updated_at AS updated_at,
       r.completed_at AS completed_at,
       r.completed_count AS completed_count,
       r.failed_count AS failed_count,
       r.running_count AS running_count
ORDER BY r.triggered_at DESC
LIMIT $limit
"""

GET_SCENARIO_RUN = """
MATCH (r:AiSummarisationScenarioRun {run_id: $run_id})
RETURN r.run_id AS run_id,
       r.status AS status,
       r.case_ids_json AS case_ids_json,
       r.child_runs_json AS child_runs_json,
       r.guideline_id AS guideline_id,
       r.completeness_domain AS completeness_domain,
       r.completeness_subdomain AS completeness_subdomain,
       r.plan_definition_id AS plan_definition_id,
       r.triggered_by AS triggered_by,
       r.triggered_at AS triggered_at,
       r.updated_at AS updated_at,
       r.completed_at AS completed_at,
       r.completed_count AS completed_count,
       r.failed_count AS failed_count,
       r.running_count AS running_count
LIMIT 1
"""
