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

BENIGN_QUALIFIER_CLOSURE_QUERY = (
    "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[rf:DOCUMENTS]->(c_f) "
    "WHERE toString(p.id) = $patient_id "
    "  AND toString(e.date) >= $after_date "
    "  AND toString(e.date) <= $before_date "
    "  AND toLower(coalesce(c_f.semanticTag, '')) IN $finding_tags "
    "  AND coalesce(rf.assertion, 'present') IN $assertions "
    "  AND EXISTS { "
    "      MATCH (e)-[rq:DOCUMENTS]->(c_q) "
    "      WHERE toString(c_q.conceptId) IN $qualifier_ids "
    "        AND coalesce(rq.assertion, 'present') IN $assertions "
    "  } "
    "RETURN "
    "    toString(e.id)   AS encounter_id, "
    "    toString(e.date) AS encounter_date, "
    "    c_f.conceptId    AS concept_id, "
    "    c_f.name         AS concept_name "
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
    "    ep.referral_match_method   = $referral_match_method, "
    "    ep.referral_inferred       = $referral_inferred, "
    "    ep.first_seen_date         = $first_seen_date, "
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
    "MATCH (ep:EpisodeOfCare {episode_id: $episode_id}) "
    "OPTIONAL MATCH (:Encounter)-[r_old:IS_PART_OF]->(ep) "
    "DELETE r_old "
    "WITH ep "
    "UNWIND $encounters AS e "
    "OPTIONAL MATCH (enc:Encounter {id: e.encounter_id}) "
    "WITH ep, enc, e WHERE enc IS NOT NULL "
    "MERGE (enc)-[r:IS_PART_OF]->(ep) "
    "SET r.milestone_type = e.milestone_type, "
    "    r.referral_subtype = e.referral_subtype, "
    "    r.linked_by = 'episode_builder', "
    "    r.linked_at = datetime() "
)

STALE_CLOSE_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.patient_id = $patient_id
  AND ep.episode_id IN $episode_ids
  AND ep.status = 'in_progress'
  AND ep.auto_closed <> true
WITH ep,
     CASE
       WHEN ep.referral_date IS NULL
            OR trim(toString(ep.referral_date)) = ''
         THEN null
       ELSE date(ep.referral_date)
     END AS ref_date,
     date() AS today
WITH ep, ref_date, today,
     CASE
       WHEN ep.specialist_seen = true
            AND ep.specialist_visit_date IS NOT NULL
            AND trim(toString(ep.specialist_visit_date)) <> ''
         THEN date(ep.specialist_visit_date)
       ELSE ref_date
     END AS spec_date,
     EXISTS {
       MATCH (:Encounter)-[r:IS_PART_OF]->(ep)
       WHERE r.milestone_type IN ['diagnosis_confirmed', 'diagnosis']
     } AS has_dx,
     EXISTS {
       MATCH (:Encounter)-[r:IS_PART_OF]->(ep)
       WHERE r.milestone_type IN ['benign_closure', 'treatment_started']
     } AS has_benign_or_treatment
// DI-LEO-AI-159: never mark an episode stale if a diagnosis-confirmed,
// benign-closure, or treatment-started milestone is linked. Such episodes
// reflect a real clinical outcome that should not be auto-closed as
// "lost to follow-up".
WHERE NOT (has_dx OR has_benign_or_treatment)
SET ep.status = CASE
      WHEN ep.specialist_seen = true
           AND spec_date IS NOT NULL
           AND duration.inDays(spec_date, today).days > $post_spec_days
        THEN 'stale_post_specialist'
      WHEN ref_date IS NOT NULL
           AND duration.inDays(ref_date, today).days > $hard_days
        THEN 'stale_no_diagnosis'
      ELSE ep.status
    END,
    ep.auto_closed = CASE
      WHEN ep.specialist_seen = true
           AND spec_date IS NOT NULL
           AND duration.inDays(spec_date, today).days > $post_spec_days THEN true
      WHEN ref_date IS NOT NULL
           AND duration.inDays(ref_date, today).days > $hard_days THEN true
      ELSE false
    END,
    ep.auto_close_reason = CASE
      WHEN ep.specialist_seen = true
           AND spec_date IS NOT NULL
           AND duration.inDays(spec_date, today).days > $post_spec_days
        THEN 'auto_stale_90d_post_specialist'
      WHEN ref_date IS NOT NULL
           AND duration.inDays(ref_date, today).days > $hard_days
        THEN 'auto_stale_12m_no_diagnosis'
      ELSE null
    END,
    ep.hitl_flag = CASE
      WHEN ep.specialist_seen = true
           AND spec_date IS NOT NULL
           AND duration.inDays(spec_date, today).days > $post_spec_days THEN true
      WHEN ref_date IS NOT NULL
           AND duration.inDays(ref_date, today).days > $hard_days THEN true
      ELSE ep.hitl_flag
    END,
    ep.hitl_reason = CASE
      WHEN ep.specialist_seen = true
           AND spec_date IS NOT NULL
           AND duration.inDays(spec_date, today).days > $post_spec_days
        THEN 'Auto-closed: specialist seen >90 days ago with no diagnosis coded. Verify pathway outcome.'
      WHEN ref_date IS NOT NULL
           AND duration.inDays(ref_date, today).days > $hard_days
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
  AND other.referral_date IS NOT NULL
  AND ep.referral_date IS NOT NULL
  AND abs(duration.inDays(date(other.referral_date), date(ep.referral_date)).days) <= $window_days
