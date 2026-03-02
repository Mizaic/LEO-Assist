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
ON CREATE SET
    cr.created_at = datetime(),
    cr.resolved   = false
SET cr.label_id          = $label_id,
    cr.entity_index      = $entity_index,
    cr.entity_text       = $entity_text,
    cr.entity_label      = $entity_label,
    cr.coded             = $coded,
    cr.snomed_concept_id = $snomed_concept_id,
    cr.snomed_term       = $snomed_term,
    cr.score             = $score,
    cr.semantic_tag      = $semantic_tag,
    cr.updated_at        = datetime()
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

IGNORE_CODING_REVIEW = """
MATCH (cr:CodingReview {review_id: $review_id})
SET cr.resolved             = true,
    cr.resolved_by          = $reviewer,
    cr.resolved_term        = coalesce(cr.resolved_term, "__ignored_by_rule__"),
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

GET_PENDING_FOR_RECHECK = """
MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
WHERE cr.resolved = false
  AND t.include = true
RETURN
    cr.review_id    AS review_id,
    cr.entity_text  AS entity_text,
    cr.entity_label AS entity_label
LIMIT $limit
"""

UPDATE_CODING_REVIEW_FIELDS = """
MATCH (cr:CodingReview {review_id: $review_id})
SET cr.coded             = $coded,
    cr.snomed_concept_id = $snomed_concept_id,
    cr.snomed_term       = $snomed_term,
    cr.score             = $score,
    cr.semantic_tag      = $semantic_tag,
    cr.updated_at        = datetime()
RETURN cr.review_id AS review_id
"""

AUTO_RESOLVE_CODING_REVIEW = """
MATCH (cr:CodingReview {review_id: $review_id})
SET cr.resolved              = true,
    cr.resolved_concept_id   = $concept_id,
    cr.resolved_term         = $term,
    cr.resolved_by           = $resolved_by,
    cr.resolved_at           = datetime(),
    cr.updated_at            = datetime(),
    cr.resolved_model_tier   = CASE WHEN $resolved_by STARTS WITH 'escalation:'
                                    THEN substring($resolved_by, 12)
                                    ELSE null END,
    cr.resolved_method       = CASE WHEN $resolved_by STARTS WITH 'escalation:'
                                    THEN 'model_escalation'
                                    WHEN $resolved_by STARTS WITH 'cascade:'
                                    THEN 'cascade'
                                    ELSE 'auto_recheck' END
RETURN cr.review_id AS review_id
"""

# ---------------------------------------------------------------------------
# CodingIgnoreRule -- persistent suppression rules for the coding review queue.
# When a term is ignored via the review UI, a CodingIgnoreRule node is created
# so future verification runs skip that term without re-queuing it.
# ---------------------------------------------------------------------------

UPSERT_CODING_IGNORE_RULE = """
MERGE (r:CodingIgnoreRule {entity_text: $entity_text})
ON CREATE SET r.rule_id = $rule_id, r.created_at = datetime()
SET r.entity_label = $entity_label,
    r.reason       = $reason,
    r.created_by   = coalesce(r.created_by, $created_by),
    r.active       = true,
    r.updated_at   = datetime()
RETURN r.rule_id AS rule_id, r.entity_text AS entity_text
"""

GET_CODING_IGNORE_RULES = """
MATCH (r:CodingIgnoreRule)
WHERE coalesce(r.active, true) = true
RETURN
    r.rule_id      AS rule_id,
    r.entity_text  AS entity_text,
    r.entity_label AS entity_label,
    r.reason       AS reason,
    r.created_by   AS created_by,
    toString(r.created_at) AS created_at
ORDER BY r.updated_at DESC
"""

GET_ALL_CODING_IGNORE_RULES = """
MATCH (r:CodingIgnoreRule)
RETURN
    r.rule_id               AS rule_id,
    coalesce(r.active, true) AS active,
    r.entity_text           AS entity_text,
    r.entity_label          AS entity_label,
    r.reason                AS reason,
    r.created_by            AS created_by,
    toString(r.created_at)  AS created_at,
    toString(r.updated_at)  AS updated_at
ORDER BY r.updated_at DESC
"""

DEACTIVATE_CODING_IGNORE_RULE = """
MATCH (r:CodingIgnoreRule {rule_id: $rule_id})
SET r.active     = false,
    r.updated_at = datetime()
RETURN r.rule_id AS rule_id
"""

# ---------------------------------------------------------------------------
# CodingSuggestion -- auto-generated surface form suggestions from the pipeline.
# Grouped by entity_text so a HITL operator sees one row per root cause.
# ---------------------------------------------------------------------------

UPSERT_CODING_SUGGESTION = """
MERGE (s:CodingSuggestion {entity_text: $entity_text})
ON CREATE SET
    s.created_at          = datetime(),
    s.occurrence_count    = 1
ON MATCH SET
    s.occurrence_count    = coalesce(s.occurrence_count, 0) + 1
SET s.entity_label        = $entity_label,
    s.suggested_term      = $suggested_term,
    s.confidence          = $confidence,
    s.model_tier          = $model_tier,
    s.model_id            = $model_id,
    s.status              = coalesce(s.status, $status),
    s.updated_at          = datetime()
RETURN
    s.entity_text         AS entity_text,
    s.occurrence_count    AS occurrence_count,
    s.status              AS status
"""

# ---------------------------------------------------------------------------
# Batch deduplication -- group pending reviews by entity_text so the HITL
# operator resolves one root cause instead of N identical symptoms.
# ---------------------------------------------------------------------------

GROUP_CODING_REVIEWS_BY_ENTITY = """
MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
WHERE cr.resolved = false
  AND t.include = true
WITH cr.entity_text AS entity_text,
     cr.entity_label AS entity_label,
     count(cr) AS review_count,
     max(cr.score) AS best_score,
     collect(cr.review_id)[0] AS sample_review_id,
     min(cr.coded) AS any_uncoded
RETURN entity_text,
       entity_label,
       review_count,
       best_score,
       sample_review_id,
       any_uncoded
ORDER BY review_count DESC, best_score ASC
SKIP $skip
LIMIT $limit
"""

COUNT_CODING_REVIEW_GROUPS = """
MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
WHERE cr.resolved = false
  AND t.include = true
WITH cr.entity_text AS entity_text
RETURN count(DISTINCT entity_text) AS group_count
"""

BATCH_RESOLVE_BY_ENTITY_TEXT = """
MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
WHERE cr.resolved = false
  AND t.include = true
  AND cr.entity_text = $entity_text
SET cr.resolved            = true,
    cr.resolved_concept_id = $resolved_concept_id,
    cr.resolved_term       = $resolved_term,
    cr.resolved_by         = $reviewer,
    cr.resolved_at         = datetime(),
    cr.updated_at          = datetime(),
    cr.resolved_method     = 'batch_resolve'
RETURN count(cr) AS resolved_count
"""
