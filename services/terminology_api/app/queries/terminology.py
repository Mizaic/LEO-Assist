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

# ---------------------------------------------------------------------------
# Batch queries — UNWIND-based, reduce N×8 round trips to ~4 per request
# ---------------------------------------------------------------------------

# Single query covering both Term exact match and SurfaceForm exact match
# for all terms in one round trip.
# Returns: input_term, concept_id, fsn, semantic_tag, read_codes, score,
#          surface_form_status ('sf_exact' branch has status, term branch is '')
BATCH_EXACT_QUERY = """
UNWIND $normalized_terms AS norm

OPTIONAL MATCH (t:Term {normalized_form: norm})-[:DESCRIBES]->(ct:Concept)
WHERE ct.active = true
OPTIONAL MATCH (ct)-[:MAPS_TO_READ]->(rdt:ReadCode)
WITH norm, ct, collect(DISTINCT rdt.code) AS rdt_codes
WITH norm,
     collect(
       CASE WHEN ct IS NOT NULL
            THEN {concept_id: ct.id, fsn: ct.fsn, semantic_tag: ct.semantic_tag,
                  read_codes: rdt_codes, score: 1.0, surface_form_status: ''}
       END
     ) AS raw_term_hits
WITH norm, [x IN raw_term_hits WHERE x IS NOT NULL] AS term_hits

OPTIONAL MATCH (sf:SurfaceForm {normalized: norm})-[m:MAPS_TO]->(cs:Concept)
WHERE cs.active = true
WITH norm, term_hits, sf, cs, max(coalesce(m.confidence, 0.0)) AS best_conf
OPTIONAL MATCH (cs)-[:MAPS_TO_READ]->(rds:ReadCode)
WITH norm, term_hits, cs, sf, best_conf, collect(DISTINCT rds.code) AS rds_codes
WITH norm, term_hits,
     collect(
       CASE WHEN cs IS NOT NULL
            THEN {concept_id: cs.id, fsn: cs.fsn, semantic_tag: cs.semantic_tag,
                  read_codes: rds_codes, score: 1.2,
                  surface_form_status: coalesce(sf.status, '')}
       END
     ) AS raw_sf_hits
WITH norm, term_hits, [x IN raw_sf_hits WHERE x IS NOT NULL] AS sf_hits

RETURN norm AS input_term,
       term_hits + sf_hits AS hits
"""

# Batched fulltext search: runs one fulltext query string against both
# the term and surface-form indexes, collecting all matches keyed by
# the originating input term.  Callers iterate over the fulltext query
# variants (phrase, raw, AND-tokens) and merge results.
# Returns: input_term, concept_id, fsn, semantic_tag, read_codes, score,
#          surface_form_status
BATCH_FULLTEXT_QUERY = """
CALL db.index.fulltext.queryNodes("term_fulltext", $ft_query) YIELD node AS tnode, score AS tscore
MATCH (tnode)-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, max(tscore) AS best_score, collect(DISTINCT rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, best_score AS score, '' AS surface_form_status
ORDER BY best_score DESC
LIMIT $k
UNION ALL
CALL db.index.fulltext.queryNodes("surface_form_fulltext", $ft_query) YIELD node AS sfnode, score AS sfscore
MATCH (sfnode)-[:MAPS_TO]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, sfnode, max(sfscore) AS best_score, collect(DISTINCT rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, best_score * 1.2 AS score, sfnode.status AS surface_form_status
ORDER BY best_score DESC
LIMIT $k
"""

