"""Cypher queries for terminology operations against the Knowledge Graph."""

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

EXACT_QUERY = """
MATCH (t:Term {normalized_form: $normalized})-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, collect(DISTINCT rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, 1.0 AS score
LIMIT $k
"""

EXACT_SURFACE_FORM_QUERY = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[m:MAPS_TO]->(c:Concept)
WHERE c.active = true
WITH sf, c, max(coalesce(m.confidence, 0.0)) AS best_confidence
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, sf, best_confidence, collect(DISTINCT rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, 1.2 AS score, sf.status AS surface_form_status
ORDER BY best_confidence DESC
LIMIT $k
"""

FULLTEXT_QUERY = """
CALL db.index.fulltext.queryNodes("term_fulltext", $ft_query) YIELD node, score
MATCH (node)-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, max(score) AS best_score, collect(DISTINCT rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, best_score AS score
ORDER BY best_score DESC
LIMIT $k
"""

FULLTEXT_SURFACE_FORM_QUERY = """
CALL db.index.fulltext.queryNodes("surface_form_fulltext", $ft_query) YIELD node, score
MATCH (node)-[:MAPS_TO]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, node, max(score) AS best_score, collect(DISTINCT rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, best_score * 1.2 AS score, node.status AS surface_form_status
ORDER BY best_score DESC
LIMIT $k
"""

VECTOR_QUERY = """
CALL db.index.vector.queryNodes($index_name, $k, $embedding) YIELD node, score
MATCH (node)-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, max(score) AS best_score, collect(DISTINCT rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, best_score AS score
ORDER BY best_score DESC
LIMIT $k
"""

VECTOR_SURFACE_FORM_QUERY = """
CALL db.index.vector.queryNodes($index_name, $k, $embedding) YIELD node, score
MATCH (node:SurfaceForm)-[:MAPS_TO]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, max(score) AS best_score, collect(DISTINCT rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, best_score AS score
ORDER BY best_score DESC
LIMIT $k
"""

UPSERT_SURFACE_FORMS = """
UNWIND $rows AS r
MATCH (c:Concept {id: r.concept_id})
MERGE (sf:SurfaceForm {normalized: r.normalized})
ON CREATE SET sf.created_at = datetime(),
              sf.created_by = r.approved_by,
              sf.status     = r.status
ON MATCH SET  sf.status = CASE
                  WHEN sf.status = 'pending' AND r.status = 'pending'
                  THEN 'approved'
                  ELSE coalesce(sf.status, r.status)
              END
SET sf.form         = r.form,
    sf.source       = r.source,
    sf.last_seen_at = datetime()
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET m.created_at = datetime(), m.created_by = r.approved_by
SET m.confidence  = r.confidence,
    m.approved_by = r.approved_by,
    m.approved_at = datetime(),
    m.provenance  = r.provenance
RETURN count(sf) AS written
"""

LIST_APPROVED_WITH_REVIEWER = """
MATCH (c:EncounterCandidate)
WHERE c.approval_status = 'approved'
OPTIONAL MATCH (c)-[:HAS_TASK]->(:ReviewTask)-[:HAS_APPROVAL]->(a:Approval)
RETURN c, a.reviewer AS reviewer
ORDER BY c.patient_id, c.encounter_id
"""

LIST_APPROVED_FOR_PATIENT_WITH_REVIEWER = """
MATCH (c:EncounterCandidate)
WHERE c.approval_status = 'approved' AND c.patient_id = $patient_id
OPTIONAL MATCH (c)-[:HAS_TASK]->(:ReviewTask)-[:HAS_APPROVAL]->(a:Approval)
RETURN c, a.reviewer AS reviewer
ORDER BY c.encounter_id
"""

# Re-export from canonical shared location for backwards compatibility.
from libs.cypher.terminology_queries import DESCENDANTS_TEMPLATE  # noqa: F401

BATCH_LOOKUP_QUERY = """
UNWIND $terms AS norm
OPTIONAL MATCH (t:Term)-[:DESCRIBES]->(c:Concept)
WHERE toLower(t.normalized_form) = norm AND c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(r:ReadCode)
RETURN norm AS normalized,
       c.id AS snomed_concept_id,
       c.fsn AS snomed_term,
       collect(DISTINCT r.code)[0] AS read_code
"""

APPROVE_SURFACE_FORM = """
MATCH (sf:SurfaceForm {normalized: $normalized})
WHERE sf.status = 'pending'
SET sf.status = 'approved',
    sf.approved_at = datetime(),
    sf.approved_by = $approved_by
RETURN sf.normalized AS normalized, sf.status AS status
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

DELETE_SURFACE_FORM = """
MATCH (sf:SurfaceForm {normalized: $normalized})
DETACH DELETE sf
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
