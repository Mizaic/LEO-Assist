"""Cypher query strings for the domain-agnostic patient EPR endpoints.

Atlas trace:
  DO: DO-31410049
  DI: DI-F46494AE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-31410049")

Kept in a separate module so patients_epr.py stays within the 500-LOC limit.
All queries accept $search, $condition_type, $has_alerts, $skip, $limit.
Scoped variants additionally require $scope_org_ids.
"""

from libs.auth.org_scope import ORG_PATIENT_FILTER

_ORG_GUARD = ORG_PATIENT_FILTER

# ---------------------------------------------------------------------------
# Shared filter conditions -- used after the initial WHERE (or AND ORG_GUARD)
# ---------------------------------------------------------------------------

# Used directly after "WHERE" in admin queries (no leading AND).
_FILTER_CONDITIONS = (
    "($search IS NULL OR p.id CONTAINS $search) "
    "AND ($condition_type IS NULL OR EXISTS { "
    "  MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep2:EpisodeOfCare) "
    "  WHERE coalesce(ep2.condition_type, ep2.cancer_type) = $condition_type "
    "}) "
    "AND ($has_alerts IS NULL OR $has_alerts = false OR EXISTS { "
    "  MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(a2:SafetyNetAlert) "
    "  WHERE a2.resolved_at IS NULL "
    "}) "
)

# ---------------------------------------------------------------------------
# Aggregation tail -- shared by both list queries
# ---------------------------------------------------------------------------

_AGG_TAIL = (
    "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gpGp:Organization) "
    "OPTIONAL MATCH (p)-[:REGISTERED_IN]->(gpReg:Organization) "
    "WITH p, coalesce(gpGp, gpReg) AS gp "
    "OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "  WHERE NOT ep.status IN ['merged', 'closed_phantom', 'closed_related'] "
    "OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter) "
    "OPTIONAL MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(alert:SafetyNetAlert) "
    "  WHERE alert.resolved_at IS NULL "
    "OPTIONAL MATCH (p)-[:HAS_DOCUMENT_REFERENCE]->(doc:DocumentReference) "
    "OPTIONAL MATCH (rr:ReferralRequest)-[:FOR_PATIENT]->(p) "
    "OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc2:Encounter)-[:DOCUMENTS]->(snomed) "
    "WITH p, gp, "
    "count(DISTINCT ep) AS episode_count, "
    "count(DISTINCT enc) AS encounter_count, "
    "max(toString(enc.date)) AS last_activity, "
    "count(DISTINCT alert) AS active_alert_count, "
    "count(DISTINCT doc) AS document_count, "
    "count(DISTINCT rr) AS referral_count, "
    "count(DISTINCT snomed) AS coded_concept_count, "
    "collect(DISTINCT snomed.semanticTag) AS raw_tags, "
    "collect(DISTINCT coalesce(ep.condition_type, ep.cancer_type)) AS condition_types "
    "RETURN "
    "  p.id AS patient_id, "
    "  coalesce(p.name, p.id) AS display_name, "
    "  p.nhsNumber AS nhs_number, "
    "  p.gender AS gender, "
    "  p.birthDate AS birth_date, "
    "  gp.name AS practice_name, "
    "  episode_count, "
    "  encounter_count, "
    "  last_activity, "
    "  active_alert_count, "
    "  document_count, "
    "  referral_count, "
    "  coded_concept_count, "
    "  [t IN raw_tags WHERE t IS NOT NULL AND t <> ''] AS semantic_tags, "
    "  [ct IN condition_types WHERE ct IS NOT NULL AND ct <> ''] AS condition_types"
)

# ---------------------------------------------------------------------------
# Patient list
# ---------------------------------------------------------------------------

LIST_PATIENTS_SCOPED = (
    "MATCH (p:Patient) "
    "WHERE "
    + _ORG_GUARD
    + " AND "
    + _FILTER_CONDITIONS
    + "WITH p ORDER BY p.id ASC SKIP $skip LIMIT $limit "
    + _AGG_TAIL
)

