"""Cypher for Validation Lab findings and clinical pipeline-run open.

Atlas:
  DI: DI-562F2C9E
  DO: DO-4FD76836
"""

UPSERT_VALIDATION_FINDING = """
MERGE (f:ValidationFinding {id: $finding_id})
SET f.run_id = $run_id,
    f.stage_id = $stage_id,
    f.category = $category,
    f.target = $target,
    f.note = $note,
    f.status = $status,
    f.updated_at = datetime(),
    f.created_at = coalesce(f.created_at, datetime())
WITH f
OPTIONAL MATCH (lab:ValidationLabRun {id: $run_id})
FOREACH (_ IN CASE WHEN lab IS NULL THEN [] ELSE [1] END |
  MERGE (lab)-[:HAS_FINDING]->(f)
)
WITH f
OPTIONAL MATCH (pipe:PipelineRun {id: $run_id})
FOREACH (_ IN CASE WHEN pipe IS NULL THEN [] ELSE [1] END |
  MERGE (pipe)-[:HAS_FINDING]->(f)
)
RETURN f {
  .id, .run_id, .stage_id, .category, .target, .note, .status,
  .created_at, .updated_at
} AS finding
"""

LIST_FINDINGS_FOR_RUN = """
MATCH (f:ValidationFinding {run_id: $run_id})
RETURN f {
  .id, .run_id, .stage_id, .category, .target, .note, .status,
  .created_at, .updated_at
} AS finding
ORDER BY f.created_at DESC
"""

LIST_OPEN_FINDINGS = """
MATCH (f:ValidationFinding)
WHERE f.status IN $statuses
RETURN f {
  .id, .run_id, .stage_id, .category, .target, .note, .status,
  .created_at, .updated_at
} AS finding
ORDER BY f.created_at DESC
LIMIT $limit
"""

LIST_RECENT_PIPELINE_RUNS = """
MATCH (r:PipelineRun)
WHERE r.id IS NOT NULL
OPTIONAL MATCH (p:Patient)-[:HAS_ENCOUNTER]->(:Encounter)-[:TRIGGERED]->(r)
OPTIONAL MATCH (p2:Patient)-[:HAS_ENCOUNTER]->(:Encounter)<-[:FOR_ENCOUNTER]-(r)
OPTIONAL MATCH (p3:Patient)-[:HAS_PIPELINE_RUN]->(r)
OPTIONAL MATCH (p4:Patient {id: r.patient_id})
WITH r, coalesce(p, p2, p3, p4) AS patient
OPTIONAL MATCH (rr:ReferralRequest)-[:FOR_PATIENT]->(patient)
WITH r, patient, head(collect(rr)) AS rr
RETURN r.id AS run_id,
       coalesce(r.status, '') AS status,
       toString(coalesce(r.created_at, r.updated_at, datetime())) AS created_at,
       coalesce(r.plan_definition_id, r.plan_id, '') AS plan_id,
       coalesce(patient.id, '') AS patient_id,
       coalesce(patient.displayName, patient.name, '') AS patient_name,
       coalesce(patient.nhsNumber, '') AS nhs_number,
       coalesce(rr.ubrn, rr.id, '') AS ubrn
ORDER BY r.created_at DESC
LIMIT $limit
"""

LIST_CLINICAL_PATIENTS = """
MATCH (r:PipelineRun)
WHERE r.id IS NOT NULL
OPTIONAL MATCH (p:Patient)-[:HAS_ENCOUNTER]->(:Encounter)-[:TRIGGERED]->(r)
OPTIONAL MATCH (p2:Patient)-[:HAS_ENCOUNTER]->(:Encounter)<-[:FOR_ENCOUNTER]-(r)
OPTIONAL MATCH (p3:Patient)-[:HAS_PIPELINE_RUN]->(r)
OPTIONAL MATCH (p4:Patient {id: r.patient_id})
WITH r, coalesce(p, p2, p3, p4) AS patient
WHERE patient IS NOT NULL
WITH patient, r
ORDER BY r.created_at DESC
WITH patient, collect(r) AS runs
WITH patient, runs[0] AS latest, size(runs) AS run_count
OPTIONAL MATCH (rr:ReferralRequest)-[:FOR_PATIENT]->(patient)
WITH patient, latest, run_count, head(collect(rr)) AS rr
WITH patient, latest, run_count,
     coalesce(patient.displayName, patient.name, '') AS patient_name,
     coalesce(patient.nhsNumber, '') AS nhs_number,
     coalesce(rr.ubrn, rr.id, '') AS ubrn
WHERE $compact = '' OR (
  replace(replace(toUpper(nhs_number), ' ', ''), '-', '') = $compact
  OR replace(replace(toUpper(ubrn), ' ', ''), '-', '') = $compact
  OR toUpper(toString(patient.id)) = toUpper($lookup)
  OR toUpper(patient_name) CONTAINS toUpper($lookup)
)
RETURN coalesce(patient.id, '') AS patient_id,
       patient_name,
       nhs_number,
       ubrn,
       latest.id AS run_id,
       coalesce(latest.status, '') AS status,
       toString(coalesce(latest.created_at, latest.updated_at, datetime()))
         AS created_at,
       coalesce(latest.plan_definition_id, latest.plan_id, '') AS plan_id,
       run_count
ORDER BY latest.created_at DESC
LIMIT $limit
"""

