"""Cypher query strings for the domain-agnostic patient EPR endpoints.

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
    "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp:Organization) "
    "OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "  WHERE NOT ep.status IN ['merged', 'closed_phantom', 'closed_related'] "
    "OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter) "
    "OPTIONAL MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(alert:SafetyNetAlert) "
    "  WHERE alert.resolved_at IS NULL "
    "WITH p, gp, "
    "count(DISTINCT ep) AS episode_count, "
    "count(DISTINCT enc) AS encounter_count, "
    "max(toString(enc.date)) AS last_activity, "
    "count(DISTINCT alert) AS active_alert_count, "
    "collect(DISTINCT coalesce(ep.condition_type, ep.cancer_type)) AS condition_types "
    "RETURN "
    "  p.id AS patient_id, "
    "  p.gender AS gender, "
    "  p.birthDate AS birth_date, "
    "  gp.name AS practice_name, "
    "  episode_count, "
    "  encounter_count, "
    "  last_activity, "
    "  active_alert_count, "
    "  [ct IN condition_types WHERE ct IS NOT NULL AND ct <> ''] AS condition_types"
)

# ---------------------------------------------------------------------------
# Patient list
# ---------------------------------------------------------------------------

LIST_PATIENTS_SCOPED = (
    "MATCH (p:Patient) "
    "WHERE " + _ORG_GUARD + " AND "
    + _FILTER_CONDITIONS
    + "WITH p ORDER BY p.id ASC SKIP $skip LIMIT $limit "
    + _AGG_TAIL
)

LIST_PATIENTS_ADMIN = (
    "MATCH (p:Patient) "
    "WHERE " + _FILTER_CONDITIONS
    + "WITH p ORDER BY p.id ASC SKIP $skip LIMIT $limit "
    + _AGG_TAIL
)

# ---------------------------------------------------------------------------
# Count queries (same filters, no pagination)
# ---------------------------------------------------------------------------

COUNT_PATIENTS_SCOPED = (
    "MATCH (p:Patient) "
    "WHERE " + _ORG_GUARD + " AND "
    + _FILTER_CONDITIONS
    + "RETURN count(p) AS total"
)

COUNT_PATIENTS_ADMIN = (
    "MATCH (p:Patient) "
    "WHERE " + _FILTER_CONDITIONS
    + "RETURN count(p) AS total"
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

GET_PATIENT_DETAIL_SCOPED = (
    "MATCH (p:Patient {id: $patient_id}) "
    "WHERE " + _ORG_GUARD + " "
    "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp:Organization) "
    "OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "OPTIONAL MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(alert:SafetyNetAlert) "
    "  WHERE alert.resolved_at IS NULL "
    "RETURN "
    "  p.id AS patient_id, "
    "  p.gender AS gender, "
    "  p.birthDate AS birth_date, "
    "  gp.name AS practice_name, "
    "  count(DISTINCT alert) AS active_alert_count, "
    "  collect(DISTINCT { "
    "    episode_id: ep.episode_id, "
    "    condition_type: coalesce(ep.condition_type, ep.cancer_type), "
    "    status: ep.status, "
    "    referral_date: toString(ep.referral_date), "
    "    end_date: toString(ep.end_date), "
    "    inferred_outcome: ep.inferred_outcome "
    "  }) AS episodes"
)

GET_PATIENT_DETAIL_ADMIN = (
    "MATCH (p:Patient {id: $patient_id}) "
    "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp:Organization) "
    "OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "OPTIONAL MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(alert:SafetyNetAlert) "
    "  WHERE alert.resolved_at IS NULL "
    "RETURN "
    "  p.id AS patient_id, "
    "  p.gender AS gender, "
    "  p.birthDate AS birth_date, "
    "  gp.name AS practice_name, "
    "  count(DISTINCT alert) AS active_alert_count, "
    "  collect(DISTINCT { "
    "    episode_id: ep.episode_id, "
    "    condition_type: coalesce(ep.condition_type, ep.cancer_type), "
    "    status: ep.status, "
    "    referral_date: toString(ep.referral_date), "
    "    end_date: toString(ep.end_date), "
    "    inferred_outcome: ep.inferred_outcome "
    "  }) AS episodes"
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
    "  RETURN 'episode' AS item_type, ep.episode_id AS item_id, "
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
    "} "
    "WITH item_type, item_id, item_date, label, extra "
    "WHERE item_id IS NOT NULL AND item_date IS NOT NULL "
    "RETURN item_type, item_id, item_date, label, extra "
    "ORDER BY item_date DESC "
    "LIMIT 100"
)

GET_TIMELINE_SCOPED = (
    "MATCH (p:Patient {id: $patient_id}) "
    "WHERE " + _ORG_GUARD + " "
    + _TIMELINE_BODY
)

GET_TIMELINE_ADMIN = (
    "MATCH (p:Patient {id: $patient_id}) "
    + _TIMELINE_BODY
)
