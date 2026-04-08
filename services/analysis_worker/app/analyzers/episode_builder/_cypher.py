"""Cypher query constants for episode building."""

# Benign closure: "No evidence of cancer found" coded in the window
BENIGN_CLOSURE_QUERY = (
    "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c) "
    "WHERE toString(p.id) = $patient_id "
    "  AND c.conceptId = $concept_id "
    "  AND coalesce(r.assertion, 'present') = 'present' "
    "  AND toString(e.date) >= $after_date "
    "  AND toString(e.date) <= $before_date "
    "RETURN "
    "    toString(e.id)   AS encounter_id, "
    "    toString(e.date) AS encounter_date, "
    "    c.conceptId      AS concept_id, "
    "    c.name           AS concept_name "
    "ORDER BY encounter_date"
)

MERGE_EPISODE = (
    "MATCH (p:Patient) WHERE toString(p.id) = $patient_id "
    "MERGE (ep:EpisodeOfCare {episode_id: $episode_id}) "
    "SET ep.patient_id              = $patient_id, "
    "    ep.domain_id               = $domain_id, "
    "    ep.condition_type          = $condition_type, "
    "    ep.cancer_type             = $cancer_type, "
    "    ep.referral_date           = $referral_date, "
    "    ep.end_date                = $end_date, "
    "    ep.specialist_seen         = $specialist_seen, "
    "    ep.specialist_visit_date   = $specialist_visit_date, "
    "    ep.referral_site           = $referral_site, "
    "    ep.referral_route          = $referral_route, "
    "    ep.place_of_presentation   = $place_of_presentation, "
    "    ep.first_presentation_date = $first_presentation_date, "
    "    ep.presenting_complaint    = $presenting_complaint, "
    "    ep.status                  = $status, "
    "    ep.auto_closed             = $auto_closed, "
    "    ep.auto_close_reason       = $auto_close_reason, "
    "    ep.hitl_flag               = $hitl_flag, "
    "    ep.hitl_reason             = $hitl_reason, "
    "    ep.letter_inferred_benign  = $letter_inferred_benign, "
    "    ep.cancer_stage            = coalesce(ep.cancer_stage, 'unknown'), "
    "    ep.cancer_stage_raw        = coalesce(ep.cancer_stage_raw, ''), "
    "    ep.cancer_stage_group      = coalesce(ep.cancer_stage_group, ''), "
    "    ep.tnm_t                   = coalesce(ep.tnm_t, ''), "
    "    ep.tnm_n                   = coalesce(ep.tnm_n, ''), "
    "    ep.tnm_m                   = coalesce(ep.tnm_m, ''), "
    "    ep.staging_system          = coalesce(ep.staging_system, 'unknown'), "
    "    ep.staging_source          = coalesce(ep.staging_source, 'none'), "
    "    ep.staging_confidence      = coalesce(ep.staging_confidence, 0.0), "
    "    ep.updated_at              = datetime() "
    "MERGE (p)-[:HAS_EPISODE_OF_CARE]->(ep) "
    "RETURN ep"
)

LINK_ENCOUNTERS = (
    "UNWIND $encounters AS e "
    "OPTIONAL MATCH (enc:Encounter {id: e.encounter_id}) "
    "WITH enc, e WHERE enc IS NOT NULL "
    "MATCH (ep:EpisodeOfCare {episode_id: $episode_id}) "
    "MERGE (enc)-[r:IS_PART_OF]->(ep) "
    "ON CREATE SET r.milestone_type = e.milestone_type, "
    "              r.linked_by = 'episode_builder', "
    "              r.linked_at = datetime() "
)

STALE_CLOSE_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.patient_id = $patient_id
  AND ep.episode_id IN $episode_ids
  AND ep.status = 'in_progress'
  AND ep.auto_closed <> true
WITH ep,
     date(ep.referral_date) AS ref_date,
     CASE
       WHEN ep.specialist_seen = true AND ep.specialist_visit_date IS NOT NULL
         THEN date(ep.specialist_visit_date)
       ELSE date(ep.referral_date)
     END AS spec_date,
     date() AS today
SET ep.status = CASE
      WHEN ep.specialist_seen = true
           AND duration.inDays(spec_date, today).days > $post_spec_days
        THEN 'stale_post_specialist'
      WHEN duration.inDays(ref_date, today).days > $hard_days
        THEN 'stale_no_diagnosis'
      ELSE ep.status
    END,
    ep.auto_closed = CASE
      WHEN ep.specialist_seen = true
           AND duration.inDays(spec_date, today).days > $post_spec_days THEN true
      WHEN duration.inDays(ref_date, today).days > $hard_days THEN true
      ELSE false
    END,
    ep.auto_close_reason = CASE
      WHEN ep.specialist_seen = true
           AND duration.inDays(spec_date, today).days > $post_spec_days
        THEN 'auto_stale_90d_post_specialist'
      WHEN duration.inDays(ref_date, today).days > $hard_days
        THEN 'auto_stale_12m_no_diagnosis'
      ELSE null
    END,
    ep.hitl_flag = CASE
      WHEN ep.specialist_seen = true
           AND duration.inDays(spec_date, today).days > $post_spec_days THEN true
      WHEN duration.inDays(ref_date, today).days > $hard_days THEN true
      ELSE ep.hitl_flag
    END,
    ep.hitl_reason = CASE
      WHEN ep.specialist_seen = true
           AND duration.inDays(spec_date, today).days > $post_spec_days
        THEN 'Auto-closed: specialist seen >90 days ago with no diagnosis coded. Verify pathway outcome.'
      WHEN duration.inDays(ref_date, today).days > $hard_days
        THEN 'Auto-closed: >12 months since referral, no diagnosis coded. Verify pathway outcome.'
      ELSE ep.hitl_reason
    END
