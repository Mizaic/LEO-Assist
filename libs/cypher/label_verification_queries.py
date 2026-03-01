"""Cypher queries for dual-model label verification and HITL resolution.

`LabelVerificationReview` nodes track disagreements between AWS and Azure
suggestions for a specific entity inside a `TrainingLabel` record.

When a human resolves a disagreement, we record which model was correct
(model_a_was_correct / model_b_was_correct) so per-model accuracy stats
can be calculated, mirroring the classification review scorecard pattern.
"""

# ------------------------------------------------------------------
# Write queries
# ------------------------------------------------------------------

UPDATE_LABEL_VERIFICATION = """
MATCH (t:TrainingLabel {label_id: $label_id})
SET t.verified_at             = datetime(),
    t.verification_agreement  = $verification_agreement,
    t.model_a_label           = $model_a_label,
    t.model_b_label           = $model_b_label,
    t.quality_score           = $quality_score,
    t.updated_at              = datetime()
RETURN
    t.label_id                AS label_id,
    t.verification_agreement  AS verification_agreement,
    t.quality_score           AS quality_score
"""

UPSERT_LABEL_VERIFICATION_REVIEW = """
MATCH (t:TrainingLabel {label_id: $label_id})
MERGE (r:LabelVerificationReview {review_id: $review_id})
ON CREATE SET r.created_at = datetime()
SET r.label_id                = $label_id,
    r.entity_index            = $entity_index,
    r.entity_text             = $entity_text,
    r.current_label           = $current_label,
    r.model_a_label           = $model_a_label,
    r.model_a_rationale       = $model_a_rationale,
    r.model_b_label           = $model_b_label,
    r.model_b_rationale       = $model_b_rationale,
    r.resolved                = false,
    r.resolved_label          = null,
    r.resolved_at             = null,
    r.resolved_by             = null,
    r.model_a_was_correct     = null,
    r.model_b_was_correct     = null,
    r.updated_at              = datetime()
MERGE (r)-[:REVIEWS_LABEL]->(t)
RETURN r.review_id AS review_id
"""

RESOLVE_LABEL_VERIFICATION_REVIEW = """
MATCH (r:LabelVerificationReview {review_id: $review_id})
WHERE coalesce(r.resolved, false) = false
MATCH (t:TrainingLabel {label_id: r.label_id})
SET r.resolved                = true,
    r.resolved_label          = $resolved_label,
    r.resolved_by             = $reviewer,
    r.resolved_at             = datetime(),
    r.model_a_was_correct     = $model_a_was_correct,
    r.model_b_was_correct     = $model_b_was_correct,
    r.updated_at              = datetime(),
    t.entities_json           = $entities_json,
    t.updated_at              = datetime(),
    t.verified_at             = datetime()
RETURN
    r.review_id               AS review_id,
    r.label_id                AS label_id,
    r.resolved_label          AS resolved_label,
    r.model_a_was_correct     AS model_a_was_correct,
    r.model_b_was_correct     AS model_b_was_correct
"""

# ------------------------------------------------------------------
# Read queries
# ------------------------------------------------------------------

GET_VERIFICATION_QUEUE = """
MATCH (r:LabelVerificationReview)-[:REVIEWS_LABEL]->(t:TrainingLabel)
WHERE coalesce(r.resolved, false) = false
  AND t.include = true
RETURN
    r.review_id               AS review_id,
    r.label_id                AS label_id,
    r.entity_index            AS entity_index,
    r.entity_text             AS entity_text,
    r.current_label           AS current_label,
    r.model_a_label           AS model_a_label,
    r.model_a_rationale       AS model_a_rationale,
    r.model_b_label           AS model_b_label,
    r.model_b_rationale       AS model_b_rationale,
    toString(r.created_at)    AS created_at,
    t.text                    AS text,
    t.entities_json           AS entities_json,
    t.source                  AS source
ORDER BY r.created_at DESC
SKIP $skip
LIMIT $limit
"""

COUNT_VERIFICATION_QUEUE_PENDING = """
MATCH (r:LabelVerificationReview)-[:REVIEWS_LABEL]->(t:TrainingLabel)
WHERE coalesce(r.resolved, false) = false
  AND t.include = true
RETURN count(r) AS pending
"""

GET_VERIFICATION_STATS = """
MATCH (t:TrainingLabel)
WHERE t.include = true
WITH
    count(t) AS total_labels,
    sum(CASE WHEN t.verified_at IS NOT NULL THEN 1 ELSE 0 END) AS verified_labels,
    sum(CASE WHEN t.verification_agreement = true THEN 1 ELSE 0 END) AS agreements,
    sum(CASE WHEN t.verification_agreement = false THEN 1 ELSE 0 END) AS disagreements
CALL {
    MATCH (r:LabelVerificationReview)-[:REVIEWS_LABEL]->(t2:TrainingLabel)
    WHERE coalesce(r.resolved, false) = false
      AND t2.include = true
    RETURN count(r) AS pending
}
RETURN total_labels, verified_labels, agreements, disagreements, pending
"""

GET_LABEL_VERIFIER_SCORECARD = """
MATCH (r:LabelVerificationReview)
WHERE r.resolved = true
  AND r.model_a_was_correct IS NOT NULL
RETURN
    count(r)                                                          AS total_resolved,
    sum(CASE WHEN r.model_a_was_correct THEN 1 ELSE 0 END)           AS model_a_correct,
    sum(CASE WHEN r.model_b_was_correct THEN 1 ELSE 0 END)           AS model_b_correct,
    sum(CASE WHEN r.model_a_was_correct
              AND r.model_b_was_correct THEN 1 ELSE 0 END)           AS both_correct,
    sum(CASE WHEN NOT r.model_a_was_correct
             AND NOT r.model_b_was_correct THEN 1 ELSE 0 END)        AS both_wrong,
    sum(CASE WHEN r.model_a_was_correct
             AND NOT r.model_b_was_correct THEN 1 ELSE 0 END)        AS only_a_correct,
    sum(CASE WHEN NOT r.model_a_was_correct
              AND r.model_b_was_correct THEN 1 ELSE 0 END)           AS only_b_correct
"""
