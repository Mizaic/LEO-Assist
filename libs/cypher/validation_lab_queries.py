"""Cypher for Validation Lab cases, runs, and gold.

Atlas trace:
  DO: DO-3A70C3DD
  DI: DI-724CD8A5
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-3A70C3DD")

Atlas: DO-3A70C3DD / DI-724CD8A5 / DI-9138BAC9

Every case is one synthetic test patient: optional PMH (pmh_json),
zero or more background encounters (encounters_json), and exactly one
referral document (referral_text) -- the only thing the pipeline ever
processes.
"""

UPSERT_VALIDATION_CASE = """
MERGE (c:ValidationCase {id: $case_id})
SET c.title = $title,
    c.summary = $summary,
    c.tags = $tags,
    c.referral_text = $referral_text,
    c.case_type = $case_type,
    c.scenario_type = $scenario_type,
    c.pmh_json = $pmh_json,
    c.encounters_json = $encounters_json,
    c.ag_thread_json = $ag_thread_json,
    c.ag_response_text = $ag_response_text,
    c.gp_encounter_json = $gp_encounter_json,
    c.reason_for_submission = $reason_for_submission,
    c.verbalisation_seed = $verbalisation_seed,
    c.nhs_number = $nhs_number,
    c.gp_practice_name = $gp_practice_name,
    c.gp_encounter_id = $gp_encounter_id,
    c.patient_id = $patient_id,
    c.encounter_id = $encounter_id,
    c.referral_id = $referral_id,
    c.document_reference_id = $document_reference_id,
    c.communication_request_id = $communication_request_id,
    c.ubrn = $ubrn,
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
  .id, .title, .summary, .tags, .referral_text, .case_type, .scenario_type,
  .pmh_json,
  .encounters_json, .ag_thread_json, .ag_response_text,
  .gp_encounter_json, .reason_for_submission, .verbalisation_seed,
  .nhs_number, .gp_practice_name, .gp_encounter_id,
  .patient_id, .encounter_id, .referral_id, .document_reference_id,
  .communication_request_id, .ubrn,
  .chunk_ids, .background_encounter_ids, .plan_id,
  .gold_json, .created_at, .updated_at, .created_by
} AS case,
collect(r {
  .id, .persist_mode, .plan_id, .phase_ids, .status,
  .outputs_json, .created_at, .error_message,
  .llm_cost_usd, .llm_total_tokens, .llm_calls
})[0..20] AS runs
"""

LIST_VALIDATION_CASES = """
MATCH (c:ValidationCase)
OPTIONAL MATCH (c)-[:HAS_LAB_RUN]->(r:ValidationLabRun)
WITH c, r ORDER BY r.created_at DESC
WITH c, head(collect(r)) AS latest
RETURN {
  id: c.id,
  title: c.title,
  summary: coalesce(c.summary, ''),
  tags: coalesce(c.tags, []),
  referral_preview: CASE
    WHEN c.referral_text IS NULL THEN ''
    ELSE substring(c.referral_text, 0, 180)
  END,
  patient_id: c.patient_id,
  plan_id: c.plan_id,
  case_type: coalesce(c.case_type, 'referral'),
  scenario_type: coalesce(c.scenario_type, 'generic'),
  updated_at: c.updated_at,
  created_at: c.created_at,
  has_gold: CASE
    WHEN c.gold_json IS NULL OR c.gold_json = '' OR c.gold_json = '{}'
    THEN false
    ELSE true
  END,
  latest_run_id: latest.id,
  latest_run_status: latest.status,
  latest_llm_cost_usd: latest.llm_cost_usd,
  latest_llm_total_tokens: latest.llm_total_tokens,
  latest_llm_calls: latest.llm_calls
} AS case
ORDER BY c.updated_at DESC
LIMIT $limit
"""

DELETE_VALIDATION_CASE = """
MATCH (c:ValidationCase {id: $case_id})
OPTIONAL MATCH (c)-[:HAS_LAB_RUN]->(r:ValidationLabRun)
WITH c, c.patient_id AS patient_id, collect(r) AS runs
FOREACH (run IN runs | DETACH DELETE run)
DETACH DELETE c
RETURN patient_id
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
    r.llm_cost_usd = $llm_cost_usd,
    r.llm_total_tokens = $llm_total_tokens,
    r.llm_calls = $llm_calls,
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
  .outputs_json, .created_at, .error_message,
  .llm_cost_usd, .llm_total_tokens, .llm_calls
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
       collect(DISTINCT bg {.id, .label, .text, .encounter_kind}) AS background_encounters
"""

PROBE_AG_SHAPE = """
MATCH (p:Patient {id: $patient_id})
OPTIONAL MATCH (cr:CommunicationRequest {id: $communication_request_id})
      -[:FOR_PATIENT]->(p)
OPTIONAL MATCH (cr)-[:HAS_CONVERSATION]->(c:Communication)
OPTIONAL MATCH (cr)-[:HAS_RESPONSE]->(agr:AdviceAndGuidanceResponse)
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(gp:Encounter)
WHERE gp.encounter_kind = 'gp_consultation'
RETURN p.id AS patient_id,
       cr.id AS communication_request_id,
       cr.ubrn AS ubrn,
       collect(DISTINCT c {.id, .category, .note}) AS communications,
       agr.id AS agr_id,
       collect(DISTINCT gp {.id, .label, .text, .encounter_kind}) AS gp_encounters
"""