"""

INFERENCE_FETCH_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.patient_id = $patient_id
  AND ep.episode_id IN $episode_ids
  AND ep.status = 'stale_post_specialist'
  AND ep.inferred_outcome IS NULL
  AND ep.specialist_visit_date IS NOT NULL
RETURN ep.episode_id AS episode_id,
       toString(ep.specialist_visit_date) AS specialist_date
"""

INFERENCE_ENC_Q = """
MATCH (p:Patient {id: $pid})-[:HAS_ENCOUNTER]->(enc:Encounter)
WHERE enc.date > $from_date AND enc.date <= $to_date
RETURN enc.date AS date, enc.flags AS flags, enc.text AS text
ORDER BY enc.date
"""

INFERENCE_UPDATE_Q = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})
SET ep.inferred_outcome      = $inferred_outcome,
    ep.inferred_outcome_date = $inferred_outcome_date,
    ep.inferred_confidence   = $inferred_confidence,
    ep.inference_signals     = $inference_signals,
    ep.hitl_flag = CASE
      WHEN $inferred_outcome IS NULL THEN true
      ELSE ep.hitl_flag END,
    ep.hitl_reason = CASE
      WHEN $inferred_outcome IS NULL THEN coalesce(ep.hitl_reason, 'No post-specialist signals found in 180d window.')
      ELSE ('Inferred ' + $inferred_outcome + ' from post-specialist encounters. Confidence: ' + toString($inferred_confidence) + '. Signals: ' + $inference_signals)
    END,
    ep.updated_at = datetime()
"""

RELATED_CLOSE_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.patient_id = $patient_id
  AND ep.episode_id IN $episode_ids
  AND ep.cancer_type = 'non_site_specific'
  AND NOT ep.status IN ['closed_related', 'closed_phantom', 'merged']
  AND ep.auto_closed <> true
WITH ep
MATCH (other:EpisodeOfCare)
WHERE other.patient_id = $patient_id
  AND other.cancer_type <> 'non_site_specific'
  AND other.episode_id <> ep.episode_id
  AND NOT other.status IN ['merged', 'closed_phantom']
  AND abs(duration.inDays(date(other.referral_date), date(ep.referral_date)).days) <= $window_days
SET ep.status          = 'closed_related',
    ep.auto_closed     = true,
    ep.auto_close_reason = 'auto_related_cancer_found_other_pathway',
    ep.hitl_flag       = true,
    ep.hitl_reason     = 'Auto-closed: specific-site episode (' + other.cancer_type +
                         ') exists within window. NSS companion pathway closed.'
"""

FETCH_EPISODES_FOR_MERGE_Q = (
    "MATCH (ep:EpisodeOfCare {patient_id: $patient_id}) "
    "WHERE NOT ep.status IN ['merged', 'closed_phantom'] "
    "  AND ep.cancer_type IS NOT NULL "
    "  AND ep.referral_date IS NOT NULL "
    "RETURN ep.episode_id AS episode_id, ep.cancer_type AS cancer_type, "
    "       toString(ep.referral_date) AS referral_date, ep.status AS status"
)

MARK_MERGED_Q = (
    "MATCH (dup:EpisodeOfCare {episode_id: $dup_id}) "
    "MATCH (primary:EpisodeOfCare {episode_id: $primary_id}) "
    "SET dup.status          = 'merged', "
    "    dup.merged_into     = $primary_id, "
    "    dup.merged_at       = datetime(), "
    "    dup.merge_reasoning = $reasoning "
    "WITH dup, primary "
    "OPTIONAL MATCH (enc:Encounter)-[r:IS_PART_OF]->(dup) "
    "WITH enc, r, primary WHERE enc IS NOT NULL "
    "MERGE (enc)-[r2:IS_PART_OF]->(primary) "
    "ON CREATE SET r2.milestone_type = r.milestone_type, "
    "              r2.linked_by = 'episode_builder_merge', "
    "              r2.linked_at = datetime()"
)

REFERRAL_CONTEXT_TEXT_Q = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
  AND toString(e.date) >= $start_date
  AND toString(e.date) <= $end_date
  AND e.text IS NOT NULL
RETURN toString(e.date) AS encounter_date, e.text AS text
ORDER BY encounter_date
"""
