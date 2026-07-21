"""Referral audit metrics (Tier F) -- query ReferralRequest nodes directly.

These metrics back the Clinical Referral Audit template. They differ from
the Tier A-E metrics which follow the EpisodeOfCare / Encounter / Assessment
path. Here the primary entity is ReferralRequest.

Internal module -- import via audit_metric_queries.py.

# LONG FUNCTION: data declaration file (metric registry entries)
"""

from __future__ import annotations

from typing import Any

from libs.cypher._audit_metrics_core import ORG_GUARD

# ---------------------------------------------------------------------------
# Shared fragments
# ---------------------------------------------------------------------------

# Org guard for ReferralRequest metrics.
# Checks two paths:
#   1. GP practice scope:  r -> Patient -[:HAS_GENERAL_PRACTITIONER]-> org
#   2. Trust/site scope:   r -> Patient -[:REGISTERED_IN]-> org
# Secondary care trusts (e.g. M0L1I) use REGISTERED_IN; GP practices use HAS_GENERAL_PRACTITIONER.
_RR_ORG_GUARD = (
    "(size($scope_org_ids) = 0 "
    "OR EXISTS { MATCH (r)-[:FOR_PATIENT]->(_rp:Patient)"
    "-[:HAS_GENERAL_PRACTITIONER]->(_gp_rr) "
    "WHERE _gp_rr.id IN $scope_org_ids } "
    "OR EXISTS { MATCH (r)-[:FOR_PATIENT]->(_rp2:Patient)"
    "-[:REGISTERED_IN]->(_org_rr) "
    "WHERE _org_rr.id IN $scope_org_ids })"
)

_DATE_GUARD_RR = (
    "($date_from IS NULL OR r.eReferralPathwayStart >= $date_from) "
    "AND ($date_to IS NULL OR r.eReferralPathwayStart <= $date_to)"
)

_RR_BASE = "MATCH (r:ReferralRequest) WHERE " + _RR_ORG_GUARD + " AND " + _DATE_GUARD_RR + " "

_SAFE_RR = "CASE WHEN count(r) = 0 THEN 1 ELSE count(r) END"

_DATE_PARAMS: dict[str, Any] = {
    "date_from": {"type": "string", "format": "date", "required": False},
    "date_to": {"type": "string", "format": "date", "required": False},
}

# ---------------------------------------------------------------------------
# Tier F -- ReferralRequest audit metrics
# ---------------------------------------------------------------------------