SET ep.status          = 'closed_related',
    ep.auto_closed     = true,
    ep.auto_close_reason = 'auto_related_cancer_found_other_pathway',
    ep.hitl_flag       = true,
    ep.hitl_reason     = 'Auto-closed: specific-site episode (' + other.cancer_type +
                         ') exists within window. NSS companion pathway closed.'
"""

FETCH_EPISODES_FOR_MERGE_Q = (
    # DI-LEO-AI-137: return ALL non-merged episodes (including
    # floating/diagnosis-only episodes with NULL referral_date and NSS
    # episodes). The evidence-wins merger clusters by date and
    # re-extracts cancer_type from diagnosis encounter text, so the
    # legacy WHERE clauses that filtered on cancer_type/referral_date
    # being non-null are removed.
    "MATCH (ep:EpisodeOfCare {patient_id: $patient_id}) "
    "WHERE NOT ep.status IN ['merged', 'closed_phantom'] "
    "OPTIONAL MATCH (e:Encounter)-[link:IS_PART_OF]->(ep) "
    "  WHERE link.milestone_type IN ['diagnosis', 'diagnosis_confirmed'] "
    "WITH ep, collect(DISTINCT coalesce(e.text, '')) AS diagnosis_texts "
    "OPTIONAL MATCH (t:Encounter)-[tlink:IS_PART_OF]->(ep) "
    "  WHERE tlink.milestone_type = 'treatment_started' "
    "WITH ep, diagnosis_texts, count(t) AS treatment_count "
    "RETURN ep.episode_id         AS episode_id, "
    "       ep.cancer_type        AS cancer_type, "
    "       toString(ep.referral_date) AS referral_date, "
    "       toString(coalesce(ep.end_date, ep.referral_date)) AS end_date, "
    "       ep.status             AS status, "
    "       diagnosis_texts       AS diagnosis_texts, "
    "       treatment_count       AS treatment_count, "
    "       coalesce(ep.referral_match_method, 'strict_site') AS match_method"
)

# DI-LEO-AI-137: move all IS_PART_OF milestone links from a duplicate
# episode onto its primary, de-duplicating by (encounter_id,
# milestone_type) so we do not create redundant edges. The duplicate
# is then marked merged in the same transaction via ``MARK_MERGED_Q``.
MOVE_LINKS_Q = """
MATCH (e:Encounter)-[old:IS_PART_OF]->(dup:EpisodeOfCare {episode_id: $dup_id})
MATCH (primary:EpisodeOfCare {episode_id: $primary_id})
WITH e, old, dup, primary, old.milestone_type AS mtype
OPTIONAL MATCH (e)-[existing:IS_PART_OF {milestone_type: mtype}]->(primary)
FOREACH (_ IN CASE WHEN existing IS NULL THEN [1] ELSE [] END |
  MERGE (e)-[new:IS_PART_OF {milestone_type: mtype}]->(primary)
  SET new.created_at = coalesce(old.created_at, datetime()),
      new.referral_subtype = coalesce(old.referral_subtype, ''),
      new.linked_by = 'merge_duplicate'
)
DELETE old
"""

# DI-LEO-AI-403 (Pattern N2): post-merge same-day referral collapse.
# After merges complete on a primary episode, sweep its referral
# IS_PART_OF edges and keep only one per date. Subtype priority
# matches the Python helper in _milestone_dedup.py:
#     prism (0) -> form_field (1) -> text_generic (2) -> other (3).
# Ties on rank are broken by earliest created_at, then stable
# elementId. The kept edge survives; the rest are deleted.
COLLAPSE_SAME_DAY_REFERRALS_Q = """
MATCH (e:Encounter)-[r:IS_PART_OF {milestone_type: 'referral'}]
      ->(ep:EpisodeOfCare {episode_id: $primary_id})
WITH ep, e.date AS day, r,
     CASE coalesce(r.referral_subtype, '')
       WHEN 'prism' THEN 0
       WHEN 'form_field' THEN 1
       WHEN 'text_generic' THEN 2
       ELSE 3
     END AS rank,
     coalesce(r.created_at, datetime()) AS ts,
     elementId(r) AS rid
ORDER BY rank, ts, rid
WITH ep, day, collect(r) AS rels
WHERE size(rels) > 1
FOREACH (extra IN tail(rels) | DELETE extra)
"""

MARK_MERGED_Q = (
    "MATCH (dup:EpisodeOfCare {episode_id: $dup_id}) "
    "MATCH (primary:EpisodeOfCare {episode_id: $primary_id}) "
    "SET dup.status          = 'merged', "
    "    dup.merged_into     = $primary_id, "
    "    dup.merged_at       = datetime(), "
    "    dup.merge_reasoning = $reasoning "
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
