"""Core metric registry: 14 original audit metrics.

Atlas trace:
  DO: DO-F8EFEF89
  DI: DI-E47C3FC2
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-F8EFEF89")

Internal module -- import via audit_metric_queries.py.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Shared Cypher fragments (re-exported by the public module)
# ---------------------------------------------------------------------------

# Tenant guard: restricts patients to orgs in the caller's scope.
# Empty-list bypass: when $scope_org_ids is [] (platform admin), all patients
# are visible. Non-admin callers always have at least one org ID.
#
# Two traversal paths:
#   1. HAS_GENERAL_PRACTITIONER -- primary care / GP practice scope
#   2. REGISTERED_IN            -- secondary care trust / site scope (e.g. M0L1I)
ORG_GUARD = (
    "(size($scope_org_ids) = 0 "
    "OR EXISTS { MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(_gp) "
    "WHERE _gp.id IN $scope_org_ids } "
    "OR EXISTS { MATCH (p)-[:REGISTERED_IN]->(_org_reg) "
    "WHERE _org_reg.id IN $scope_org_ids })"
)

# Episode status filter: exclude phantom/merged/related-closed episodes.
EPISODE_ACTIVE = "NOT ep.status IN ['merged', 'closed_phantom', 'closed_related']"

# ---------------------------------------------------------------------------
# Core metrics (14 original)
# ---------------------------------------------------------------------------

CORE_METRICS: list[dict[str, Any]] = [
    {
        "metric_id": "patient_count",
        "title": "Patient count",
        "description": (
            "Total number of patients with at least one episode in the date range."
        ),
        "output_type": "kpi_strip",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
            "condition_type": {"type": "string", "required": False},
        },
        "output_schema": [{"name": "count", "type": "integer"}],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " "
            "AND ($date_from IS NULL OR ep.referral_date >= $date_from) "
            "AND ($date_to IS NULL OR ep.referral_date <= $date_to) "
            "AND ($condition_type IS NULL OR ep.condition_type = $condition_type) "
            "AND " + EPISODE_ACTIVE + " "
            "RETURN count(DISTINCT p.id) AS count"
        ),
    },
    {
        "metric_id": "episode_count_by_status",
        "title": "Episodes by status",
        "description": "Number of episodes grouped by their current status.",
        "output_type": "bar_chart",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "status", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " "
            "AND ($date_from IS NULL OR ep.referral_date >= $date_from) "
            "AND ($date_to IS NULL OR ep.referral_date <= $date_to) "
            "RETURN coalesce(ep.status, 'unknown') AS status, "
            "count(ep) AS count "
            "ORDER BY count DESC"
        ),
    },
    {
        "metric_id": "episode_count_by_condition",
        "title": "Episodes by condition type",
        "description": (
            "Number of episodes grouped by condition or suspected site type."
        ),
        "output_type": "bar_chart",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "condition_type", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " "
            "AND ($date_from IS NULL OR ep.referral_date >= $date_from) "
            "AND ($date_to IS NULL OR ep.referral_date <= $date_to) "
            "AND " + EPISODE_ACTIVE + " "
            "RETURN coalesce(ep.condition_type, 'unspecified') AS condition_type, "
            "count(ep) AS count "
            "ORDER BY count DESC"
        ),
    },
    {
        "metric_id": "referral_route_distribution",
        "title": "Referral route distribution",
        "description": (
            "How patients were referred (e.g. 2-week wait, urgent, routine), "
            "as count and percentage."
        ),
        "output_type": "bar_chart",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "referral_route", "type": "string"},
            {"name": "n", "type": "integer"},
            {"name": "pct", "type": "float"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " "
            "AND ep.referral_date IS NOT NULL "
            "AND ($date_from IS NULL OR ep.referral_date >= $date_from) "
            "AND ($date_to IS NULL OR ep.referral_date <= $date_to) "
            "AND " + EPISODE_ACTIVE + " "
            "WITH coalesce(ep.referral_route, 'unknown') AS referral_route, "
            "count(ep) AS n "
            "WITH collect({route: referral_route, n: n}) AS rows, "
            "sum(n) AS total "
            "UNWIND rows AS row "
            "RETURN row.route AS referral_route, row.n AS n, "
            "round(100.0 * row.n / total, 1) AS pct "
            "ORDER BY n DESC"
        ),
    },
    {
        "metric_id": "referral_site_distribution",
        "title": "Suspected site at referral",
        "description": (
            "Distribution of the suspected cancer or care site recorded at "
            "the time of referral."
        ),
        "output_type": "bar_chart",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "referral_site", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " "
            "AND ep.referral_site IS NOT NULL "
            "AND ($date_from IS NULL OR ep.referral_date >= $date_from) "
            "AND ($date_to IS NULL OR ep.referral_date <= $date_to) "
            "AND " + EPISODE_ACTIVE + " "
            "RETURN coalesce(ep.referral_site, 'unknown') AS referral_site, "
            "count(ep) AS count "
            "ORDER BY count DESC"
        ),
    },
    {
        "metric_id": "place_of_presentation",
        "title": "Place of first presentation",
        "description": (
            "Where patients first presented before referral "
            "(e.g. GP, A&E, self-referral)."
        ),
        "output_type": "bar_chart",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "place", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " "
            "AND ($date_from IS NULL OR ep.referral_date >= $date_from) "
            "AND ($date_to IS NULL OR ep.referral_date <= $date_to) "
            "AND " + EPISODE_ACTIVE + " "
            "RETURN coalesce(ep.place_of_presentation, 'unknown') AS place, "
            "count(ep) AS count "
            "ORDER BY count DESC"
        ),
    },
    {
        "metric_id": "primary_care_interval",
        "title": "Primary care interval",
        "description": (
            "Number of days from first presentation to referral, "
            "for each episode in the date range."
        ),
        "output_type": "interval_plot",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
            "condition_type": {"type": "string", "required": False},
        },
        "output_schema": [
            {"name": "episode_id", "type": "string"},
            {"name": "interval_days", "type": "integer"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " "
            "AND ep.first_presentation_date IS NOT NULL "
            "AND ep.referral_date IS NOT NULL "
            "AND ($date_from IS NULL OR ep.referral_date >= $date_from) "
            "AND ($date_to IS NULL OR ep.referral_date <= $date_to) "
            "AND ($condition_type IS NULL OR ep.condition_type = $condition_type) "
            "AND " + EPISODE_ACTIVE + " "
            "RETURN ep.episode_id AS episode_id, "
            "duration.between(date(ep.first_presentation_date), "
            "date(ep.referral_date)).days AS interval_days "
            "ORDER BY interval_days"
        ),
    },
    {
        "metric_id": "diagnostic_interval",
        "title": "Diagnostic interval",
        "description": (
            "Number of days from referral to diagnosis, "
            "for each episode in the date range."
        ),
        "output_type": "interval_plot",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
            "condition_type": {"type": "string", "required": False},
        },
        "output_schema": [
            {"name": "episode_id", "type": "string"},
            {"name": "interval_days", "type": "integer"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " "
            "AND ep.referral_date IS NOT NULL "
            "AND ep.diagnosis_date IS NOT NULL "
            "AND ($date_from IS NULL OR ep.referral_date >= $date_from) "
            "AND ($date_to IS NULL OR ep.referral_date <= $date_to) "
            "AND ($condition_type IS NULL OR ep.condition_type = $condition_type) "
            "AND " + EPISODE_ACTIVE + " "
            "RETURN ep.episode_id AS episode_id, "
            "duration.between(date(ep.referral_date), "
            "date(ep.diagnosis_date)).days AS interval_days "
            "ORDER BY interval_days"
        ),
    },
    {
        "metric_id": "episodes_over_time",
        "title": "Episodes over time",
        "description": "Number of new episodes opened per month or quarter.",
        "output_type": "line_chart",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
            "granularity": {
                "type": "string",
                "enum": ["month", "quarter"],
                "required": False,
                "default": "month",
            },
        },
        "output_schema": [
            {"name": "period", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " "
            "AND ep.referral_date IS NOT NULL "
            "AND ($date_from IS NULL OR ep.referral_date >= $date_from) "
            "AND ($date_to IS NULL OR ep.referral_date <= $date_to) "
            "WITH ep, "
            "CASE WHEN $granularity = 'quarter' "
            "  THEN toString(date(ep.referral_date).year) + '-Q' + "
            "       toString(((date(ep.referral_date).month - 1) / 3) + 1) "
            "  ELSE substring(toString(ep.referral_date), 0, 7) "
            "END AS period "
            "RETURN period, count(ep) AS count "
            "ORDER BY period"
        ),
    },
    {
        "metric_id": "coding_completeness",
        "title": "Coding completeness",
        "description": (
            "Percentage of encounters that have at least one coded finding."
        ),
        "output_type": "kpi_strip",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "coded_count", "type": "integer"},
            {"name": "total_count", "type": "integer"},
            {"name": "pct", "type": "float"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE " + ORG_GUARD + " "
            "AND ($date_from IS NULL OR toString(e.date) >= $date_from) "
            "AND ($date_to IS NULL OR toString(e.date) <= $date_to) "
            "OPTIONAL MATCH (e)-[doc:DOCUMENTS]->() "
            "WITH e, count(doc) AS doc_count "
            "RETURN count(e) AS total_count, "
            "count(CASE WHEN doc_count > 0 THEN 1 END) AS coded_count, "
            "round(100.0 * count(CASE WHEN doc_count > 0 THEN 1 END) / "
            "CASE WHEN count(e) = 0 THEN 1 ELSE count(e) END, 1) AS pct"
        ),
    },
    {
        "metric_id": "top_coded_conditions",
        "title": "Most common coded conditions",
        "description": (
            "The most frequently coded SNOMED disorders across all encounters."
        ),
        "output_type": "table",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
            "limit": {
                "type": "integer",
                "minimum": 5,
                "maximum": 50,
                "required": False,
                "default": 20,
            },
        },
        "output_schema": [
            {"name": "concept_id", "type": "string"},
            {"name": "term", "type": "string"},
            {"name": "n", "type": "integer"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)"
            "-[:DOCUMENTS]->(c) "
            "WHERE " + ORG_GUARD + " "
            "AND ($date_from IS NULL OR toString(e.date) >= $date_from) "
            "AND ($date_to IS NULL OR toString(e.date) <= $date_to) "
            "RETURN coalesce(c.id, 'unknown') AS concept_id, "
            "coalesce(c.fsn, c.term, 'unknown') AS term, "
            "count(*) AS n "
            "ORDER BY n DESC "
            "LIMIT $limit"
        ),
    },
    {
        "metric_id": "safety_net_alerts_by_type",
        "title": "Safety netting alerts by type",
        "description": "Count of safety netting alerts grouped by alert type.",
        "output_type": "bar_chart",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "alert_type", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_SAFETY_NET_ALERT]->(a:SafetyNetAlert) "
            "WHERE " + ORG_GUARD + " "
            "AND ($date_from IS NULL OR toString(a.created_at) >= $date_from) "
            "AND ($date_to IS NULL OR toString(a.created_at) <= $date_to) "
            "RETURN coalesce(a.alert_type, 'unknown') AS alert_type, "
            "count(a) AS count "
            "ORDER BY count DESC"
        ),
    },
    {
        "metric_id": "cancer_type_distribution",
        "title": "Cancer type distribution",
        "description": (
            "Distribution of confirmed cancer types across completed episodes, "
            "with optional benchmark overlay."
        ),
        "output_type": "bar_chart",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "cancer_type", "type": "string"},
            {"name": "n", "type": "integer"},
            {"name": "pct", "type": "float"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " "
            "AND ep.cancer_type IS NOT NULL "
            "AND ep.inferred_outcome = 'cancer' "
            "AND ($date_from IS NULL OR ep.referral_date >= $date_from) "
            "AND ($date_to IS NULL OR ep.referral_date <= $date_to) "
            "WITH ep.cancer_type AS cancer_type, count(ep) AS n "
            "WITH collect({ct: cancer_type, n: n}) AS rows, sum(n) AS total "
            "UNWIND rows AS row "
            "RETURN row.ct AS cancer_type, row.n AS n, "
            "round(100.0 * row.n / total, 1) AS pct "
            "ORDER BY n DESC"
        ),
    },
    {
        "metric_id": "cancer_stage_distribution",
        "title": "Cancer stage at diagnosis",
        "description": (
            "Distribution of cancer stage at the point of diagnosis "
            "across completed episodes."
        ),
        "output_type": "bar_chart",
        "param_schema": {
            "date_from": {"type": "string", "format": "date", "required": False},
            "date_to": {"type": "string", "format": "date", "required": False},
        },
        "output_schema": [
            {"name": "stage", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
        "cypher": (
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE " + ORG_GUARD + " "
            "AND ep.inferred_outcome = 'cancer' "
            "AND ($date_from IS NULL OR ep.referral_date >= $date_from) "
            "AND ($date_to IS NULL OR ep.referral_date <= $date_to) "
            "RETURN coalesce(ep.stage_at_diagnosis, 'unknown') AS stage, "
            "count(ep) AS count "
            "ORDER BY stage"
        ),
    },
]
