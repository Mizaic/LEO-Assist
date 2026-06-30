"""Extended metric registry: 18 new audit metrics added in Phase 2.

Tiers:
  A -- Referral quality (Assessment-based, 4 metrics)
  B -- Demographics intelligence (4 metrics)
  C -- Quality outcomes (4 metrics)
  D -- Safety (3 metrics)
  E -- Operational excellence (3 metrics)

Internal module -- import via audit_metric_queries.py.
"""

from __future__ import annotations

from typing import Any

from libs.cypher._audit_metrics_core import EPISODE_ACTIVE, ORG_GUARD

# Shared Assessment match fragment reused by Tier A metrics.
_SBAR_MATCH = (
    "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)"
    "-[:HAS_ASSESSMENT]->(a:Assessment {type:'SBAR'}) "
)

_DATE_GUARD_ENC = (
    "($date_from IS NULL OR toString(e.date) >= $date_from) "
    "AND ($date_to IS NULL OR toString(e.date) <= $date_to)"
)

_DATE_GUARD_EP = (
    "($date_from IS NULL OR ep.referral_date >= $date_from) "
    "AND ($date_to IS NULL OR ep.referral_date <= $date_to)"
)

_DATE_GUARD_ALERT = (
    "($date_from IS NULL OR toString(a.created_at) >= $date_from) "
    "AND ($date_to IS NULL OR toString(a.created_at) <= $date_to)"
)

_SAFE_DIV = "CASE WHEN count(a) = 0 THEN 1 ELSE count(a) END"
_SAFE_DIV_EP = "CASE WHEN count(ep) = 0 THEN 1 ELSE count(ep) END"
_SAFE_DIV_ALT = "CASE WHEN count(a) = 0 THEN 1.0 ELSE toFloat(count(a)) END"

# ---------------------------------------------------------------------------
# Tier A -- Referral quality (Assessment-based)
# ---------------------------------------------------------------------------