LIST_PATIENTS_ADMIN = (
    "MATCH (p:Patient) "
    "WHERE "
    + _FILTER_CONDITIONS
    + "WITH p ORDER BY p.id ASC SKIP $skip LIMIT $limit "
    + _AGG_TAIL
)

# ---------------------------------------------------------------------------
# Count queries (same filters, no pagination)
# ---------------------------------------------------------------------------

COUNT_PATIENTS_SCOPED = (
    "MATCH (p:Patient) "
    "WHERE " + _ORG_GUARD + " AND " + _FILTER_CONDITIONS + "RETURN count(p) AS total"
)

COUNT_PATIENTS_ADMIN = (
    "MATCH (p:Patient) " "WHERE " + _FILTER_CONDITIONS + "RETURN count(p) AS total"
)

# ---------------------------------------------------------------------------
# Facets (distinct condition types)
# ---------------------------------------------------------------------------

FACETS_SCOPED = (
    "MATCH (p:Patient) "
    "WHERE " + _ORG_GUARD + " "
    "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "WITH coalesce(ep.condition_type, ep.cancer_type) AS ct "
    "WHERE ct IS NOT NULL AND ct <> '' "
    "RETURN DISTINCT ct AS condition_type "
    "ORDER BY condition_type ASC "
    "LIMIT 50"
)

FACETS_ADMIN = (
    "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "WITH coalesce(ep.condition_type, ep.cancer_type) AS ct "
    "WHERE ct IS NOT NULL AND ct <> '' "
    "RETURN DISTINCT ct AS condition_type "
    "ORDER BY condition_type ASC "
    "LIMIT 50"
)

# ---------------------------------------------------------------------------
# Patient detail
# ---------------------------------------------------------------------------

_EPISODE_COLLECT = (
    "collect(DISTINCT { "
    "  episode_id: coalesce(ep.episode_id, ep.id), "
    "  condition_type: coalesce(ep.condition_type, ep.cancer_type), "
    "  status: ep.status, "
    "  referral_date: toString(ep.referral_date), "
    "  end_date: toString(ep.end_date), "
    "  inferred_outcome: ep.inferred_outcome, "
    "  staging_value: ep.staging_value, "
    "  staging_early_late: ep.staging_early_late, "
    "  referral_route: ep.referral_route, "
    "  place_of_presentation: ep.place_of_presentation, "
    "  prior_consultations_n: ep.prior_consultations_n, "
    "  safety_netting_recorded: ep.safety_netting_recorded, "
    "  first_presentation_date: toString(ep.first_presentation_date) "
    "}) AS episodes"
)

_PATIENT_DETAIL_RETURN = (
    "RETURN "
    "  p.id AS patient_id, "
    "  coalesce(p.name, p.id) AS display_name, "
    "  p.nhsNumber AS nhs_number, "
    "  p.gender AS gender, "
    "  p.birthDate AS birth_date, "
    "  gp.name AS practice_name, "
    "  count(DISTINCT alert) AS active_alert_count, " + _EPISODE_COLLECT
)

_GP_OPTIONAL = (
    "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gpGp:Organization) "
    "OPTIONAL MATCH (p)-[:REGISTERED_IN]->(gpReg:Organization) "
    "WITH p, coalesce(gpGp, gpReg) AS gp "
)

GET_PATIENT_DETAIL_SCOPED = (
    "MATCH (p:Patient {id: $patient_id}) "
    "WHERE "
    + _ORG_GUARD
    + " "
    + _GP_OPTIONAL
    + "OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "OPTIONAL MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(alert:SafetyNetAlert) "
    "  WHERE alert.resolved_at IS NULL "
    "WITH p, gp, ep, alert " + _PATIENT_DETAIL_RETURN
)

