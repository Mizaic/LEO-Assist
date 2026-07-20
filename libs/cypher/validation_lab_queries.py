"""Cypher for Validation Lab cases, runs, and gold.

Atlas: DO-3A70C3DD / DI-724CD8A5 / DI-9138BAC9

Every case is one synthetic test patient: optional PMH (pmh_json),
zero or more background encounters (encounters_json), and exactly one
referral document (referral_text) -- the only thing the pipeline ever
processes.
"""

UPSERT_VALIDATION_CASE = """
MERGE (c:ValidationCase {id: $case_id})
SET c.title = $title,
    c.referral_text = $referral_text,
    c.pmh_json = $pmh_json,
    c.encounters_json = $encounters_json,
    c.patient_id = $patient_id,
    c.encounter_id = $encounter_id,
    c.referral_id = $referral_id,
    c.document_reference_id = $document_reference_id,
    c.chunk_ids = $chunk_ids,
    c.background_encounter_ids = $background_encounter_ids,
    c.plan_id = $plan_id,
    c.gold_json = $gold_json,
    c.updated_at = datetime(),
    c.created_at = coalesce(c.created_at, datetime()),
    c.created_by = coalesce(c.created_by, $created_by)
RETURN c
"""

GET_VALIDATION_CASE = """
MATCH (c:ValidationCase {id: $case_id})
OPTIONAL MATCH (c)-[:HAS_LAB_RUN]->(r:ValidationLabRun)
WITH c, r ORDER BY r.created_at DESC
RETURN c {
  .id, .title, .referral_text, .pmh_json, .encounters_json,
  .patient_id, .encounter_id, .referral_id, .document_reference_id,
  .chunk_ids, .background_encounter_ids, .plan_id,
  .gold_json, .created_at, .updated_at, .created_by
} AS case,
collect(r {
  .id, .persist_mode, .plan_id, .phase_ids, .status,
  .outputs_json, .created_at, .error_message
})[0..20] AS runs
"""

LIST_VALIDATION_CASES = """
MATCH (c:ValidationCase)
RETURN c {
  .id, .title, .patient_id, .plan_id, .updated_at, .created_at
} AS case
ORDER BY c.updated_at DESC
LIMIT $limit
"""

UPSERT_LAB_RUN = """
MATCH (c:ValidationCase {id: $case_id})
MERGE (r:ValidationLabRun {id: $run_id})
SET r.persist_mode = $persist_mode,
    r.plan_id = $plan_id,
    r.phase_ids = $phase_ids,
    r.status = $status,
    r.outputs_json = $outputs_json,
    r.error_message = $error_message,
    r.created_at = coalesce(r.created_at, datetime()),
    r.updated_at = datetime()
MERGE (c)-[:HAS_LAB_RUN]->(r)
RETURN r
"""

GET_LAB_RUN = """
MATCH (c:ValidationCase {id: $case_id})
      -[:HAS_LAB_RUN]->(r:ValidationLabRun {id: $run_id})
RETURN r {
  .id, .persist_mode, .plan_id, .phase_ids, .status,
  .outputs_json, .created_at, .error_message
} AS run,
c {
  .id, .title, .patient_id, .gold_json,
  .encounter_id, .referral_id,
  .document_reference_id, .chunk_ids
} AS case
"""

SET_CASE_GOLD = """
MATCH (c:ValidationCase {id: $case_id})
SET c.gold_json = $gold_json,
    c.updated_at = datetime()
RETURN c.id AS id
"""

UPDATE_VALIDATION_CASE = """
MATCH (c:ValidationCase {id: $case_id})
SET c.title = coalesce($title, c.title),
    c.referral_text = coalesce($referral_text, c.referral_text),
    c.plan_id = coalesce($plan_id, c.plan_id),
    c.gold_json = coalesce($gold_json, c.gold_json),
    c.updated_at = datetime()
RETURN c
"""

# Graph shape probe for VT assertions (patient graph). Referral is the
# only submission shape now -- see docs/REFERRAL-PIPELINE-INTEGRATION.md.
PROBE_REFERRAL_SHAPE = """
MATCH (p:Patient {id: $patient_id})
OPTIONAL MATCH (rr:ReferralRequest {id: $referral_id})-[:FOR_PATIENT]->(p)
OPTIONAL MATCH (p)-[:HAS_DOCUMENT_REFERENCE]->(dr:DocumentReference {id: $dr_id})
OPTIONAL MATCH (dr)-[:HAS_CHUNK]->(ch:Chunk)
OPTIONAL MATCH (p)-[:HAS_CONDITION|HAS_MEDICATION_STATEMENT|HAS_ALLERGY]->(pmh)
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(bg:Encounter)
WHERE bg.id <> $encounter_id
RETURN p.id AS patient_id,
       rr.id AS referral_id,
       dr.id AS document_reference_id,
       collect(DISTINCT ch {.id, .text}) AS chunks,
       collect(DISTINCT pmh {.id, .term, .snomed_concept_id}) AS pmh_items,
       collect(DISTINCT bg {.id, .label, .text}) AS background_encounters
"""
