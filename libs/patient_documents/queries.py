"""Cypher for manual patient document CRUD."""

SOURCE_MANUAL_JOURNEY = "manual_journey"

GET_DOCUMENT_FOR_PATIENT = """
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
MATCH (dr:DocumentReference {id: $document_id})
WHERE dr.source = $source
  AND (
    EXISTS { MATCH (p)-[:HAS_DOCUMENT_REFERENCE]->(dr) }
    OR EXISTS {
      MATCH (p)<-[:FOR_PATIENT]-(:ReferralRequest)-[:HAS_DOCUMENT]->(dr)
    }
  )
OPTIONAL MATCH (dr)-[:HAS_CHUNK]->(ch:Chunk)
WITH dr, collect(ch.id) AS chunk_ids
RETURN toString(dr.id) AS document_id,
       coalesce(dr.title, '') AS title,
       coalesce(dr.category, '') AS category,
       coalesce(dr.date, dr.creation, '') AS document_date,
       coalesce(dr.episode_id, '') AS episode_id,
       coalesce(dr.milestone_type, '') AS milestone_type,
       coalesce(dr.text, '') AS full_text,
       chunk_ids
LIMIT 1
"""

CREATE_DOCUMENT_GRAPH = """
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
MERGE (dr:DocumentReference {id: $document_id})
SET dr.source = $source,
    dr.title = $title,
    dr.category = $category,
    dr.date = $document_date,
    dr.creation = $document_date,
    dr.contentType = 'text/markdown',
    dr.text = $markdown_body,
    dr.episode_id = CASE WHEN $episode_id <> '' THEN $episode_id ELSE dr.episode_id END,
    dr.milestone_type = CASE WHEN $milestone_type <> '' THEN $milestone_type ELSE dr.milestone_type END,
    dr.updated_at = datetime(),
    dr.created_at = coalesce(dr.created_at, datetime())
MERGE (p)-[:HAS_DOCUMENT_REFERENCE]->(dr)
WITH p, dr
MERGE (rr:ReferralRequest {id: $referral_id})
SET rr.source = $source,
    rr.status = 'active',
    rr.updated_at = datetime()
MERGE (rr)-[:FOR_PATIENT]->(p)
MERGE (rr)-[:HAS_DOCUMENT]->(dr)
MERGE (dr)-[:DERIVED_FROM]->(rr)
RETURN toString(dr.id) AS document_id,
       toString(rr.id) AS referral_id
"""

UPDATE_DOCUMENT_META = """
MATCH (dr:DocumentReference {id: $document_id, source: $source})
SET dr.title = coalesce($title, dr.title),
    dr.category = coalesce($category, dr.category),
    dr.date = coalesce($document_date, dr.date),
    dr.episode_id = CASE WHEN $episode_id IS NULL THEN dr.episode_id ELSE $episode_id END,
    dr.milestone_type = CASE WHEN $milestone_type IS NULL THEN dr.milestone_type ELSE $milestone_type END,
    dr.updated_at = datetime()
RETURN toString(dr.id) AS document_id
"""

UPDATE_DOCUMENT_BODY = """
MATCH (dr:DocumentReference {id: $document_id, source: $source})
SET dr.text = $markdown_body,
    dr.updated_at = datetime()
RETURN toString(dr.id) AS document_id
"""

DELETE_DOCUMENT_CHUNKS = """
MATCH (dr:DocumentReference {id: $document_id, source: $source})-[:HAS_CHUNK]->(ch:Chunk)
DETACH DELETE ch
"""

DELETE_DOCUMENT_NODE = """
MATCH (dr:DocumentReference {id: $document_id, source: $source})
DETACH DELETE dr
"""

DELETE_ORPHAN_REFERRAL = """
MATCH (rr:ReferralRequest {id: $referral_id, source: $source})
WHERE NOT EXISTS { MATCH (rr)-[:HAS_DOCUMENT]->(:DocumentReference) }
DETACH DELETE rr
"""

DELETE_MILESTONE_ENCOUNTER = """
MATCH (e:Encounter {id: $encounter_id, source: $source})
DETACH DELETE e
"""

UPSERT_MILESTONE_ENCOUNTER = """
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
MERGE (e:Encounter {id: $encounter_id})
SET e.source = $source,
    e.referral_id = $referral_id,
    e.document_reference_id = $document_id,
    e.milestone_type = $milestone_type,
    e.updated_at = datetime(),
    e.created_at = coalesce(e.created_at, datetime())
MERGE (p)-[:HAS_ENCOUNTER]->(e)
RETURN e.id AS encounter_id
"""

ATTACH_ENCOUNTER_TO_EPISODE = """
MATCH (e:Encounter {id: $encounter_id})
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})
MERGE (e)-[r:IS_PART_OF {milestone_type: $milestone_type}]->(ep)
ON CREATE SET r.linked_by = 'manual_journey',
              r.linked_at = datetime()
RETURN e.id AS encounter_id
"""

LIST_EPISODE_ENCOUNTERS_UP_TO_MILESTONE = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})<-[r:IS_PART_OF]-(e:Encounter)
WHERE r.milestone_type IN $milestone_types
RETURN DISTINCT toString(e.id) AS encounter_id,
       r.milestone_type AS milestone_type
ORDER BY r.milestone_type
"""

LIST_EPISODE_ASSESSMENTS = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})-[:HAS_ASSESSMENT]->(a:Assessment)
RETURN toString(a.id) AS assessment_id,
       coalesce(a.assessment_scope, 'referral') AS assessment_scope,
       coalesce(a.milestone_type, '') AS milestone_type,
       coalesce(a.updated_at, a.created_at, '') AS updated_at
ORDER BY updated_at DESC
"""

SET_ASSESSMENT_MILESTONE = """
MATCH (a:Assessment {id: $assessment_id})
SET a.milestone_type = $milestone_type,
    a.assessment_scope = $assessment_scope,
    a.updated_at = datetime()
RETURN a.id AS id
"""
