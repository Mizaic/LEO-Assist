"""Fail pipeline runs that still say running after the lease died.

Atlas:
  DI: DI-36F80B95
  DO: DO-CE65B1F2
  VT: VT-0203C659
"""

FAIL_STALE_RUNNING_PIPELINE_RUNS = """
MATCH (r:PipelineRun {status: 'running'})
WHERE r.updated_at < datetime() - duration({minutes: $stale_after_minutes})
  AND NOT EXISTS {
    MATCH (r)-[:HAS_STAGE]->(live:PipelineStageRun)
    WHERE live.status = 'running'
      AND live.lease_until IS NOT NULL
      AND live.lease_until > datetime()
  }
SET r.status = 'failed',
    r.error = coalesce(r.error, 'stale_running_no_active_lease'),
    r.updated_at = datetime()
WITH r
OPTIONAL MATCH (r)-[:HAS_STAGE]->(s:PipelineStageRun)
WHERE s.status = 'running'
SET s.status = 'failed',
    s.errors_json = coalesce(s.errors_json, $errors_json),
    s.updated_at = datetime(),
    s.lease_until = null
RETURN collect(DISTINCT r.id) AS run_ids
"""