GET_PATIENT_DETAIL_ADMIN = (
    "MATCH (p:Patient {id: $patient_id}) "
    + _GP_OPTIONAL
    + "OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "OPTIONAL MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(alert:SafetyNetAlert) "
    "  WHERE alert.resolved_at IS NULL "
    "WITH p, gp, ep, alert " + _PATIENT_DETAIL_RETURN
)

# ---------------------------------------------------------------------------
# Activity timeline
# ---------------------------------------------------------------------------

_TIMELINE_BODY = (
    "CALL { "
    "  WITH p "
    "  OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter) "
    "  RETURN 'encounter' AS item_type, enc.id AS item_id, "
    "         toString(enc.date) AS item_date, "
    "         coalesce(enc.consultation_type, 'Encounter') AS label, "
    "         null AS extra "
    "  UNION "
    "  WITH p "
    "  OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "  RETURN 'episode' AS item_type, coalesce(ep.episode_id, ep.id) AS item_id, "
    "         toString(ep.referral_date) AS item_date, "
    "         coalesce(ep.condition_type, ep.cancer_type, 'Episode') AS label, "
    "         ep.status AS extra "
    "  UNION "
    "  WITH p "
    "  OPTIONAL MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(a:SafetyNetAlert) "
    "  RETURN 'alert' AS item_type, a.id AS item_id, "
    "         toString(a.created_at) AS item_date, "
    "         coalesce(a.alert_type, 'Alert') AS label, "
    "         a.resolved_at AS extra "
    "  UNION "
    "  WITH p "
    "  OPTIONAL MATCH (p)<-[:FOR_PATIENT]-(rr:ReferralRequest) "
    "  RETURN 'referral' AS item_type, rr.id AS item_id, "
    "         toString(coalesce("
    "           rr.eReferralPathwayStart, rr.createdAt, rr.updated_at"
    "         )) AS item_date, "
    "         coalesce(rr.specialty, 'Referral') AS label, "
    "         coalesce(rr.ubrn, rr.id) AS extra "
    "  UNION "
    "  WITH p "
    "  OPTIONAL MATCH (p)<-[:FOR_PATIENT]-(rr_doc:ReferralRequest)"
    "        -[:HAS_DOCUMENT]->(dr:DocumentReference) "
    "  RETURN 'document' AS item_type, dr.id AS item_id, "
    "         toString(coalesce("
    "           dr.creation, dr.date, rr_doc.createdAt,"
    "           rr_doc.eReferralPathwayStart, rr_doc.updated_at"
    "         )) AS item_date, "
    "         coalesce(dr.documentTitle, dr.title, dr.description, 'Document') "
    "           AS label, "
    "         coalesce(dr.contentType, '') AS extra "
    "  UNION "
    "  WITH p "
    "  OPTIONAL MATCH (p)-[:HAS_ASSESSMENT]->(a:Assessment) "
    "  WHERE coalesce(a.type, 'SBAR') = 'SBAR' "
    "  RETURN 'sbar' AS item_type, a.id AS item_id, "
    "         toString(a.created_at) AS item_date, "
    "         'SBAR assessment' AS label, "
    "         coalesce(a.status, '') AS extra "
    "} "
    "WITH item_type, item_id, item_date, label, extra "
    "WHERE item_id IS NOT NULL AND item_date IS NOT NULL "
    "RETURN item_type, item_id, item_date, label, extra "
    "ORDER BY item_date DESC "
    "LIMIT 200"
)

GET_TIMELINE_SCOPED = (
    "MATCH (p:Patient {id: $patient_id}) " "WHERE " + _ORG_GUARD + " " + _TIMELINE_BODY
)

GET_TIMELINE_ADMIN = "MATCH (p:Patient {id: $patient_id}) " + _TIMELINE_BODY

# ---------------------------------------------------------------------------
# Encounter list with text preview
# ---------------------------------------------------------------------------