REFERRAL_METRICS: list[dict[str, Any]] = [
    {
        "metric_id": "rr_status_distribution",
        "title": "Referral status breakdown",
        "description": "Count of ReferralRequest nodes by current state (ers_state / leo_state).",
        "output_type": "bar_chart",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "status", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            _RR_BASE
            + "RETURN coalesce(r.ers_state, r.leo_state, 'unknown') AS status, "
            "count(r) AS count ORDER BY count DESC"
        ),
    },
    {
        "metric_id": "rr_priority_distribution",
        "title": "Referral priority distribution",
        "description": "Count of referrals by priority (TWO_WEEK_WAIT, URGENT, ROUTINE).",
        "output_type": "bar_chart",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "priority", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            _RR_BASE
            + "RETURN coalesce(r.priority, 'unknown') AS priority, "
            "count(r) AS count ORDER BY count DESC"
        ),
    },
    {
        "metric_id": "rr_monthly_trend",
        "title": "Monthly referral volume",
        "description": "Number of referrals received per calendar month (eReferralPathwayStart).",
        "output_type": "line_chart",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "month", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            _RR_BASE
            + "WITH substring(r.eReferralPathwayStart, 0, 7) AS month, count(r) AS count "
            "WHERE month IS NOT NULL "
            "RETURN month, count ORDER BY month"
        ),
    },
    {
        "metric_id": "rr_yoy_trend",
        "title": "Referral volume year-on-year",
        "description": "Monthly referral count split by year for trend comparison.",
        "output_type": "line_chart",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "month", "type": "string"},
            {"name": "year", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            _RR_BASE
            + "WHERE r.eReferralPathwayStart IS NOT NULL "
            "WITH substring(r.eReferralPathwayStart, 5, 2) AS month, "
            "substring(r.eReferralPathwayStart, 0, 4) AS year, r "
            "RETURN month, year, count(r) AS count ORDER BY year, month"
        ),
    },
    {
        "metric_id": "rr_by_service",
        "title": "Referrals by service",
        "description": "Number of referrals received by each clinical service.",
        "output_type": "bar_chart",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "service", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            "MATCH (r:ReferralRequest)-[:FOR_SERVICE]->(s:Service) "
            "WHERE " + _RR_ORG_GUARD + " AND " + _DATE_GUARD_RR + " "
            "RETURN s.name AS service, count(r) AS count ORDER BY count DESC"
        ),
    },
    {
        "metric_id": "rr_by_commissioning_org",
        "title": "Referrals by commissioning organisation",
        "description": "Referral count by commissioning organisation (COMMISSIONED_BY relationship).",
        "output_type": "bar_chart",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "organisation", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            "MATCH (r:ReferralRequest)-[:COMMISSIONED_BY]->(o:Organization) "
            "WHERE " + _RR_ORG_GUARD + " AND " + _DATE_GUARD_RR + " "
            "RETURN o.name AS organisation, count(r) AS count "
            "ORDER BY count DESC LIMIT 10"
        ),
    },
    {
        "metric_id": "rr_avg_days_to_appointment",
        "title": "Average days from referral to first appointment",
        "description": "Mean number of days between eReferralPathwayStart and first booked/fulfilled appointment.",
        "output_type": "kpi_strip",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "metric", "type": "string"},
            {"name": "value", "type": "float"},
        ],
        "cypher": (
            "MATCH (r:ReferralRequest)-[:HAS_APPOINTMENT]->(a:Appointment) "
            "WHERE (a.status = 'booked' OR a.status = 'fulfilled') "
            "AND r.eReferralPathwayStart IS NOT NULL "
            "AND " + _RR_ORG_GUARD + " AND " + _DATE_GUARD_RR + " "
            "WITH r, min(a.created) AS first_appt "
            "RETURN 'Avg days to first appointment' AS metric, "
            "round(avg(duration.between("
            "datetime(r.eReferralPathwayStart), datetime(first_appt)).days), 1) AS value"
        ),
    },
    {
        "metric_id": "rr_workflow_state",
        "title": "Referral workflow state",
        "description": "Distribution of referrals by combined leo_state / ers_state workflow step.",
        "output_type": "bar_chart",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "state", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            _RR_BASE
            + "RETURN coalesce(r.leo_state, r.ers_state, 'unknown') AS state, "
            "count(r) AS count ORDER BY count DESC"
        ),
    },
    {
        "metric_id": "rr_wait_time_distribution",
        "title": "Wait time distribution",
        "description": "Referrals by wait-time band from referral date to first booked appointment.",
        "output_type": "bar_chart",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "band", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            "MATCH (r:ReferralRequest)-[:HAS_APPOINTMENT]->(a:Appointment) "
            "WHERE (a.status = 'booked' OR a.status = 'fulfilled') "
            "AND r.eReferralPathwayStart IS NOT NULL "
            "AND " + _RR_ORG_GUARD + " AND " + _DATE_GUARD_RR + " "
            "WITH r, min(a.created) AS first_appt "
            "WITH duration.between(datetime(r.eReferralPathwayStart), "
            "datetime(first_appt)).days AS wait_days "
            "RETURN CASE "
            "  WHEN wait_days < 14 THEN '0-2 weeks' "
            "  WHEN wait_days < 28 THEN '2-4 weeks' "
            "  WHEN wait_days < 56 THEN '4-8 weeks' "
            "  WHEN wait_days < 84 THEN '8-12 weeks' "
            "  ELSE '12+ weeks' "
            "END AS band, count(*) AS count "
            "ORDER BY CASE band "
            "  WHEN '0-2 weeks' THEN 1 WHEN '2-4 weeks' THEN 2 "
            "  WHEN '4-8 weeks' THEN 3 WHEN '8-12 weeks' THEN 4 ELSE 5 END"
        ),
    },
    {
        "metric_id": "rr_wait_time_breaches_by_service",
        "title": "62-day wait breaches by service",
        "description": "Percentage of referrals per service exceeding 62-day wait target.",
        "output_type": "bar_chart",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "service", "type": "string"},
            {"name": "total", "type": "integer"},
            {"name": "breaches", "type": "integer"},
            {"name": "breach_pct", "type": "float"},
        ],
        "cypher": (
            "MATCH (r:ReferralRequest)-[:FOR_SERVICE]->(s:Service), "
            "(r)-[:HAS_APPOINTMENT]->(a:Appointment) "
            "WHERE (a.status = 'booked' OR a.status = 'fulfilled') "
            "AND r.eReferralPathwayStart IS NOT NULL "
            "AND " + _RR_ORG_GUARD + " AND " + _DATE_GUARD_RR + " "
            "WITH s.name AS service, r, min(a.created) AS first_appt "
            "WITH service, r, duration.between("
            "datetime(r.eReferralPathwayStart), datetime(first_appt)).days AS wait "
            "WITH service, count(r) AS total, "
            "sum(CASE WHEN wait > 62 THEN 1 ELSE 0 END) AS breaches "
            "RETURN service, total, breaches, "
            "round(100.0 * breaches / CASE WHEN total = 0 THEN 1 ELSE total END, 1) "
            "AS breach_pct ORDER BY breach_pct DESC LIMIT 10"
        ),
    },
    {
        "metric_id": "rr_peer_review_analysis",
        "title": "Peer review AI assessment",
        "description": "Distribution of AI assessment verdicts from peer review nodes.",
        "output_type": "bar_chart",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "ai_assessment", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            "MATCH (r:ReferralRequest)-[:HAS_PEER_REVIEW]->(p:PeerReview) "
            "WHERE " + _RR_ORG_GUARD + " AND " + _DATE_GUARD_RR + " "
            "RETURN coalesce(p.peer_review_ai_assessment, 'unknown') AS ai_assessment, "
            "count(r) AS count ORDER BY count DESC"
        ),
    },
    {
        "metric_id": "rr_top_conditions",
        "title": "Top conditions on referred patients",
        "description": "Most common coded conditions on patients who have a referral.",
        "output_type": "bar_chart",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "condition", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            "MATCH (r:ReferralRequest)-[:FOR_PATIENT]->(p:Patient)-[:HAS_CONDITION]->(c:Condition) "
            "WHERE " + _RR_ORG_GUARD + " AND " + _DATE_GUARD_RR + " "
            "RETURN c.name AS condition, count(DISTINCT r) AS count "
            "ORDER BY count DESC LIMIT 10"
        ),
    },
    {
        "metric_id": "rr_top_medications",
        "title": "Top medications on referred patients",
        "description": "Most common medications on patients who have a referral.",
        "output_type": "bar_chart",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "medication", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            "MATCH (r:ReferralRequest)-[:FOR_PATIENT]->(p:Patient)-[:HAS_MEDICATION]->(m:Medication) "
            "WHERE " + _RR_ORG_GUARD + " AND " + _DATE_GUARD_RR + " "
            "RETURN m.name AS medication, count(DISTINCT r) AS count "
            "ORDER BY count DESC LIMIT 10"
        ),
    },
    {
        "metric_id": "rr_abnormal_observations",
        "title": "Abnormal observations on referred patients",
        "description": "Observations flagged abnormal on patients who have a referral.",
        "output_type": "bar_chart",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "observation", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            "MATCH (r:ReferralRequest)-[:FOR_PATIENT]->(p:Patient)"
            "-[rel:HAS_OBSERVATION]->(o:Observation) "
            "WHERE rel.abnormal = true "
            "AND " + _RR_ORG_GUARD + " AND " + _DATE_GUARD_RR + " "
            "RETURN o.name AS observation, count(DISTINCT r) AS count "
            "ORDER BY count DESC LIMIT 10"
        ),
    },
    {
        "metric_id": "rr_outcome_flow",
        "title": "Referral outcome flow (priority to state)",
        "description": "Number of referrals for each priority-to-final-state combination.",
        "output_type": "table",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "priority", "type": "string"},
            {"name": "state", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            _RR_BASE
            + "WITH coalesce(r.priority, 'unknown') AS priority, "
            "coalesce(r.ers_state, r.leo_state, 'unknown') AS state, r "
            "RETURN priority, state, count(r) AS count ORDER BY count DESC"
        ),
    },
    {
        "metric_id": "rr_patient_gender",
        "title": "Gender distribution of referred patients",
        "description": "Breakdown of referred patients by recorded gender.",
        "output_type": "bar_chart",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "gender", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            "MATCH (r:ReferralRequest)-[:FOR_PATIENT]->(p:Patient) "
            "WHERE " + _RR_ORG_GUARD + " AND " + _DATE_GUARD_RR + " "
            "RETURN coalesce(p.gender, 'unknown') AS gender, "
            "count(r) AS count ORDER BY count DESC"
        ),
    },
    {
        "metric_id": "rr_patient_age_bands",
        "title": "Age distribution of referred patients",
        "description": "Referred patients grouped into standard age bands.",
        "output_type": "bar_chart",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "age_band", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            "MATCH (r:ReferralRequest)-[:FOR_PATIENT]->(p:Patient) "
            "WHERE p.birthDate IS NOT NULL "
            "AND " + _RR_ORG_GUARD + " AND " + _DATE_GUARD_RR + " "
            "WITH date().year - date(p.birthDate).year AS age, r "
            "RETURN CASE "
            "  WHEN age < 18 THEN 'Under 18' "
            "  WHEN age < 30 THEN '18-29' "
            "  WHEN age < 45 THEN '30-44' "
            "  WHEN age < 60 THEN '45-59' "
            "  WHEN age < 75 THEN '60-74' "
            "  ELSE '75+' "
            "END AS age_band, count(r) AS count ORDER BY age_band"
        ),
    },
    {
        "metric_id": "rr_imd_distribution",
        "title": "Deprivation distribution of referred patients",
        "description": "Referred patients grouped by Index of Multiple Deprivation decile.",
        "output_type": "bar_chart",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "imd_group", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            "MATCH (r:ReferralRequest)-[:FOR_PATIENT]->(p:Patient)-[:HAS_ADDRESS]->(a:Address) "
            "WHERE a.imd_decile IS NOT NULL "
            "AND " + _RR_ORG_GUARD + " AND " + _DATE_GUARD_RR + " "
            "RETURN CASE "
            "  WHEN a.imd_decile <= 3 THEN 'Most deprived (1-3)' "
            "  WHEN a.imd_decile <= 7 THEN 'Middle (4-7)' "
            "  ELSE 'Least deprived (8-10)' "
            "END AS imd_group, count(r) AS count ORDER BY imd_group"
        ),
    },
    {
        "metric_id": "rr_document_types",
        "title": "Referral document types",
        "description": "Content types of documents attached to referrals.",
        "output_type": "bar_chart",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "doc_type", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            "MATCH (r:ReferralRequest)-[:HAS_DOCUMENT]->(d:DocumentReference) "
            "WHERE " + _RR_ORG_GUARD + " AND " + _DATE_GUARD_RR + " "
            "RETURN coalesce(d.contentType, 'unknown') AS doc_type, "
            "count(d) AS count ORDER BY count DESC"
        ),
    },
    {
        "metric_id": "rr_data_completeness",
        "title": "Referral data completeness by field",
        "description": (
            "Percentage of referrals with each key relationship present "
            "(Service, Patient, Document, Appointment, Commissioning org)."
        ),
        "output_type": "bar_chart",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "field", "type": "string"},
            {"name": "present_n", "type": "integer"},
            {"name": "total", "type": "integer"},
            {"name": "pct", "type": "float"},
        ],
        "cypher": (
            _RR_BASE
            + "WITH count(r) AS total, "
            "sum(CASE WHEN EXISTS {(r)-[:FOR_SERVICE]->(:Service)} THEN 1 ELSE 0 END) AS n_svc, "
            "sum(CASE WHEN EXISTS {(r)-[:FOR_PATIENT]->(:Patient)} THEN 1 ELSE 0 END) AS n_pat, "
            "sum(CASE WHEN EXISTS {(r)-[:HAS_DOCUMENT]->(:DocumentReference)} THEN 1 ELSE 0 END) AS n_doc, "
            "sum(CASE WHEN EXISTS {(r)-[:HAS_APPOINTMENT]->(:Appointment)} THEN 1 ELSE 0 END) AS n_appt, "
            "sum(CASE WHEN EXISTS {(r)-[:COMMISSIONED_BY]->(:Organization)} THEN 1 ELSE 0 END) AS n_org "
            "UNWIND ["
            "  {field: 'Service', n: n_svc},"
            "  {field: 'Patient', n: n_pat},"
            "  {field: 'Document', n: n_doc},"
            "  {field: 'Appointment', n: n_appt},"
            "  {field: 'Commissioning org', n: n_org}"
            "] AS row "
            "RETURN row.field AS field, row.n AS present_n, total, "
            "round(100.0 * row.n / CASE WHEN total = 0 THEN 1 ELSE total END, 1) AS pct "
            "ORDER BY pct"
        ),
    },
    {
        "metric_id": "rr_dq_score",
        "title": "Referral data quality score",
        "description": (
            "Percentage of referrals with all three core fields complete: "
            "Service, Patient, and at least one Document."
        ),
        "output_type": "kpi_strip",
        "param_schema": _DATE_PARAMS,
        "output_schema": [
            {"name": "metric", "type": "string"},
            {"name": "value", "type": "float"},
            {"name": "target", "type": "float"},
        ],
        "cypher": (
            _RR_BASE
            + "WITH count(r) AS total, "
            "sum(CASE WHEN "
            "  EXISTS {(r)-[:FOR_SERVICE]->(:Service)} AND "
            "  EXISTS {(r)-[:FOR_PATIENT]->(:Patient)} AND "
            "  EXISTS {(r)-[:HAS_DOCUMENT]->(:DocumentReference)} "
            "THEN 1 ELSE 0 END) AS complete_n "
            "RETURN 'Data quality score (%)' AS metric, "
            "round(100.0 * complete_n / CASE WHEN total = 0 THEN 1 ELSE total END, 1) AS value, "
            "95.0 AS target"
        ),
    },
]