_TIER_A: list[dict[str, Any]] = [
    {
        "metric_id": "referral_stt_rate",
        "title": "Straight-to-test rate",
        "description": (
            "Percentage of assessed referrals where LEO recommended "
            "straight-to-test (STT) as the next step."
        ),
        "output_type": "kpi_strip",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "total_assessed", "type": "integer"},
            {"name": "stt_count", "type": "integer"},
            {"name": "stt_pct", "type": "float"},
        ],
        "cypher": (
            _SBAR_MATCH
            + "WHERE " + ORG_GUARD + " "
            + "AND a.stt IS NOT NULL "
            + "AND " + _DATE_GUARD_ENC + " "
            + "RETURN count(a) AS total_assessed, "
            + "count(CASE WHEN a.stt = true THEN 1 END) AS stt_count, "
            + "round(100.0 * count(CASE WHEN a.stt = true THEN 1 END) "
            + "/ " + _SAFE_DIV + ", 1) AS stt_pct"
        ),
    },
    {
        "metric_id": "referral_guideline_compliance_rate",
        "title": "Guideline compliance rate",
        "description": (
            "Percentage of referrals matching at least one NICE/NG12 assessment rule, "
            "indicating the referral was clinically justified."
        ),
        "output_type": "kpi_strip",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "total_assessed", "type": "integer"},
            {"name": "compliant_count", "type": "integer"},
            {"name": "compliance_pct", "type": "float"},
        ],
        "cypher": (
            _SBAR_MATCH
            + "WHERE " + ORG_GUARD + " "
            + "AND " + _DATE_GUARD_ENC + " "
            + "RETURN count(a) AS total_assessed, "
            + "count(CASE WHEN size(coalesce(a.assessment_rules, [])) > 0 "
            + "  THEN 1 END) AS compliant_count, "
            + "round(100.0 * count(CASE WHEN size(coalesce(a.assessment_rules, [])) > 0 "
            + "  THEN 1 END) / " + _SAFE_DIV + ", 1) AS compliance_pct"
        ),
    },
    {
        "metric_id": "referral_alternative_pathway_rate",
        "title": "Alternative pathway rate",
        "description": (
            "Percentage of referrals where LEO suggested a different care pathway "
            "than the one chosen by the referrer."
        ),
        "output_type": "kpi_strip",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "total_assessed", "type": "integer"},
            {"name": "alt_pathway_count", "type": "integer"},
            {"name": "alt_pathway_pct", "type": "float"},
        ],
        "cypher": (
            _SBAR_MATCH
            + "WHERE " + ORG_GUARD + " "
            + "AND a.alternative_pathway IS NOT NULL "
            + "AND " + _DATE_GUARD_ENC + " "
            + "RETURN count(a) AS total_assessed, "
            + "count(CASE WHEN a.alternative_pathway = true "
            + "  OR toLower(toString(a.alternative_pathway)) = 'yes' "
            + "  THEN 1 END) AS alt_pathway_count, "
            + "round(100.0 * count(CASE WHEN a.alternative_pathway = true "
            + "  OR toLower(toString(a.alternative_pathway)) = 'yes' "
            + "  THEN 1 END) / " + _SAFE_DIV + ", 1) AS alt_pathway_pct"
        ),
    },
    {
        "metric_id": "referral_completeness_rate",
        "title": "Referral completeness rate",
        "description": (
            "Percentage of referrals with no required information fields missing. "
            "Based on the SBAR completeness check run at assessment time."
        ),
        "output_type": "kpi_strip",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "total_assessed", "type": "integer"},
            {"name": "complete_count", "type": "integer"},
            {"name": "completeness_pct", "type": "float"},
        ],
        "cypher": (
            _SBAR_MATCH
            + "WHERE " + ORG_GUARD + " "
            + "AND a.completeness_failed_count IS NOT NULL "
            + "AND " + _DATE_GUARD_ENC + " "
            + "RETURN count(a) AS total_assessed, "
            + "count(CASE WHEN a.completeness_failed_count = 0 THEN 1 END) AS complete_count, "
            + "round(100.0 * count(CASE WHEN a.completeness_failed_count = 0 THEN 1 END) "
            + "/ " + _SAFE_DIV + ", 1) AS completeness_pct"
        ),
    },
    {
        "metric_id": "referral_named_completeness",
        "title": "Missing fields by type",
        "description": (
            "Count and percentage of assessed referrals missing each required "
            "completeness field group (e.g. Blood results, Presenting symptom). "
            "Groups are named in the pathway completeness schema. "
            "Only referrals with a configured completeness schema are counted. "
            "Uses apoc.convert.fromJsonMap -- requires APOC (available on Neo4j Aura)."
        ),
        "output_type": "bar_chart",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "field_group", "type": "string"},
            {"name": "missing_n", "type": "integer"},
            {"name": "total_assessed", "type": "integer"},
            {"name": "missing_pct", "type": "float"},
        ],
        "cypher": (
            _SBAR_MATCH
            + "WHERE " + ORG_GUARD + " "
            + "AND a.completeness_result_json IS NOT NULL "
            + "AND " + _DATE_GUARD_ENC + " "
            + "WITH a.completeness_result_json AS json_str "
            + "WITH apoc.convert.fromJsonMap(json_str) AS parsed "
            + "WHERE parsed.configured = true "
            + "WITH count(parsed) AS total, collect(parsed) AS all_parsed "
            + "UNWIND all_parsed AS parsed "
            + "UNWIND parsed.missing_groups AS grp "
            + "WHERE grp.required = true "
            + "WITH total, grp.name AS field_group, count(grp) AS missing_n "
            + "RETURN field_group, missing_n, total AS total_assessed, "
            + "round(100.0 * missing_n / "
            + "CASE WHEN total = 0 THEN 1 ELSE total END, 1) AS missing_pct "
            + "ORDER BY missing_n DESC"
        ),
    },
]

# ---------------------------------------------------------------------------
# Tier B -- Demographics intelligence
# ---------------------------------------------------------------------------