_ENCOUNTERS_BODY = (
    "MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter) "
    "OPTIONAL MATCH (enc)-[:DOCUMENTS]->(coded) "
    "WITH enc, count(DISTINCT coded) AS doc_coded_count "
    "RETURN enc.id AS encounter_id, "
    "       toString(enc.date) AS encounter_date, "
    "       coalesce(enc.consultation_type, 'Encounter') AS encounter_type, "
    "       enc.specialty AS specialty, "
    "       left(coalesce(enc.text, enc.raw_text, ''), 120) AS text_preview, "
    "       CASE WHEN doc_coded_count > 0 THEN doc_coded_count "
    "            ELSE coalesce(enc.coded_count, 0) END AS coded_count, "
    "       enc.episode_id AS episode_id "
    "ORDER BY encounter_date DESC "
    "LIMIT 200"
)

GET_ENCOUNTERS_SCOPED = (
    "MATCH (p:Patient {id: $patient_id}) "
    "WHERE " + _ORG_GUARD + " " + _ENCOUNTERS_BODY
)

GET_ENCOUNTERS_ADMIN = "MATCH (p:Patient {id: $patient_id}) " + _ENCOUNTERS_BODY

# ---------------------------------------------------------------------------
# Encounter detail (full text + coded terms)
# ---------------------------------------------------------------------------

_ENCOUNTER_DETAIL_BODY = (
    "MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter {id: $encounter_id}) "
    "OPTIONAL MATCH (enc)-[rel:DOCUMENTS]->(concept) "
    "WHERE concept.name IS NOT NULL "
    "WITH enc, collect(DISTINCT {"
    "  code_id: toString(concept.conceptId), "
    "  display: concept.name, "
    "  system: 'SNOMED', "
    "  evidence_sentence: rel.evidence_sentence, "
    "  assertion: rel.assertion, "
    "  confidence: rel.confidence, "
    "  value: rel.value, "
    "  unit: rel.unit"
    "}) AS doc_terms "
    "OPTIONAL MATCH (enc)-[:HAS_CODE]->(code:Code) "
    "WITH enc, doc_terms, collect(DISTINCT {"
    "  code_id: code.code, "
    "  display: code.display, "
    "  system: coalesce(code.system, 'SNOMED')"
    "}) AS legacy_terms "
    "RETURN enc.id AS encounter_id, "
    "       toString(enc.date) AS encounter_date, "
    "       coalesce(enc.consultation_type, 'Encounter') AS encounter_type, "
    "       enc.specialty AS specialty, "
    "       coalesce(enc.text, enc.raw_text, '') AS full_text, "
    "       enc.episode_id AS episode_id, "
    "       doc_terms + [t IN legacy_terms WHERE t.display IS NOT NULL] "
    "       AS coded_terms"
)

GET_ENCOUNTER_DETAIL_SCOPED = (
    "MATCH (p:Patient {id: $patient_id}) "
    "WHERE " + _ORG_GUARD + " " + _ENCOUNTER_DETAIL_BODY
)

GET_ENCOUNTER_DETAIL_ADMIN = (
    "MATCH (p:Patient {id: $patient_id}) " + _ENCOUNTER_DETAIL_BODY
)

# ---------------------------------------------------------------------------
# Documents (DocumentReference nodes)
# ---------------------------------------------------------------------------

