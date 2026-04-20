"""Cypher queries for dual-model label verification and HITL resolution.

Atlas trace:
  DO: DO-BE96444E
  DI: DI-BAC284B4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BE96444E")

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
    r.model_a_confidence      = $model_a_confidence,
    r.model_b_label           = $model_b_label,
    r.model_b_rationale       = $model_b_rationale,
    r.model_b_confidence      = $model_b_confidence,
    r.auto_resolve_method     = $auto_resolve_method,
    r.auto_resolve_confidence = $auto_resolve_confidence,
    r.auto_resolve_reason     = $auto_resolve_reason,
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
    r.resolved_model_tier     = CASE WHEN $reviewer STARTS WITH 'auto_triage:escalation:'
                                     THEN substring($reviewer, 22)
                                     ELSE null END,
    r.resolved_method         = CASE WHEN $reviewer STARTS WITH 'auto_triage:'
                                     THEN substring($reviewer, 12)
                                     ELSE 'human' END,
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
ORDER BY r.created_at DESC, r.review_id ASC
SKIP $skip
LIMIT $limit
"""

GET_VERIFICATION_HISTORY = """
MATCH (r:LabelVerificationReview)-[:REVIEWS_LABEL]->(t:TrainingLabel)
WHERE coalesce(r.resolved, false) = true
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
    r.resolved_label          AS resolved_label,
    r.resolved_by             AS resolved_by,
    toString(r.resolved_at)   AS resolved_at,
    toString(r.created_at)    AS created_at,
    t.text                    AS text,
    t.entities_json           AS entities_json,
    t.source                  AS source
ORDER BY r.resolved_at DESC, r.review_id ASC
SKIP $skip
LIMIT $limit
"""

COUNT_VERIFICATION_QUEUE_PENDING = """
MATCH (r:LabelVerificationReview)-[:REVIEWS_LABEL]->(t:TrainingLabel)
WHERE coalesce(r.resolved, false) = false
  AND t.include = true
RETURN count(r) AS pending
"""

COUNT_VERIFICATION_HISTORY = """
MATCH (r:LabelVerificationReview)-[:REVIEWS_LABEL]->(t:TrainingLabel)
WHERE coalesce(r.resolved, false) = true
  AND t.include = true
RETURN count(r) AS total
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

GET_LABEL_VERIFIER_SCORECARD_BREAKDOWN = """
MATCH (r:LabelVerificationReview)
WHERE r.resolved = true
WITH
    coalesce(r.resolved_label, "__UNKNOWN__") AS label,
    coalesce(r.resolved_by, "human") AS resolved_by,
    count(r) AS n,
    sum(CASE WHEN r.model_a_was_correct THEN 1 ELSE 0 END) AS model_a_correct,
    sum(CASE WHEN r.model_b_was_correct THEN 1 ELSE 0 END) AS model_b_correct
RETURN label, resolved_by, n, model_a_correct, model_b_correct
ORDER BY n DESC, label ASC
"""

GET_HITL_REVIEWED_LABEL_IDS = """
MATCH (r:LabelVerificationReview)
WHERE coalesce(r.resolved, false) = true
  AND r.resolved_by IS NOT NULL
  AND NOT r.resolved_by STARTS WITH 'auto_triage:'
RETURN DISTINCT r.label_id AS label_id
"""

DELETE_PENDING_VERIFICATION_REVIEWS = """
MATCH (r:LabelVerificationReview)-[:REVIEWS_LABEL]->(t:TrainingLabel)
WHERE coalesce(r.resolved, false) = false
  AND t.include = true
DETACH DELETE r
"""

RESET_TRAINING_LABEL_VERIFICATION_FIELDS = """
MATCH (t:TrainingLabel)
WHERE t.include = true
SET t.verified_at = null,
    t.verification_agreement = null,
    t.model_a_label = null,
    t.model_b_label = null,
    t.quality_score = null,
    t.updated_at = datetime()
RETURN count(t) AS reset_labels
"""

DELETE_ALL_VERIFICATION_REVIEWS_FOR_INCLUDED = """
MATCH (r:LabelVerificationReview)-[:REVIEWS_LABEL]->(t:TrainingLabel)
WHERE t.include = true
DETACH DELETE r
"""
