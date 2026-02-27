"""Neo4j schema and write/query templates for HITL MVP.

Queries are now defined in libs/cypher/ and re-exported here for backward
compatibility. New code should import from libs/cypher/ directly.
"""
from __future__ import annotations

# Re-export from central registry
from libs.cypher.schema_constraints import (  # noqa: F401
    PATIENT_SCHEMA_CONSTRAINTS,
    CODING_SCHEMA_CONSTRAINTS,
)
from libs.cypher.candidate_queries import (  # noqa: F401
    UPSERT_CANDIDATE,
    CREATE_REVIEW_TASK,
    APPEND_CHANGE,
    APPEND_APPROVAL,
    LIST_TASKS,
    GET_TASK_DETAIL,
    GET_AUDIT_TIMELINE,
    LIST_APPROVED_CANDIDATES,
    LIST_APPROVED_CANDIDATES_FOR_PATIENT,
)
from libs.cypher.cleanup_queries import (  # noqa: F401
    RESET_PATIENT_REVIEW_QUEUE,
    RESET_ENCOUNTER_REVIEW_QUEUE,
    RESET_PATIENT_DOCUMENTS,
    RESET_PATIENT_DIRECT_SEMANTIC,
    DELETE_ENCOUNTER_DOCUMENTS,
)
from libs.cypher.documents_queries import (  # noqa: F401
    DELETE_CODED_LINK,
    UPDATE_CODED_LINK_MODIFIERS,
    LIST_ENCOUNTER_CODED_LINKS,
    LIST_PATIENT_CODING_STATUS,
)


# ── Patient graph queries ──────────────────────────────────

LIST_PATIENTS = """
MATCH (p:Patient)
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
RETURN toString(p.id) AS patient_id, count(e) AS encounter_count
ORDER BY patient_id
"""

LIST_APPROVED_COUNT_BY_PATIENT = """
MATCH (c:EncounterCandidate)
WHERE c.approval_status = 'approved'
RETURN c.patient_id AS patient_id, count(*) AS reviewed_count
"""

GET_PATIENT = """
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
RETURN toString(p.id) AS patient_id,
       count(e) AS encounter_count,
       p.gender AS gender,
       toString(p.birthDate) AS birth_date
"""

LIST_PATIENT_ENCOUNTERS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (e)-[r:DOCUMENTS]->()
WITH e, count(r) AS coded_count
RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text, coded_count, e.flags AS flags
ORDER BY e.date
LIMIT $limit
"""

GET_ENCOUNTER = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
OPTIONAL MATCH (e)-[r:DOCUMENTS]->()
WITH e, count(r) AS coded_count
RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text, coded_count
"""


# ── Encounter search queries ──────────────────────────────

SEARCH_ENCOUNTERS_KEYWORD = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
  AND toLower(e.text) CONTAINS toLower($q)
OPTIONAL MATCH (e)-[r:DOCUMENTS]->()
WITH e, count(r) AS coded_count
RETURN toString(e.id) AS encounter_id,
       toString(e.date) AS date,
       e.text AS text,
       coded_count,
       e.flags AS flags
ORDER BY e.date DESC
LIMIT $limit
"""

SEARCH_ENCOUNTERS_BY_CONCEPT_DOCS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(s)
WHERE toString(p.id) = $patient_id AND s.conceptId IN $concept_ids
WITH e, collect(DISTINCT s.conceptId) AS matched_concepts
OPTIONAL MATCH (e)-[r:DOCUMENTS]->()
WITH e, matched_concepts, count(r) AS coded_count
RETURN toString(e.id) AS encounter_id,
       toString(e.date) AS date,
       e.text AS text,
       coded_count,
       e.flags AS flags,
       matched_concepts
ORDER BY size(matched_concepts) DESC, e.date DESC
LIMIT $limit
"""

SEARCH_ENCOUNTERS_BY_CONCEPT_CANDIDATES = """
MATCH (ec:EncounterCandidate)
WHERE ec.patient_id = $patient_id
  AND any(cid IN $concept_ids WHERE ec.sentences_json CONTAINS cid)
WITH collect(DISTINCT ec.encounter_id) AS eids
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id AND toString(e.id) IN eids
OPTIONAL MATCH (e)-[r:DOCUMENTS]->()
WITH e, count(r) AS coded_count
RETURN toString(e.id) AS encounter_id,
       toString(e.date) AS date,
       e.text AS text,
       coded_count,
       e.flags AS flags
ORDER BY e.date DESC
LIMIT $limit
"""

SEARCH_ENCOUNTERS_VECTOR = """
CALL db.index.vector.queryNodes('encounter_vector_index', $k, $query_vector)
YIELD node, score
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(node)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (node)-[r:DOCUMENTS]->()
WITH node AS e, score, count(r) AS coded_count
RETURN toString(e.id) AS encounter_id,
       toString(e.date) AS date,
       e.text AS text,
       coded_count,
       e.flags AS flags,
       score AS similarity
ORDER BY score DESC
LIMIT $limit
"""


TERMINOLOGY_SEARCH = """
CALL db.index.fulltext.queryNodes("term_fulltext", $q) YIELD node, score
MATCH (node)-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
OPTIONAL MATCH (c)-[:MAPS_TO_ICD10]->(icd:Icd10Code)
WITH c, max(score) AS best_score,
     collect(DISTINCT rd.code)[0] AS read_code,
     collect(DISTINCT icd.code)[0] AS icd10
RETURN c.id AS snomed_concept_id,
       c.fsn AS term,
       c.semantic_tag AS semantic_tag,
       icd10,
       read_code,
       best_score AS score
ORDER BY best_score DESC
LIMIT $limit
"""

TERMINOLOGY_SEARCH_FILTERED = """
CALL db.index.fulltext.queryNodes("term_fulltext", $q) YIELD node, score
MATCH (node)-[:DESCRIBES]->(c:Concept)
WHERE c.active = true AND c.semantic_tag IN $tags
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
OPTIONAL MATCH (c)-[:MAPS_TO_ICD10]->(icd:Icd10Code)
WITH c, max(score) AS best_score,
     collect(DISTINCT rd.code)[0] AS read_code,
     collect(DISTINCT icd.code)[0] AS icd10
RETURN c.id AS snomed_concept_id,
       c.fsn AS term,
       c.semantic_tag AS semantic_tag,
       icd10,
       read_code,
       best_score AS score
ORDER BY best_score DESC
LIMIT $limit
"""