# Referral-ingested documents are often linked only via
# (ReferralRequest)-[:HAS_DOCUMENT]->(DocumentReference), not
# (Patient)-[:HAS_DOCUMENT_REFERENCE]. Match both paths (same as
# patient_finder.list_patient_document_references and sbar context
# integrity checks).
_DOCUMENTS_BODY = (
    "CALL { "
    "  WITH p "
    "  MATCH (p)-[:HAS_DOCUMENT_REFERENCE]->(doc:DocumentReference) "
    "  RETURN doc "
    "  UNION "
    "  WITH p "
    "  MATCH (p)<-[:FOR_PATIENT]-(:ReferralRequest)-[:HAS_DOCUMENT]->(doc:DocumentReference) "
    "  RETURN doc "
    "} "
    "WITH p, doc "
    "OPTIONAL MATCH (doc)-[:HAS_CHUNK]->(chunk:Chunk) "
    "WITH p, doc, chunk "
    "ORDER BY coalesce(chunk.ordinal, 0) "
    "WITH p, doc, collect(chunk.text) AS chunk_texts "
    "WITH p, doc, chunk_texts, "
    "  reduce(s = '', t IN chunk_texts | "
    "    CASE WHEN s = '' THEN coalesce(t, '') "
    "    ELSE s + '\\n\\n' + coalesce(t, '') END) AS full_text "
    "OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "WHERE doc.episode_id IS NULL OR ep.episode_id = doc.episode_id "
    "WITH doc, full_text, head(collect(ep)) AS ep "
    "OPTIONAL MATCH (doc)-[:DERIVED_FROM]->(rr_from:ReferralRequest) "
    "OPTIONAL MATCH (rr_via:ReferralRequest)-[:HAS_DOCUMENT]->(doc) "
    "WITH doc, full_text, ep, coalesce(rr_from, rr_via) AS rr "
    "OPTIONAL MATCH (rr)-[:HAS_ASSESSMENT]->(a:Assessment) "
    "WHERE a.type = 'SBAR' OR a IS NULL "
    "WITH doc, full_text, ep, rr, head(collect(a)) AS a "
    "RETURN doc.id AS document_id, "
    "       toString(coalesce("
    "         doc.date, doc.creation, rr.createdAt, rr.eReferralPathwayStart"
    "       )) AS document_date, "
    "       coalesce("
    "         nullif(doc.type, ''), "
    "         CASE "
    "           WHEN rr IS NOT NULL THEN 'Referral document' "
    "           ELSE 'Document' "
    "         END"
    "       ) AS document_type, "
    "       coalesce(doc.title, doc.documentTitle, doc.description, 'Untitled') AS title, "
    "       coalesce("
    "         nullif(doc.category, ''), "
    "         CASE WHEN rr IS NOT NULL THEN 'referral' ELSE '' END"
    "       ) AS category, "
    "       left(coalesce(nullif(doc.text, ''), full_text, ''), 200) AS text_preview, "
    "       coalesce(nullif(doc.text, ''), full_text, '') AS full_text, "
    "       coalesce(doc.contentType, '') AS content_type, "
    "       coalesce(doc.leoOriginalUrl, doc.url, '') AS original_url, "
    "       coalesce(doc.leoMarkdownUrl, '') AS markdown_url, "
    "       coalesce(doc.episode_id, ep.episode_id) AS episode_id, "
    "       coalesce(ep.condition_type, ep.cancer_type, 'General') AS episode_label, "
    "       coalesce(toString(rr.id), '') AS referral_id, "
    "       a.id AS sbar_id, "
    "       a.status AS sbar_status, "
    "       a.situation AS sbar_situation, "
    "       a.background AS sbar_background, "
    "       a.assessment AS sbar_assessment, "
    "       a.recommendation AS sbar_recommendation "
    "ORDER BY document_date DESC "
    "LIMIT 100"
)

GET_DOCUMENTS_SCOPED = (
    "MATCH (p:Patient {id: $patient_id}) " "WHERE " + _ORG_GUARD + " " + _DOCUMENTS_BODY
)

GET_DOCUMENTS_ADMIN = "MATCH (p:Patient {id: $patient_id}) " + _DOCUMENTS_BODY

# ---------------------------------------------------------------------------
# Patient-level SBAR assessments (episode-scoped + rollup)
# ---------------------------------------------------------------------------

