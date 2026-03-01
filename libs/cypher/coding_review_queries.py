"""Cypher queries for coding verification — tracking which training entities
resolve successfully to SNOMED concepts via the terminology API.

CodingReview nodes record:
- entity_text / entity_label from the training data
- whether /resolve returned a SNOMED concept
- the best candidate (if any) with score and semantic_tag
- whether a human reviewed and confirmed/corrected the coding
"""

UPSERT_CODING_REVIEW = """
MATCH (t:TrainingLabel {label_id: $label_id})
MERGE (cr:CodingReview {review_id: $review_id})
ON CREATE SET cr.created_at = datetime()
SET cr.label_id        = $label_id,
    cr.entity_index    = $entity_index,
    cr.entity_text     = $entity_text,
    cr.entity_label    = $entity_label,
    cr.coded           = $coded,
    cr.snomed_concept_id = $snomed_concept_id,
    cr.snomed_term     = $snomed_term,
    cr.score           = $score,
    cr.semantic_tag    = $semantic_tag,
    cr.resolved        = false,
    cr.updated_at      = datetime()
MERGE (cr)-[:REVIEWS_CODING]->(t)
RETURN cr.review_id AS review_id
"""

RESOLVE_CODING_REVIEW = """
MATCH (cr:CodingReview {review_id: $review_id})
SET cr.resolved             = true,
    cr.resolved_concept_id  = $resolved_concept_id,
    cr.resolved_term        = $resolved_term,
    cr.resolved_by          = $reviewer,
    cr.resolved_at          = datetime(),
    cr.updated_at           = datetime()
RETURN cr.review_id AS review_id
"""

GET_CODING_REVIEW_QUEUE = """
MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
WHERE cr.resolved = false
  AND t.include = true
RETURN
    cr.review_id          AS review_id,
    cr.label_id           AS label_id,
    cr.entity_index       AS entity_index,
    cr.entity_text        AS entity_text,
    cr.entity_label       AS entity_label,
    cr.coded              AS coded,
    cr.snomed_concept_id  AS snomed_concept_id,
    cr.snomed_term        AS snomed_term,
    cr.score              AS score,
    cr.semantic_tag       AS semantic_tag,
    toString(cr.created_at) AS created_at,
    t.text                AS encounter_text,
    t.source              AS source
ORDER BY cr.coded ASC, cr.score ASC, cr.created_at ASC
SKIP $skip
LIMIT $limit
"""

COUNT_CODING_REVIEW_PENDING = """
MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
WHERE cr.resolved = false
  AND t.include = true
RETURN count(cr) AS pending
"""

GET_CODING_REVIEW_STATS = """
MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
WHERE t.include = true
WITH
    count(cr) AS total,
    sum(CASE WHEN cr.coded = true THEN 1 ELSE 0 END) AS coded,
    sum(CASE WHEN cr.coded = false THEN 1 ELSE 0 END) AS uncoded,
    sum(CASE WHEN cr.resolved = true THEN 1 ELSE 0 END) AS resolved,
    sum(CASE WHEN cr.resolved = false THEN 1 ELSE 0 END) AS pending,
    sum(CASE WHEN cr.score IS NOT NULL AND cr.score < 0.7 THEN 1 ELSE 0 END) AS low_confidence
RETURN total, coded, uncoded, resolved, pending, low_confidence
"""

DELETE_ALL_CODING_REVIEWS = """
MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
WHERE t.include = true
DETACH DELETE cr
"""
