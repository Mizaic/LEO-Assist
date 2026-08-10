"""Cypher for patient document pipeline re-runs.

Resolves referral-linked DocumentReference context for production
referral-received triggers from the Care patient viewer.
"""

RESOLVE_DOCUMENT_RUN_CONTEXT = """
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
MATCH (dr:DocumentReference {id: $document_reference_id})
WHERE EXISTS { MATCH (p)-[:HAS_DOCUMENT_REFERENCE]->(dr) }
   OR EXISTS {
     MATCH (p)<-[:FOR_PATIENT]-(:ReferralRequest)-[:HAS_DOCUMENT]->(dr)
   }
OPTIONAL MATCH (p)<-[:FOR_PATIENT]-(rr_doc:ReferralRequest)-[:HAS_DOCUMENT]->(dr)
OPTIONAL MATCH (dr)-[:DERIVED_FROM]->(rr_from:ReferralRequest)
WITH p, dr, coalesce(rr_doc, rr_from) AS rr
OPTIONAL MATCH (rr)-[:IN_WORKFLOW]->(:Workflow)<-[:HAS_WORKFLOW]-(svc_w:Service)
  -[:PROVIDES_SERVICE_FOR]->(sp_w:Organization)
OPTIONAL MATCH (rr)-[:FOR_SERVICE]->(svc_f:Service)
  -[:PROVIDES_SERVICE_FOR]->(sp_f:Organization)
OPTIONAL MATCH (dr)-[:HAS_CHUNK]->(ch:Chunk)
WITH p, dr, rr, coalesce(sp_w, sp_f) AS sp_org, head(collect(ch)) AS sample_chunk
RETURN toString(p.id) AS patient_id,
       coalesce(
         toString(p.tenantId),
         toString(dr.tenantId),
         toString(sample_chunk.tenantId),
         toString(rr.tenantId),
         toString(sp_org.tenantId),
         toString(sp_org.id),
         ''
       ) AS tenant_id,
       toString(dr.id) AS document_reference_id,
       coalesce(toString(rr.id), '') AS referral_id,
       CASE
         WHEN rr.id IS NOT NULL THEN toString(rr.id) + ':referral-assessment'
         ELSE ''
       END AS encounter_id
LIMIT 1
"""

ENSURE_REFERRAL_ASSESSMENT_ENCOUNTER = """
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
MATCH (rr:ReferralRequest {id: $referral_id})-[:FOR_PATIENT]->(p)
MERGE (e:Encounter {id: $encounter_id})
SET e.referral_id = $referral_id,
    e.source = coalesce(e.source, 'patient-viewer'),
    e.updated_at = datetime(),
    e.created_at = coalesce(e.created_at, datetime())
MERGE (p)-[:HAS_ENCOUNTER]->(e)
RETURN e.id AS encounter_id
LIMIT 1
"""