_TIER_B: list[dict[str, Any]] = [
    {
        "metric_id": "patient_gender_distribution",
        "title": "Patient gender distribution",
        "description": (
            "How the patient population is split by gender across "
            "the selected date range."
        ),
        "output_type": "bar_chart",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "gender", "type": "string"},
            {"name": "n", "type": "integer"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " AND " + EPISODE_ACTIVE + " "
            "AND " + _DATE_GUARD_EP + " "
            "WITH DISTINCT p "
            "RETURN coalesce(toLower(trim(p.gender)), 'unknown') AS gender, "
            "count(p) AS n "
            "ORDER BY n DESC"
        ),
    },
    {
        "metric_id": "patient_age_band_distribution",
        "title": "Patient age band distribution",
        "description": (
            "Number of distinct patients in each 10-year age band "
            "for the selected date range."
        ),
        "output_type": "bar_chart",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "age_band", "type": "string"},
            {"name": "n", "type": "integer"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " AND " + EPISODE_ACTIVE + " "
            "AND " + _DATE_GUARD_EP + " "
            "WITH DISTINCT p "
            "RETURN CASE "
            "  WHEN p.age < 30 THEN 'under 30' "
            "  WHEN p.age < 40 THEN '30-39' "
            "  WHEN p.age < 50 THEN '40-49' "
            "  WHEN p.age < 60 THEN '50-59' "
            "  WHEN p.age < 70 THEN '60-69' "
            "  WHEN p.age < 80 THEN '70-79' "
            "  ELSE '80+' "
            "END AS age_band, count(p) AS n "
            "ORDER BY age_band"
        ),
    },
    {
        "metric_id": "imd_distribution",
        "title": "Deprivation decile distribution",
        "description": (
            "Number of patients by Index of Multiple Deprivation (IMD) decile "
            "(1 = most deprived, 10 = least deprived). "
            "Requires address enrichment via /imd/enrich."
        ),
        "output_type": "bar_chart",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "imd_decile", "type": "integer"},
            {"name": "n", "type": "integer"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " AND " + EPISODE_ACTIVE + " "
            "AND " + _DATE_GUARD_EP + " "
            "WITH DISTINCT p "
            "MATCH (p)-[:HAS_ADDRESS]->(addr:Address) "
            "WHERE addr.imd_decile IS NOT NULL "
            "RETURN addr.imd_decile AS imd_decile, count(DISTINCT p) AS n "
            "ORDER BY imd_decile ASC"
        ),
    },
    {
        "metric_id": "conditions_by_deprivation",
        "title": "Conditions by deprivation quintile",
        "description": (
            "Which conditions are most common in each IMD quintile "
            "(1 = most deprived). Shows how condition prevalence varies with "
            "socioeconomic status."
        ),
        "output_type": "table",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "imd_quintile", "type": "integer"},
            {"name": "condition", "type": "string"},
            {"name": "n", "type": "integer"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " AND " + EPISODE_ACTIVE + " "
            "AND ep.condition_type IS NOT NULL "
            "AND " + _DATE_GUARD_EP + " "
            "MATCH (p)-[:HAS_ADDRESS]->(addr:Address) "
            "WHERE addr.imd_decile IS NOT NULL "
            "WITH ceiling(addr.imd_decile / 2.0) AS imd_quintile, "
            "ep.condition_type AS condition, count(ep) AS n "
            "RETURN toInteger(imd_quintile) AS imd_quintile, condition, n "
            "ORDER BY imd_quintile, n DESC"
        ),
    },
]

# ---------------------------------------------------------------------------
# Tier C -- Quality outcomes
# ---------------------------------------------------------------------------

