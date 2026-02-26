"""Cypher queries for terminology operations against the Knowledge Graph."""

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
MATCH (sf:SurfaceForm {normalized: $normalized})-[:MAPS_TO]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, collect(DISTINCT rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, 1.2 AS score
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
WITH c, max(score) AS best_score, collect(DISTINCT rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, best_score * 1.2 AS score
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

UPSERT_SURFACE_FORMS = """
UNWIND $rows AS r
MATCH (c:Concept {id: r.concept_id})
MERGE (sf:SurfaceForm {normalized: r.normalized})
ON CREATE SET sf.created_at = datetime(), sf.created_by = r.approved_by
SET sf.form = r.form,
    sf.source = r.source,
    sf.status = r.status,
    sf.last_seen_at = datetime()
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET m.created_at = datetime(), m.created_by = r.approved_by
SET m.confidence = r.confidence,
    m.approved_by = r.approved_by,
    m.approved_at = datetime(),
    m.provenance = r.provenance
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