# Batch lab-domain enrichment: given a list of concept IDs, returns the
# SNOMED ontology neighbourhood for each in one round trip.
BATCH_RELATED_CONCEPTS_QUERY = """
UNWIND $concept_ids AS cid
MATCH (c:Concept {id: cid})
WHERE c.active = true

OPTIONAL MATCH (f:Concept)-[:INTERPRETS]->(c) WHERE f.active = true
OPTIONAL MATCH (p:Concept)-[:HAS_COMPONENT]->(c) WHERE p.active = true
OPTIONAL MATCH (c)-[:INTERPRETS]->(obs:Concept)  WHERE obs.active = true
OPTIONAL MATCH (c)-[:HAS_COMPONENT]->(comp:Concept) WHERE comp.active = true
OPTIONAL MATCH (c)-[:HAS_ASSOCIATED_FINDING]->(assoc_f:Concept) WHERE assoc_f.active = true

RETURN
  c.id AS concept_id,
  [x IN collect(DISTINCT f)       WHERE x IS NOT NULL | {id: x.id, fsn: x.fsn, semantic_tag: x.semantic_tag, rel: 'INTERPRETED_BY'}]       AS interpreted_by_findings,
  [x IN collect(DISTINCT p)       WHERE x IS NOT NULL | {id: x.id, fsn: x.fsn, semantic_tag: x.semantic_tag, rel: 'COMPONENT_OF'}]          AS component_of_procedures,
  [x IN collect(DISTINCT obs)     WHERE x IS NOT NULL | {id: x.id, fsn: x.fsn, semantic_tag: x.semantic_tag, rel: 'INTERPRETS'}]            AS interprets_observables,
  [x IN collect(DISTINCT comp)    WHERE x IS NOT NULL | {id: x.id, fsn: x.fsn, semantic_tag: x.semantic_tag, rel: 'HAS_COMPONENT'}]         AS has_components,
  [x IN collect(DISTINCT assoc_f) WHERE x IS NOT NULL | {id: x.id, fsn: x.fsn, semantic_tag: x.semantic_tag, rel: 'HAS_ASSOCIATED_FINDING'}] AS associated_findings
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

# ---------------------------------------------------------------------------
# Ontology-Driven Lab Concept Resolver
# ---------------------------------------------------------------------------
# Traverses the three lab-domain relationship types materialised by
# snomed_attribute_projection.py (phase 3 loader):
#
#   HAS_COMPONENT  (246093002) — procedure -[HAS_COMPONENT]-> observable_entity
#   INTERPRETS     (363713009) — finding   -[INTERPRETS]->   observable_entity
#   HAS_ASSOCIATED_FINDING (246090004) — concept -[HAS_ASSOCIATED_FINDING]-> finding
#
# Given any concept in the procedure / observable_entity / finding family,
# returns the full constellation of related concepts so callers can resolve
# compound lab entities (observable + qualifier_value + finding) without
# resorting to LLM disambiguation.
RELATED_CONCEPTS_QUERY = """
MATCH (c:Concept {id: $concept_id})
WHERE c.active = true

// Findings that interpret THIS observable_entity (finding -> INTERPRETS -> me)
OPTIONAL MATCH (f:Concept)-[:INTERPRETS]->(c)
WHERE f.active = true

// Procedures that have THIS as a component (procedure -> HAS_COMPONENT -> me)
OPTIONAL MATCH (p:Concept)-[:HAS_COMPONENT]->(c)
WHERE p.active = true

// Observables that THIS concept interprets (me -[INTERPRETS]-> observable)
OPTIONAL MATCH (c)-[:INTERPRETS]->(obs:Concept)
WHERE obs.active = true

// Components that THIS concept has (me -[HAS_COMPONENT]-> component)
OPTIONAL MATCH (c)-[:HAS_COMPONENT]->(comp:Concept)
WHERE comp.active = true

// Findings associated with THIS concept
OPTIONAL MATCH (c)-[:HAS_ASSOCIATED_FINDING]->(assoc_f:Concept)
WHERE assoc_f.active = true

RETURN
  c.id           AS concept_id,
  c.fsn          AS concept_fsn,
  c.semantic_tag AS semantic_tag,
  [x IN collect(DISTINCT f)       WHERE x IS NOT NULL | {id: x.id, fsn: x.fsn, semantic_tag: x.semantic_tag, rel: 'INTERPRETED_BY'}]      AS interpreted_by_findings,
  [x IN collect(DISTINCT p)       WHERE x IS NOT NULL | {id: x.id, fsn: x.fsn, semantic_tag: x.semantic_tag, rel: 'COMPONENT_OF'}]         AS component_of_procedures,
  [x IN collect(DISTINCT obs)     WHERE x IS NOT NULL | {id: x.id, fsn: x.fsn, semantic_tag: x.semantic_tag, rel: 'INTERPRETS'}]           AS interprets_observables,
  [x IN collect(DISTINCT comp)    WHERE x IS NOT NULL | {id: x.id, fsn: x.fsn, semantic_tag: x.semantic_tag, rel: 'HAS_COMPONENT'}]        AS has_components,
  [x IN collect(DISTINCT assoc_f) WHERE x IS NOT NULL | {id: x.id, fsn: x.fsn, semantic_tag: x.semantic_tag, rel: 'HAS_ASSOCIATED_FINDING'}] AS associated_findings
"""