_ASSESSMENTS_RETURN = (
    "RETURN a.id AS assessment_id, "
    "       a.episode_id AS episode_id, "
    "       coalesce(ep.condition_type, ep.cancer_type,"
    " 'Patient summary') AS episode_label, "
    "       a.assessment_scope AS scope, "
    "       a.status AS status, "
    "       toString(a.created_at) AS created_at, "
    "       a.situation AS situation, "
    "       a.background AS background, "
    "       a.assessment AS assessment, "
    "       a.recommendation AS recommendation, "
    "       coalesce(a.content, a.raw_text) AS content, "
    "       a.stt AS stt, "
    "       a.stt_evidence AS stt_evidence, "
    "       a.completeness_failed_count AS completeness_failed_count, "
    "       a.background_parts AS background_parts, "
    "       a.completeness_result_json AS completeness_result_json "
    "ORDER BY created_at DESC"
)

_ASSESSMENTS_JOIN = (
    "MATCH (p)-[:HAS_ASSESSMENT]->(a:Assessment) "
    "OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "  WHERE ep.episode_id = a.episode_id "
)

GET_ASSESSMENTS_SCOPED = (
    "MATCH (p:Patient {id: $patient_id}) "
    "WHERE " + _ORG_GUARD + " " + _ASSESSMENTS_JOIN + _ASSESSMENTS_RETURN
)

GET_ASSESSMENTS_ADMIN = (
    "MATCH (p:Patient {id: $patient_id}) " + _ASSESSMENTS_JOIN + _ASSESSMENTS_RETURN
)

# ---------------------------------------------------------------------------
# Safety alerts detail
# ---------------------------------------------------------------------------

_ALERTS_BODY = (
    "OPTIONAL MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(a:SafetyNetAlert) "
    "RETURN a.id AS alert_id, "
    "       coalesce(a.alert_type, 'Alert') AS alert_type, "
    "       coalesce(a.severity, 'medium') AS severity, "
    "       toString(a.created_at) AS created_at, "
    "       toString(a.resolved_at) AS resolved_at, "
    "       a.message AS message, "
    "       a.condition_context AS condition_context, "
    "       a.guideline_ref AS guideline_ref "
    "ORDER BY created_at DESC"
)

GET_ALERTS_SCOPED = (
    "MATCH (p:Patient {id: $patient_id}) " "WHERE " + _ORG_GUARD + " " + _ALERTS_BODY
)

GET_ALERTS_ADMIN = "MATCH (p:Patient {id: $patient_id}) " + _ALERTS_BODY

PATCH_ALERT = (
    "MATCH (p:Patient {id: $patient_id})-[:HAS_SAFETY_NET_ALERT]->"
    "(a:SafetyNetAlert {id: $alert_id}) "
    "SET a.resolved_at = CASE WHEN $action = 'resolve' "
    "    THEN datetime() ELSE a.resolved_at END, "
    "    a.escalated_at = CASE WHEN $action = 'escalate' "
    "    THEN datetime() ELSE a.escalated_at END, "
    "    a.reviewed_by = $reviewed_by, "
    "    a.action = $action "
    "RETURN a.id AS alert_id, "
    "       coalesce(a.alert_type, 'Alert') AS alert_type, "
    "       toString(a.resolved_at) AS resolved_at, "
    "       toString(a.escalated_at) AS escalated_at, "
    "       a.action AS action"
)

# ---------------------------------------------------------------------------
# Episode milestones
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Coded entities (patient-level SNOMED)
# ---------------------------------------------------------------------------

