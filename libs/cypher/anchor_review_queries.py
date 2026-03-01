"""Cypher queries for the anchor domain review workflow.

AnchorReview nodes record the dual-model domain classification of each
training record.  AnchorVote nodes record a human reviewer's verdict on
records where the two models disagreed.
"""

# ------------------------------------------------------------------
# Write queries
# ------------------------------------------------------------------

UPSERT_ANCHOR_REVIEW = """
MERGE (r:AnchorReview {encounter_id: $encounter_id, milestone_type: $milestone_type})
SET r.patient_id            = $patient_id,
    r.original_label        = $original_label,
    r.text                  = $text,
    r.original_concept_id   = $original_concept_id,
    r.model_a_domain        = $model_a_domain,
    r.model_a_concept_correct = $model_a_concept_correct,
    r.model_a_assertion     = $model_a_assertion,
    r.model_a_rationale     = $model_a_rationale,
    r.model_a_target_rule   = $model_a_target_rule,
    r.model_b_domain        = $model_b_domain,
    r.model_b_concept_correct = $model_b_concept_correct,
    r.model_b_assertion     = $model_b_assertion,
    r.model_b_rationale     = $model_b_rationale,
    r.model_b_target_rule   = $model_b_target_rule,
    r.consensus_agreement   = $consensus_agreement,
    r.final_domain          = $final_domain,
    r.non_cancer_flag       = $non_cancer_flag,
    r.reviewed_at           = datetime()
WITH r
OPTIONAL MATCH (e:Encounter {id: $encounter_id})
FOREACH (_ IN CASE WHEN e IS NOT NULL THEN [1] ELSE [] END |
  MERGE (r)-[:REVIEWS]->(e)
)
"""

UPSERT_ANCHOR_VOTE = """
MATCH (r:AnchorReview {encounter_id: $encounter_id, milestone_type: $milestone_type})
MERGE (r)<-[:VOTED_ON]-(v:AnchorVote {
  encounter_id:   $encounter_id,
  milestone_type: $milestone_type
})
SET v.correct_domain        = $correct_domain,
    v.model_a_was_correct   = $model_a_was_correct,
    v.model_b_was_correct   = $model_b_was_correct,
    v.reviewer              = $reviewer,
    v.notes                 = $notes,
    v.voted_at              = datetime(),
    v.model_a_domain        = $model_a_domain,
    v.model_b_domain        = $model_b_domain
WITH r, v
SET r.human_domain          = $correct_domain,
    r.human_corrected       = true
RETURN v.encounter_id AS encounter_id, v.correct_domain AS correct_domain
"""

# ------------------------------------------------------------------
# Read queries
# ------------------------------------------------------------------

GET_ALL_ANCHOR_DISAGREEMENTS = """
MATCH (r:AnchorReview)
WHERE r.consensus_agreement = false
OPTIONAL MATCH (r)<-[:VOTED_ON]-(v:AnchorVote)
RETURN
    r.encounter_id          AS encounter_id,
    r.milestone_type        AS milestone_type,
    r.patient_id            AS patient_id,
    r.original_label        AS original_label,
    r.text                  AS text,
    r.original_concept_id   AS original_concept_id,
    r.model_a_domain        AS model_a_domain,
    r.model_a_concept_correct AS model_a_concept_correct,
    r.model_a_assertion     AS model_a_assertion,
    r.model_a_rationale     AS model_a_rationale,
    r.model_a_target_rule   AS model_a_target_rule,
    r.model_b_domain        AS model_b_domain,
    r.model_b_concept_correct AS model_b_concept_correct,
    r.model_b_assertion     AS model_b_assertion,
    r.model_b_rationale     AS model_b_rationale,
    r.model_b_target_rule   AS model_b_target_rule,
    r.non_cancer_flag       AS non_cancer_flag,
    r.human_domain          AS voted_domain,
    v.reviewer              AS reviewer,
    toString(v.voted_at)    AS voted_at
ORDER BY r.non_cancer_flag DESC, r.reviewed_at DESC
SKIP $skip
LIMIT $limit
"""

GET_NON_CANCER_FLAGS = """
MATCH (r:AnchorReview)
WHERE r.non_cancer_flag = true
OPTIONAL MATCH (r)<-[:VOTED_ON]-(v:AnchorVote)
RETURN
    r.encounter_id          AS encounter_id,
    r.milestone_type        AS milestone_type,
    r.patient_id            AS patient_id,
    r.original_label        AS original_label,
    r.text                  AS text,
    r.original_concept_id   AS original_concept_id,
    r.model_a_domain        AS model_a_domain,
    r.model_b_domain        AS model_b_domain,
    r.consensus_agreement   AS consensus_agreement,
    r.human_domain          AS voted_domain,
    v.reviewer              AS reviewer
ORDER BY r.original_label DESC, r.reviewed_at DESC
SKIP $skip
LIMIT $limit
"""

COUNT_ANCHOR_DISAGREEMENTS_PENDING = """
MATCH (r:AnchorReview)
WHERE r.consensus_agreement = false
  AND r.human_corrected IS NULL
RETURN count(r) AS pending_count
"""

COUNT_NON_CANCER_PENDING = """
MATCH (r:AnchorReview)
WHERE r.non_cancer_flag = true
  AND r.human_corrected IS NULL
RETURN count(r) AS pending_count
"""

GET_ANCHOR_SCORECARD = """
MATCH (v:AnchorVote)
RETURN
    sum(CASE WHEN v.model_a_was_correct THEN 1 ELSE 0 END)  AS model_a_correct,
    sum(CASE WHEN v.model_b_was_correct THEN 1 ELSE 0 END)  AS model_b_correct,
    sum(CASE WHEN NOT v.model_a_was_correct AND NOT v.model_b_was_correct THEN 1 ELSE 0 END)
        AS both_wrong,
    count(v) AS total_votes
"""

GET_ANCHOR_DOMAIN_DISTRIBUTION = """
MATCH (r:AnchorReview)
RETURN
    r.final_domain          AS domain,
    r.milestone_type        AS milestone_type,
    count(r)                AS n
ORDER BY milestone_type, n DESC
"""

GET_REVIEWED_TARGET_RULES = """
MATCH (r:AnchorReview)
WHERE r.consensus_agreement = true OR r.human_corrected = true
WITH
    CASE WHEN r.human_corrected = true THEN r.human_domain
         ELSE r.final_domain END AS domain,
    r.model_a_target_rule AS rule_a,
    r.model_b_target_rule AS rule_b
WHERE domain IS NOT NULL
  AND domain <> 'DISAGREEMENT'
  AND domain <> 'AMBIGUOUS'
  AND domain <> 'NON_CANCER'
RETURN
    domain,
    collect(DISTINCT rule_a)[0..200] AS rules_a,
    collect(DISTINCT rule_b)[0..200] AS rules_b
ORDER BY domain
"""
