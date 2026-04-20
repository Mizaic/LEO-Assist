"""Cypher queries for the HITL classification review workflow.

Atlas trace:
  DO: DO-BE96444E
  DI: DI-BAC284B4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BE96444E")

ClassificationVote nodes record a human reviewer's verdict on encounters
where the two classification models disagreed.  Each vote links back to the
Encounter so the correct label can be applied and the model score-card updated.
"""

# ------------------------------------------------------------------
# Read queries
# ------------------------------------------------------------------

GET_CLASSIFICATION_DISAGREEMENTS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
  AND e.classification_consensus_agreement = false
  AND e.classification_content_type IS NOT NULL
OPTIONAL MATCH (e)<-[:REVIEWS]-(v:ClassificationVote)
RETURN
    e.id                                  AS encounter_id,
    toString(e.date)                      AS date,
    e.text                                AS text,
    e.classification_content_type         AS consensus_type,
    e.classification_model_a_type         AS model_a_type,
    e.classification_model_b_type         AS model_b_type,
    e.classification_domains              AS domains,
    e.classification_clinical_significance AS clinical_significance,
    e.classification_run_id               AS run_id,
    v.correct_type                        AS voted_type,
    v.reviewer                            AS reviewer,
    v.voted_at                            AS voted_at
ORDER BY e.date DESC
"""

GET_ALL_DISAGREEMENTS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE e.classification_consensus_agreement = false
  AND e.classification_content_type IS NOT NULL
OPTIONAL MATCH (e)<-[:REVIEWS]-(v:ClassificationVote)
RETURN
    toString(p.id)                        AS patient_id,
    e.id                                  AS encounter_id,
    toString(e.date)                      AS date,
    e.text                                AS text,
    e.classification_content_type         AS consensus_type,
    e.classification_model_a_type         AS model_a_type,
    e.classification_model_b_type         AS model_b_type,
    e.classification_domains              AS domains,
    e.classification_clinical_significance AS clinical_significance,
    e.classification_run_id               AS run_id,
    v.correct_type                        AS voted_type,
    v.reviewer                            AS reviewer,
    v.voted_at                            AS voted_at
ORDER BY e.date DESC
SKIP $skip
LIMIT $limit
"""

COUNT_DISAGREEMENTS_PENDING_REVIEW = """
MATCH (e:Encounter)
WHERE e.classification_consensus_agreement = false
  AND e.classification_content_type IS NOT NULL
  AND NOT (e)<-[:REVIEWS]-(:ClassificationVote)
RETURN count(e) AS pending_count
"""

GET_MODEL_SCORECARD = """
MATCH (v:ClassificationVote)
RETURN
    sum(CASE WHEN v.model_a_was_correct THEN 1 ELSE 0 END) AS model_a_correct,
    sum(CASE WHEN v.model_b_was_correct THEN 1 ELSE 0 END) AS model_b_correct,
    sum(CASE WHEN NOT v.model_a_was_correct AND NOT v.model_b_was_correct THEN 1 ELSE 0 END) AS both_wrong,
    count(v) AS total_votes
"""

GET_FEW_SHOT_EXAMPLES = """
MATCH (e:Encounter)<-[:REVIEWS]-(v:ClassificationVote)
WHERE v.correct_type = $content_type
  AND (NOT v.model_a_was_correct OR NOT v.model_b_was_correct)
  AND e.text IS NOT NULL
  AND size(trim(e.text)) > 80
WITH e, v,
     CASE WHEN NOT v.model_a_was_correct AND NOT v.model_b_was_correct THEN 0 ELSE 1 END AS priority
ORDER BY priority ASC, v.voted_at DESC
LIMIT $limit
RETURN e.text AS text, v.correct_type AS content_type, v.notes AS notes
"""

GET_ALL_VOTED = """
MATCH (e:Encounter)<-[:REVIEWS]-(v:ClassificationVote)
OPTIONAL MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e)
RETURN
    coalesce(elementId(p), '')    AS patient_id,
    e.id                          AS encounter_id,
    toString(e.date)              AS encounter_date,
    v.model_a_type                AS haiku_predicted,
    v.model_b_type                AS gpt_predicted,
    v.correct_type                AS human_verdict,
    v.model_a_was_correct         AS haiku_correct,
    v.model_b_was_correct         AS gpt_correct,
    v.reviewer                    AS reviewer,
    toString(v.voted_at)          AS voted_at,
    coalesce(v.notes, '')         AS notes
ORDER BY v.voted_at DESC
"""

GET_CONFUSION_BREAKDOWN = """
MATCH (v:ClassificationVote)
RETURN
    v.model_a_type    AS haiku_predicted,
    v.model_b_type    AS gpt_predicted,
    v.correct_type    AS human_verdict,
    count(v)          AS n
ORDER BY human_verdict, haiku_predicted
"""

# ------------------------------------------------------------------
# Write queries
# ------------------------------------------------------------------

UPSERT_CLASSIFICATION_VOTE = """
MATCH (e:Encounter {id: $encounter_id})
MERGE (e)<-[:REVIEWS]-(v:ClassificationVote {encounter_id: $encounter_id})
SET
    v.correct_type        = $correct_type,
    v.model_a_was_correct = $model_a_was_correct,
    v.model_b_was_correct = $model_b_was_correct,
    v.reviewer            = $reviewer,
    v.notes               = $notes,
    v.voted_at            = datetime(),
    v.model_a_type        = $model_a_type,
    v.model_b_type        = $model_b_type
WITH e, v
SET e.classification_content_type    = $correct_type,
    e.classification_human_corrected = true
RETURN v.encounter_id AS encounter_id, v.correct_type AS correct_type
"""