GET_PIPELINE_RUN_EXISTS = """
MATCH (r:PipelineRun {id: $run_id})
RETURN r.id AS run_id, coalesce(r.status, '') AS status
LIMIT 1
"""

FIND_PIPELINE_RUNS_BY_IDENTIFIER = """
CALL {
  MATCH (p:Patient)
  WHERE $compact <> ''
    AND (
      replace(replace(toString(coalesce(p.nhsNumber, '')), ' ', ''), '-', '')
        = $compact
      OR toUpper(toString(p.id)) = toUpper($lookup)
    )
  RETURN p
  UNION
  MATCH (rr:ReferralRequest)
  WHERE $compact <> ''
    AND (
      replace(replace(toString(coalesce(rr.ubrn, '')), ' ', ''), '-', '')
        = $compact
      OR replace(replace(toString(coalesce(rr.id, '')), ' ', ''), '-', '')
        = $compact
      OR toString(rr.id) = $lookup
      OR toString(rr.ubrn) = $lookup
    )
  MATCH (rr)-[:FOR_PATIENT]->(p:Patient)
  RETURN p
  UNION
  MATCH (cr:CommunicationRequest)
  WHERE $compact <> ''
    AND (
      replace(replace(toString(coalesce(cr.ubrn, '')), ' ', ''), '-', '')
        = $compact
      OR toString(cr.ubrn) = $lookup
    )
  MATCH (cr)-[:FOR_PATIENT]->(p:Patient)
  RETURN p
  UNION
  MATCH (c:ValidationCase)
  WHERE $compact <> ''
    AND (
      replace(replace(toString(coalesce(c.nhs_number, '')), ' ', ''), '-', '')
        = $compact
      OR replace(replace(toString(coalesce(c.ubrn, '')), ' ', ''), '-', '')
        = $compact
    )
  MATCH (p:Patient {id: c.patient_id})
  RETURN p
}
WITH DISTINCT p
OPTIONAL MATCH (p)-[:HAS_PIPELINE_RUN]->(linked:PipelineRun)
OPTIONAL MATCH (byPid:PipelineRun {patient_id: p.id})
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(:Encounter)-[:TRIGGERED]->(trig:PipelineRun)
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(:Encounter)<-[:FOR_ENCOUNTER]-(enc:PipelineRun)
WITH p,
     collect(DISTINCT linked) + collect(DISTINCT byPid)
     + collect(DISTINCT trig) + collect(DISTINCT enc) AS bag
UNWIND bag AS run
WITH p, run
WHERE run IS NOT NULL
OPTIONAL MATCH (rr2:ReferralRequest)-[:FOR_PATIENT]->(p)
WITH p, run, head(collect(rr2)) AS rr
RETURN DISTINCT run.id AS run_id,
       coalesce(run.status, '') AS status,
       toString(coalesce(run.created_at, run.updated_at, datetime()))
         AS created_at,
       coalesce(run.plan_definition_id, run.plan_id, '') AS plan_id,
       coalesce(p.id, '') AS patient_id,
       coalesce(p.displayName, p.name, '') AS patient_name,
       coalesce(p.nhsNumber, '') AS nhs_number,
       coalesce(rr.ubrn, rr.id, '') AS ubrn
ORDER BY run.created_at DESC
LIMIT $limit
"""