_TIER_C: list[dict[str, Any]] = [
    {
        "metric_id": "early_stage_detection_rate",
        "title": "Early-stage detection rate",
        "description": (
            "Percentage of confirmed cancer diagnoses that were caught at "
            "stage 1 or 2. Higher rates indicate earlier, more treatable cancers."
        ),
        "output_type": "kpi_strip",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "confirmed_cancer", "type": "integer"},
            {"name": "early_n", "type": "integer"},
            {"name": "early_stage_pct", "type": "float"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " "
            "AND ep.inferred_outcome = 'cancer' "
            "AND ep.stage_at_diagnosis IS NOT NULL "
            "AND " + _DATE_GUARD_EP + " "
            "RETURN count(ep) AS confirmed_cancer, "
            "count(CASE WHEN ep.stage_at_diagnosis IN "
            "  ['1','2','I','II','1a','1b','2a','2b'] "
            "  OR toLower(ep.stage_at_diagnosis) STARTS WITH 'early' "
            "  THEN 1 END) AS early_n, "
            "round(100.0 * count(CASE WHEN ep.stage_at_diagnosis IN "
            "  ['1','2','I','II','1a','1b','2a','2b'] "
            "  OR toLower(ep.stage_at_diagnosis) STARTS WITH 'early' "
            "  THEN 1 END) / " + _SAFE_DIV_EP + ", 1) AS early_stage_pct"
        ),
    },
    {
        "metric_id": "cancer_conversion_rate",
        "title": "Cancer conversion rate",
        "description": (
            "Percentage of urgent or 2-week-wait referrals that resulted "
            "in a confirmed cancer diagnosis."
        ),
        "output_type": "kpi_strip",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "urgent_referrals", "type": "integer"},
            {"name": "confirmed_cancer", "type": "integer"},
            {"name": "conversion_pct", "type": "float"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " AND " + EPISODE_ACTIVE + " "
            "AND ep.referral_route IN ['2ww','2_week_wait','urgent','suspected_cancer'] "
            "AND " + _DATE_GUARD_EP + " "
            "RETURN count(ep) AS urgent_referrals, "
            "count(CASE WHEN ep.inferred_outcome = 'cancer' THEN 1 END) AS confirmed_cancer, "
            "round(100.0 * count(CASE WHEN ep.inferred_outcome = 'cancer' THEN 1 END) "
            "/ " + _SAFE_DIV_EP + ", 1) AS conversion_pct"
        ),
    },
    {
        "metric_id": "emergency_presentation_rate",
        "title": "Emergency presentation rate",
        "description": (
            "Percentage of confirmed cancer cases that first presented "
            "via A&E or an emergency route -- a proxy for late diagnosis."
        ),
        "output_type": "kpi_strip",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "confirmed_cancer", "type": "integer"},
            {"name": "emergency_n", "type": "integer"},
            {"name": "emergency_pct", "type": "float"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " "
            "AND ep.inferred_outcome = 'cancer' "
            "AND ep.place_of_presentation IS NOT NULL "
            "AND " + _DATE_GUARD_EP + " "
            "RETURN count(ep) AS confirmed_cancer, "
            "count(CASE WHEN toLower(ep.place_of_presentation) CONTAINS 'a&e' "
            "  OR toLower(ep.place_of_presentation) CONTAINS 'emergency' "
            "  THEN 1 END) AS emergency_n, "
            "round(100.0 * count(CASE WHEN toLower(ep.place_of_presentation) CONTAINS 'a&e' "
            "  OR toLower(ep.place_of_presentation) CONTAINS 'emergency' "
            "  THEN 1 END) / " + _SAFE_DIV_EP + ", 1) AS emergency_pct"
        ),
    },
    {
        "metric_id": "outcome_distribution",
        "title": "Outcome distribution",
        "description": (
            "How episodes are spread across outcomes "
            "(cancer, no cancer, pending, other)."
        ),
        "output_type": "bar_chart",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "outcome", "type": "string"},
            {"name": "n", "type": "integer"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " AND " + EPISODE_ACTIVE + " "
            "AND " + _DATE_GUARD_EP + " "
            "RETURN coalesce(ep.inferred_outcome, 'pending') AS outcome, "
            "count(ep) AS n "
            "ORDER BY n DESC"
        ),
    },
]

# ---------------------------------------------------------------------------
# Tier D -- Safety
# ---------------------------------------------------------------------------

_TIER_D: list[dict[str, Any]] = [
    {
        "metric_id": "unactioned_alerts_by_age",
        "title": "Unactioned alerts by age",
        "description": (
            "Number of open safety alerts that have not been acted on, "
            "grouped by how long they have been waiting."
        ),
        "output_type": "bar_chart",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "age_band", "type": "string"},
            {"name": "n", "type": "integer"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_SAFETY_NET_ALERT]->(a:SafetyNetAlert) "
            "WHERE " + ORG_GUARD + " "
            "AND coalesce(a.actioned, false) = false "
            "AND a.status = 'open' "
            "AND ($date_from IS NULL OR toString(a.created_at) >= $date_from) "
            "RETURN CASE "
            "  WHEN duration.inDays(a.created_at, datetime()).days < 7 "
            "    THEN '0-7 days' "
            "  WHEN duration.inDays(a.created_at, datetime()).days < 14 "
            "    THEN '7-14 days' "
            "  WHEN duration.inDays(a.created_at, datetime()).days < 30 "
            "    THEN '14-30 days' "
            "  ELSE 'over 30 days' "
            "END AS age_band, count(a) AS n "
            "ORDER BY age_band"
        ),
    },
    {
        "metric_id": "alert_escalation_rate",
        "title": "Alert escalation rate",
        "description": (
            "Percentage of safety alerts that were escalated to a higher "
            "clinical level (escalation_level > 0)."
        ),
        "output_type": "kpi_strip",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "total_alerts", "type": "integer"},
            {"name": "escalated_count", "type": "integer"},
            {"name": "escalation_pct", "type": "float"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_SAFETY_NET_ALERT]->(a:SafetyNetAlert) "
            "WHERE " + ORG_GUARD + " "
            "AND " + _DATE_GUARD_ALERT + " "
            "RETURN count(a) AS total_alerts, "
            "count(CASE WHEN coalesce(a.escalation_level, 0) > 0 THEN 1 END) "
            "AS escalated_count, "
            "round(100.0 * count(CASE WHEN coalesce(a.escalation_level, 0) > 0 THEN 1 END) "
            "/ CASE WHEN count(a) = 0 THEN 1 ELSE count(a) END, 1) AS escalation_pct"
        ),
    },
    {
        "metric_id": "repeat_referral_patients",
        "title": "Repeat referral patients",
        "description": (
            "Patients with two or more episodes for the same condition. "
            "May indicate unresolved or recurring clinical concerns."
        ),
        "output_type": "table",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "condition", "type": "string"},
            {"name": "repeat_patients", "type": "integer"},
            {"name": "max_episodes", "type": "integer"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " AND " + EPISODE_ACTIVE + " "
            "AND ep.condition_type IS NOT NULL "
            "AND " + _DATE_GUARD_EP + " "
            "WITH p, ep.condition_type AS condition, count(ep) AS episode_count "
            "WHERE episode_count >= 2 "
            "RETURN condition, count(DISTINCT p) AS repeat_patients, "
            "max(episode_count) AS max_episodes "
            "ORDER BY repeat_patients DESC"
        ),
    },
]