_CODED_ENTITIES_BODY = (
    "CALL { "
    "  WITH p "
    "  MATCH (p)-[:HAS_DISORDER|HAS_DISEASE]->(n) "
    "  WHERE n.name IS NOT NULL "
    "  RETURN 'disorder' AS entity_type, n.name AS name, "
    "         toString(n.conceptId) AS concept_id "
    "  UNION "
    "  WITH p "
    "  MATCH (p)-[:HAS_FINDING|HAS_CLINICAL_FINDING]->(n) "
    "  WHERE n.name IS NOT NULL "
    "  RETURN 'finding' AS entity_type, n.name AS name, "
    "         toString(n.conceptId) AS concept_id "
    "  UNION "
    "  WITH p "
    "  MATCH (p)-[:HAS_SITUATION]->(n) "
    "  WHERE n.name IS NOT NULL "
    "  RETURN 'situation' AS entity_type, n.name AS name, "
    "         toString(n.conceptId) AS concept_id "
    "  UNION "
    "  WITH p "
    "  MATCH (p)-[:HAS_OBSERVABLE|HAS_OBSERVABLE_ENTITY]->(n) "
    "  WHERE n.name IS NOT NULL "
    "  RETURN 'observable' AS entity_type, n.name AS name, "
    "         toString(n.conceptId) AS concept_id "
    "  UNION "
    "  WITH p "
    "  MATCH (p)-[:HAS_PROCEDURE]->(n) "
    "  WHERE n.name IS NOT NULL "
    "  RETURN 'procedure' AS entity_type, n.name AS name, "
    "         toString(n.conceptId) AS concept_id "
    "  UNION "
    "  WITH p "
    "  MATCH (p)-[:HAS_CONCEPT|HAS_PHARMACEUTICAL_BIOLOGIC_PRODUCT]->(n) "
    "  WHERE n.name IS NOT NULL "
    "  RETURN "
    "    CASE "
    "      WHEN toLower(coalesce(n.semanticTag, '')) CONTAINS 'product' "
    "        OR toLower(coalesce(n.semanticTag, '')) CONTAINS 'substance' "
    "      THEN 'medication' "
    "      ELSE 'concept' "
    "    END AS entity_type, "
    "    n.name AS name, "
    "    toString(n.conceptId) AS concept_id "
    "} "
    "WITH entity_type, name, concept_id "
    "WHERE name IS NOT NULL AND entity_type IS NOT NULL "
    "RETURN entity_type, name, concept_id "
    "ORDER BY entity_type, name "
    "LIMIT 200"
)

GET_CODED_ENTITIES_SCOPED = (
    "MATCH (p:Patient {id: $patient_id}) "
    "WHERE " + _ORG_GUARD + " " + _CODED_ENTITIES_BODY
)

GET_CODED_ENTITIES_ADMIN = "MATCH (p:Patient {id: $patient_id}) " + _CODED_ENTITIES_BODY

# ---------------------------------------------------------------------------
# Episode milestones
# ---------------------------------------------------------------------------

GET_MILESTONES = (
    "MATCH (p:Patient {id: $patient_id}) "
    "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare {episode_id: $episode_id}) "
    "OPTIONAL MATCH (enc:Encounter)-[:IS_PART_OF {milestone_type: 'referral'}]->(ep) "
    "  WITH ep, collect(DISTINCT enc.date) AS referral_dates "
    "OPTIONAL MATCH (enc2:Encounter)"
    "-[:IS_PART_OF {milestone_type: 'specialist_visit'}]->(ep) "
    "  WITH ep, referral_dates, collect(DISTINCT enc2.date) AS specialist_dates "
    "OPTIONAL MATCH (enc3:Encounter)"
    "-[:IS_PART_OF {milestone_type: 'diagnosis'}]->(ep) "
    "  WITH ep, referral_dates, specialist_dates,"
    " collect(DISTINCT enc3.date) AS diagnosis_dates "
    "OPTIONAL MATCH (enc4:Encounter)-[:IS_PART_OF {milestone_type: 'outcome'}]->(ep) "
    "RETURN ep.episode_id AS episode_id, "
    "       ep.referral_date AS referral_date, "
    "       ep.end_date AS end_date, "
    "       referral_dates, specialist_dates, diagnosis_dates, "
    "       collect(DISTINCT enc4.date) AS outcome_dates"
)
