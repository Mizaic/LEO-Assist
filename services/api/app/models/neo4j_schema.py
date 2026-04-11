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
    RESET_PATIENT_LLM_USAGE,
    RESET_PATIENT_CODING_DECISIONS,
    RESET_PATIENT_SENTENCES_PAYLOAD,
    DELETE_ENCOUNTER_DOCUMENTS,
    DELETE_ENCOUNTER_EPISODE_LINKS,
    LIST_ENCOUNTER_DOCUMENT_CONCEPT_IDS,
    CLEANUP_PATIENT_SHORTCUTS_FOR_CONCEPTS,
    DELETE_ORPHAN_ENCOUNTER_LLM_USAGE,
    DELETE_ENCOUNTER_CODING_DECISIONS,
    CLEAR_ENCOUNTER_SENTENCES_PAYLOAD,
)
from libs.cypher.documents_queries import (  # noqa: F401
    DELETE_CODED_LINK,
    UPDATE_CODED_LINK_MODIFIERS,
    LIST_ENCOUNTER_CODED_LINKS,
    LIST_PATIENT_CODING_STATUS,
    GET_PATIENT_CODING_TIMELINE,
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
CALL {
    CALL db.index.fulltext.queryNodes("term_fulltext", $q) YIELD node, score
    MATCH (node)-[:DESCRIBES]->(c:Concept)
    WHERE c.active = true
    RETURN c, score AS weighted_score
    UNION
    CALL db.index.fulltext.queryNodes("surface_form_fulltext", $q) YIELD node, score
    MATCH (node)-[:MAPS_TO]->(c:Concept)
    WHERE c.active = true
    RETURN c, score * 1.2 AS weighted_score
    UNION
    MATCH (c:Concept {id: $q})
    WHERE c.active = true
    RETURN c, 2.0 AS weighted_score
    UNION
    MATCH (rd:ReadCode {code: $q})<-[:MAPS_TO_READ]-(c:Concept)
    WHERE c.active = true
    RETURN c, 2.0 AS weighted_score
}
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
OPTIONAL MATCH (c)-[:MAPS_TO_ICD10]->(icd:Icd10Code)
WITH c, max(weighted_score) AS best_score,
     collect(DISTINCT rd.code)[0] AS read_code,
     collect(DISTINCT icd.code)[0] AS icd10
RETURN c.id AS snomed_concept_id,
       c.fsn AS term,
       c.semantic_tag AS semantic_tag,
       c.module_id AS module_id,
       icd10,
       read_code,
       best_score AS score
ORDER BY best_score DESC
LIMIT $limit
"""

TERMINOLOGY_SEARCH_FILTERED = """
CALL {
    CALL db.index.fulltext.queryNodes("term_fulltext", $q) YIELD node, score
    MATCH (node)-[:DESCRIBES]->(c:Concept)
    WHERE c.active = true AND c.semantic_tag IN $tags
    RETURN c, score AS weighted_score
    UNION
    CALL db.index.fulltext.queryNodes("surface_form_fulltext", $q) YIELD node, score
    MATCH (node)-[:MAPS_TO]->(c:Concept)
    WHERE c.active = true AND c.semantic_tag IN $tags
    RETURN c, score * 1.2 AS weighted_score
    UNION
    MATCH (c:Concept {id: $q})
    WHERE c.active = true AND c.semantic_tag IN $tags
    RETURN c, 2.0 AS weighted_score
    UNION
    MATCH (rd:ReadCode {code: $q})<-[:MAPS_TO_READ]-(c:Concept)
    WHERE c.active = true AND c.semantic_tag IN $tags
    RETURN c, 2.0 AS weighted_score
}
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
OPTIONAL MATCH (c)-[:MAPS_TO_ICD10]->(icd:Icd10Code)
WITH c, max(weighted_score) AS best_score,
     collect(DISTINCT rd.code)[0] AS read_code,
     collect(DISTINCT icd.code)[0] AS icd10
RETURN c.id AS snomed_concept_id,
       c.fsn AS term,
       c.semantic_tag AS semantic_tag,
       c.module_id AS module_id,
       icd10,
       read_code,
       best_score AS score
ORDER BY best_score DESC
LIMIT $limit
"""

LIST_SURFACE_FORMS = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
WHERE ($q IS NULL OR toLower(sf.form) CONTAINS toLower($q))
  AND ($concept_id IS NULL OR c.id = $concept_id)
WITH sf, c,
     max(m.confidence)              AS confidence,
     head(collect(m.approved_by))   AS approved_by,
     head(collect(m.provenance))    AS provenance
RETURN sf.normalized    AS normalized,
       sf.form          AS form,
       sf.source        AS source,
       sf.status        AS status,
       sf.created_by    AS created_by,
       toString(sf.created_at)    AS created_at,
       toString(sf.last_seen_at)  AS last_seen_at,
       c.id             AS concept_id,
       c.fsn            AS concept_fsn,
       c.semantic_tag   AS semantic_tag,
       confidence,
       approved_by,
       provenance
ORDER BY sf.form
SKIP $offset
LIMIT $limit
"""

COUNT_SURFACE_FORMS = """
MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept)
WHERE ($q IS NULL OR toLower(sf.form) CONTAINS toLower($q))
  AND ($concept_id IS NULL OR c.id = $concept_id)
WITH sf, c
RETURN count(*) AS total
"""

DELETE_SURFACE_FORM = """
MATCH (sf:SurfaceForm {normalized: $normalized})
DETACH DELETE sf
"""

UPSERT_SURFACE_FORM_MAPPING = """
MATCH (c:Concept {id: $concept_id})
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form = $form,
              sf.source = $source,
              sf.status = 'active',
              sf.created_at = datetime(),
              sf.created_by = $created_by
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET m.created_at = datetime(),
              m.created_by = $created_by,
              m.approved_at = datetime()
SET m.confidence = $confidence,
    m.provenance = $provenance
RETURN sf.normalized AS normalized,
       sf.form       AS form,
       c.id          AS concept_id,
       c.fsn         AS concept_fsn
"""

DELETE_SURFACE_FORM_MAPPING = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[r:MAPS_TO]->(c:Concept {id: $concept_id})
DELETE r
RETURN count(r) AS removed
"""

KEEP_SURFACE_FORM_MAPPING = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[r:MAPS_TO]->(c:Concept)
WHERE c.id <> $keep_concept_id
DELETE r
RETURN count(r) AS removed
"""

DEDUPLICATE_SURFACE_FORM_RELS = """
MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept)
WITH sf, collect({r: r, confidence: coalesce(r.confidence, 0.0)}) AS all_rels
WHERE size(all_rels) > 1
WITH sf, all_rels,
     reduce(best = all_rels[0], x IN all_rels |
       CASE WHEN x.confidence > best.confidence THEN x ELSE best END
     ) AS keeper
UNWIND all_rels AS entry
WITH entry.r AS r, keeper
WHERE r <> keeper.r
DELETE r
RETURN count(r) AS duplicates_removed
"""

AUDIT_SURFACE_FORM_DUPLICATES = """
MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept)
WITH sf, count(DISTINCT c) AS concept_count, count(r) AS rel_count
WHERE rel_count > 1
WITH sf, concept_count, rel_count
MATCH (sf)-[r:MAPS_TO]->(c:Concept)
RETURN sf.normalized       AS normalized,
       sf.form             AS form,
       concept_count,
       rel_count,
       collect({
           concept_id:  c.id,
           concept_fsn: c.fsn,
           confidence:  r.confidence,
           provenance:  r.provenance
       }) AS mappings
ORDER BY rel_count DESC, sf.form
LIMIT 200
"""

GET_CONCEPT_FOR_SUGGESTION = """
MATCH (c:Concept {id: $concept_id})
WHERE c.active = true
OPTIONAL MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c)
RETURN c.fsn            AS concept_fsn,
       c.semantic_tag   AS semantic_tag,
       collect(sf.form) AS existing_aliases
"""

GROUPED_SURFACE_FORMS = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
WHERE c.active = true
  AND ($q IS NULL
       OR toLower(sf.form) CONTAINS toLower($q)
       OR toLower(c.fsn)   CONTAINS toLower($q)
       OR c.id             CONTAINS $q
       OR EXISTS {
           MATCH (c)-[:MAPS_TO_READ]->(rd_f:ReadCode)
           WHERE rd_f.code = $q
       })
WITH c,
     collect({
       normalized:  sf.normalized,
       form:        sf.form,
       source:      sf.source,
       created_by:  sf.created_by,
       created_at:  toString(sf.created_at),
       confidence:  m.confidence
     }) AS surface_forms
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
OPTIONAL MATCH (c)-[:MAPS_TO_ICD10]->(icd:Icd10Code)
WITH c, surface_forms,
     collect(DISTINCT rd.code)[0] AS read_code,
     collect(DISTINCT icd.code)[0] AS icd10
RETURN c.id            AS concept_id,
       c.fsn           AS concept_fsn,
       c.semantic_tag  AS semantic_tag,
       read_code,
       icd10,
       surface_forms
ORDER BY c.fsn
SKIP $offset
LIMIT $limit
"""

COUNT_GROUPED_SURFACE_FORMS = """
MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept)
WHERE c.active = true
  AND ($q IS NULL
       OR toLower(sf.form) CONTAINS toLower($q)
       OR toLower(c.fsn)   CONTAINS toLower($q)
       OR c.id             CONTAINS $q
       OR EXISTS {
           MATCH (c)-[:MAPS_TO_READ]->(rd_f:ReadCode)
           WHERE rd_f.code = $q
       })
WITH DISTINCT c
RETURN count(c) AS total
"""

# Depth must be interpolated via Python .format(depth=N) before execution —
# Neo4j does not support parameterised variable-length path bounds.
DESCENDANTS_TEMPLATE = """
MATCH (ancestor:Concept {{id: $concept_id}})<-[:IS_A*1..{depth}]-(d:Concept)
WHERE d.active = true
  AND ($semantic_tag IS NULL OR d.semantic_tag = $semantic_tag)
OPTIONAL MATCH (sf:SurfaceForm)-[:MAPS_TO]->(d)
WITH d, count(sf) AS surface_form_count, collect(sf.form)[0..10] AS surface_forms
RETURN DISTINCT
    d.id            AS snomed_concept_id,
    d.fsn           AS term,
    d.semantic_tag  AS semantic_tag,
    surface_form_count,
    surface_forms
ORDER BY d.fsn
LIMIT $limit
"""