# ---------------------------------------------------------------------------
# Tier E -- Operational excellence
# ---------------------------------------------------------------------------

_TIER_E: list[dict[str, Any]] = [
    {
        "metric_id": "episode_open_age_distribution",
        "title": "Open episode age profile",
        "description": (
            "How long current open episodes have been waiting "
            "since the referral date. Helps identify waiting list pressure."
        ),
        "output_type": "bar_chart",
        "param_schema": {},
        "output_schema": [
            {"name": "age_band", "type": "string"},
            {"name": "n", "type": "integer"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " "
            "AND ep.status IN ['open','awaiting_review','in_progress'] "
            "AND ep.referral_date IS NOT NULL "
            "RETURN CASE "
            "  WHEN duration.between(date(ep.referral_date), date()).days < 14 "
            "    THEN 'under 14d' "
            "  WHEN duration.between(date(ep.referral_date), date()).days < 28 "
            "    THEN '14-28d' "
            "  WHEN duration.between(date(ep.referral_date), date()).days < 62 "
            "    THEN '28-62d' "
            "  ELSE 'over 62d' "
            "END AS age_band, count(ep) AS n "
            "ORDER BY age_band"
        ),
    },
    {
        "metric_id": "referral_completion_rate",
        "title": "Referral completion rate",
        "description": (
            "Percentage of episodes that have reached a final outcome "
            "(cancer or no cancer) in the selected period."
        ),
        "output_type": "kpi_strip",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "total", "type": "integer"},
            {"name": "completed", "type": "integer"},
            {"name": "completion_pct", "type": "float"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " AND " + EPISODE_ACTIVE + " "
            "AND " + _DATE_GUARD_EP + " "
            "RETURN count(ep) AS total, "
            "count(CASE WHEN ep.inferred_outcome IN ['cancer','no_cancer'] "
            "  THEN 1 END) AS completed, "
            "round(100.0 * count(CASE WHEN ep.inferred_outcome IN "
            "  ['cancer','no_cancer'] THEN 1 END) "
            "/ " + _SAFE_DIV_EP + ", 1) AS completion_pct"
        ),
    },
    {
        "metric_id": "coding_backlog_by_site",
        "title": "Coding backlog by site",
        "description": (
            "Number of encounters with no coded findings, grouped by GP practice. "
            "Highlights where coding workload is concentrated."
        ),
        "output_type": "table",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "organisation", "type": "string"},
            {"name": "uncoded_encounters", "type": "integer"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(org) "
            "WHERE org.id IN $scope_org_ids "
            "MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE NOT EXISTS { MATCH (e)-[:DOCUMENTS]->() } "
            "AND ($date_from IS NULL OR toString(e.date) >= $date_from) "
            "AND ($date_to IS NULL OR toString(e.date) <= $date_to) "
            "RETURN org.name AS organisation, count(e) AS uncoded_encounters "
            "ORDER BY uncoded_encounters DESC"
        ),
    },
]

# ---------------------------------------------------------------------------
# Combined list exported by this module
# ---------------------------------------------------------------------------

EXTENDED_METRICS: list[dict[str, Any]] = _TIER_A + _TIER_B + _TIER_C + _TIER_D + _TIER_E
