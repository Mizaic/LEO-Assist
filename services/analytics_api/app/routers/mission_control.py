"""Mission Control endpoints for Clinical Audit case management.

Atlas trace:
  DO: DO-9F3CD7DE
  Also implements: DO-A6D3FE39
  DI: DI-BA2C8F3E, DI-CF03E4EA
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-9F3CD7DE")

Provides endpoints:
  GET  /mission-control/patients  -- paginated, filtered patient+episode list
  GET  /mission-control/kpis      -- 6 aggregate KPI values for filter context
  GET  /mission-control/patients/{patient_id}/pipeline-events
        -- PipelineRun AuditEvent rows for the audit trail tab
  PATCH /mission-control/episodes/{episode_id}/review  -- write audit tracking

All patient queries reuse _audit_helpers org-scope logic and date filters.
The review PATCH writes only audit tracking fields (reviewed_by, reviewed_at,
audit_notes, audit_flag) -- never clinical coding data.
"""

from __future__ import annotations

import logging
import os
import re
import statistics
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from libs.analytics import confirmed_cancer_where
from libs.auth.org_scope import ORG_PATIENT_FILTER, CallerScope, get_caller_scope
from libs.episodes.lifecycle import HERO_BUCKETS, build_hero_bucket_case
from libs.episodes.status import (
    ALWAYS_EXCLUDE_STATUSES,
    CLOSURE_REASON_STATUSES,
)
from libs.neo4j_client.client import PatientGraphClient
from libs.redis_client.rebuild_status import get_rebuild_status
from services.analytics_api.app.routers._audit_helpers import (
    _add_date_filters,
    _episode_base,
)
from services.analytics_api.app.services.reconcile_pathway import (
    BucketFlipNotConfirmedError,
    EpisodeNotFoundError,
    EpisodeSnapshot,
    ReconcileRequest,
    UnknownSlotError,
    reconcile_episode,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Status groupings
# ---------------------------------------------------------------------------

# Re-exported for backwards compatibility -- tests import these directly.
# Source of truth lives in libs/episodes/status.py (DI-LEO-AI-529).
_CLOSURE_STATUSES = list(CLOSURE_REASON_STATUSES)
_ALWAYS_EXCLUDE = list(ALWAYS_EXCLUDE_STATUSES)

_MAX_MISSION_PATIENT_ID_LEN = 64
_MISSION_PATIENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_MAX_EPISODE_ID_LEN = 128
_MISSION_EPISODE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ReviewRequest(BaseModel):
    reviewed_by: str
    audit_notes: Optional[str] = None
    audit_flag: bool = False


# ---------------------------------------------------------------------------
# Internal Cypher helpers
# ---------------------------------------------------------------------------


def _apply_pathway_filter(
    base: str, params: dict, pathway_filter: str
) -> tuple[str, dict]:
    """Append pathway status WHERE clause to base match.

    'confirmed' uses the canonical NCDA confirmed-cancer cohort so the
    Mission Control patient list stays aligned with the /audit/summary
    headline (DI-LEO-AI-134).
    """
    if pathway_filter == "confirmed":
        base = base.rstrip() + f" AND {confirmed_cancer_where('ep')} "
    elif pathway_filter == "closures":
        statuses = ", ".join(f"'{s}'" for s in _CLOSURE_STATUSES)
        base = base.rstrip() + f" AND ep.status IN [{statuses}] "
    else:
        exclude = ", ".join(f"'{s}'" for s in _ALWAYS_EXCLUDE)
        base = base.rstrip() + f" AND NOT ep.status IN [{exclude}] "
    return base, params


# Allowed values for the lifecycle_bucket query parameter.
# 'all' is the wildcard that disables the filter; the four canonical
# MECE buckets reuse the same Cypher CASE expression as the dashboard
# hero cards so the filtered patient list is exactly the cohort behind
# the headline number (DI-105A4EC7 / R-24C3AAED). 'no_pathway' is the
# fifth bucket surfaced by DI-CA1B4C6E: patients in the cohort for
# whom the Episode Engine has not produced any EpisodeOfCare yet.
NO_PATHWAY_BUCKET = "no_pathway"
_LIFECYCLE_BUCKET_VALUES = ("all", NO_PATHWAY_BUCKET) + tuple(HERO_BUCKETS)
LIFECYCLE_BUCKET_PATTERN = (
    "^(all|" + NO_PATHWAY_BUCKET + "|" + "|".join(HERO_BUCKETS) + ")$"
)


def _apply_lifecycle_bucket_filter(
    base: str, params: dict, lifecycle_bucket: str
) -> tuple[str, dict]:
    """Append a WHERE clause that matches only the given hero bucket.

    Reuses ``libs.episodes.lifecycle.build_hero_bucket_case('ep')`` so
    the patient list returned by Mission Control is the same cohort
    that produced the four hero numbers on the dashboard. The
    'no_pathway' bucket is structurally different (matches patients
    with NO EpisodeOfCare) and is handled by a dedicated query path
    in the patients/kpis endpoints, so this helper is a no-op for it.
    """
    if lifecycle_bucket not in HERO_BUCKETS:
        return base, params
    case_expr = build_hero_bucket_case("ep")
    params = {**params, "lifecycle_bucket": lifecycle_bucket}
    base = base.rstrip() + f" AND {case_expr} = $lifecycle_bucket "
    return base, params


def _no_pathway_scope_match(
    org_id: Optional[str], scope: CallerScope
) -> tuple[str, dict]:
    """Return (match_clause, params) for patients-without-pathway.

    Used by the lifecycle_bucket='no_pathway' deep-link from the
    dashboard cohort summary card. Mirrors the org/scope predicates
    used by Mission Control's cohort denominator so the deep-link
    cohort exactly equals patients_without_pathway from
    /audit/summary. See DI-CA1B4C6E.
    """
    no_episode = "NOT EXISTS { (p)-[:HAS_EPISODE_OF_CARE]->(:EpisodeOfCare) }"
    if scope.is_admin and not org_id:
        return f"MATCH (p:Patient) WHERE {no_episode} ", {}
    effective_org = org_id or scope.primary_org_id
    if effective_org:
        return (
            "MATCH (_scope:Organization {id: $org}) "
            "MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
            "WHERE ((gp.id = $org) OR (gp)-[:COMMISSIONED_BY]->(_scope) "
            "    OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(_scope)) "
            f"AND {no_episode} ",
            {"org": effective_org},
        )
    return (
        f"MATCH (p:Patient) WHERE {ORG_PATIENT_FILTER} AND {no_episode} ",
        scope.to_query_params(),
    )


def _no_pathway_patients_cypher(
    base: str, params: dict, skip: int, limit: int
) -> tuple[str, str, dict]:
    """Return (count_query, data_query, params) for the no-pathway list.

    Returns each patient with episodes=[] - there are no
    EpisodeOfCare nodes by definition for this bucket. See
    DI-CA1B4C6E.
    """
    count_q = f"{base}RETURN count(DISTINCT p) AS total"
    data_q = (
        f"{base}"
        "WITH p ORDER BY p.id ASC SKIP $skip LIMIT $limit "
        "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp:Organization) "
        "RETURN "
        "  p.id AS patient_id, "
        "  p.gender AS gender, "
        "  p.birthDate AS birth_date, "
        "  gp.name AS practice_name, "
        "  [] AS episodes"
    )
    params = {**params, "skip": skip, "limit": limit}
    return count_q, data_q, params


def _apply_cancer_type_filter(
    base: str, params: dict, cancer_types: list[str]
) -> tuple[str, dict]:
    """Append cancer_type IN filter when cancer_types list is non-empty."""
    if not cancer_types:
        return base, params
    params = {**params, "cancer_types": cancer_types}
    base = base.rstrip() + " AND ep.cancer_type IN $cancer_types "
    return base, params


def _apply_closure_reason_filter(
    base: str, params: dict, closure_reasons: list[str]
) -> tuple[str, dict]:
    """Append closure reason (ep.status) IN filter."""
    if not closure_reasons:
        return base, params
    params = {**params, "closure_reasons": closure_reasons}
    base = base.rstrip() + " AND ep.status IN $closure_reasons "
    return base, params


def _apply_review_filter(
    base: str, params: dict, review_status: str
) -> tuple[str, dict]:
    """Append reviewed_at IS NULL / IS NOT NULL filter."""
    if review_status == "unreviewed":
        base = base.rstrip() + " AND ep.reviewed_at IS NULL "
    elif review_status == "reviewed":
        base = base.rstrip() + " AND ep.reviewed_at IS NOT NULL "
    return base, params


def _normalise_mission_patient_id(raw: Optional[str]) -> Optional[str]:
    """Return a safe patient id token for Cypher, or None if absent/invalid."""
    if raw is None:
        return None
    s = raw.strip()
    if not s or len(s) > _MAX_MISSION_PATIENT_ID_LEN:
        return None
    if not _MISSION_PATIENT_ID_PATTERN.match(s):
        return None
    return s


def _normalise_mission_episode_id(raw: Optional[str]) -> Optional[str]:
    """Return a safe episode id for Cypher, or None if absent/invalid."""
    if raw is None:
        return None
    s = raw.strip()
    if not s or len(s) > _MAX_EPISODE_ID_LEN:
        return None
    if not _MISSION_EPISODE_ID_PATTERN.match(s):
        return None
    return s


def _patient_pipeline_audit_prefix(
    scope: CallerScope,
    org_id: Optional[str],
) -> tuple[str, dict]:
    """Return (cypher_prefix, extra_params) that bind ``p:Patient`` in org scope."""
    effective_org = org_id if scope.is_admin else (org_id or scope.primary_org_id)
    if effective_org:
        q = (
            "MATCH (_scope:Organization {id: $org}) "
            "MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
            "WHERE toString(p.id) = $patient_id "
            "AND ((gp.id = $org) OR (gp)-[:COMMISSIONED_BY]->(_scope) OR "
            "(gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(_scope)) "
        )
        return q, {"org": effective_org}
    if scope.is_admin:
        return "MATCH (p:Patient) WHERE toString(p.id) = $patient_id ", {}
    q = (
        "MATCH (p:Patient) "
        "WHERE toString(p.id) = $patient_id "
        f"AND {ORG_PATIENT_FILTER} "
    )
    return q, {**scope.to_query_params()}


def _truncate_audit_text(raw: Optional[str], max_len: int = 800) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw)
    if len(s) <= max_len:
        return s
    return s[:max_len] + "..."


def _pipeline_queue_depth() -> Optional[int]:
    conn = os.getenv("AZURE_SERVICE_BUS_CONNECTION_STRING", "").strip()
    queue_name = (
        os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs").strip() or "pipeline-jobs"
    )
    if not conn:
        return None
    try:
        from azure.servicebus.management import ServiceBusAdministrationClient

        admin = ServiceBusAdministrationClient.from_connection_string(conn)
        props = admin.get_queue_runtime_properties(queue_name)
        return int(getattr(props, "active_message_count", 0) or 0)
    except Exception:
        logger.debug("Could not read Service Bus runtime properties", exc_info=True)
        return None


def _duration_and_throughput_estimate() -> tuple[Optional[float], Optional[float]]:
    """Return (median_duration_seconds, throughput_runs_per_minute)."""
    q = (
        "MATCH (ae:AuditEvent) "
        "WHERE coalesce(ae.`type`, '') = 'PipelineRun' "
        "  AND ae.total_duration_ms IS NOT NULL "
        "  AND ae.created_at >= datetime() - duration('PT60M') "
        "RETURN ae.total_duration_ms AS total_duration_ms, ae.created_at AS created_at "
        "ORDER BY ae.created_at DESC "
        "LIMIT 500"
    )
    client = PatientGraphClient()
    try:
        rows = client.run(q)
    finally:
        client.close()

    if not rows:
        return None, None

    durations_ms = [
        float(r.get("total_duration_ms"))
        for r in rows
        if r.get("total_duration_ms") is not None
    ]
    if not durations_ms:
        return None, None

    median_seconds = statistics.median(durations_ms) / 1000.0
    throughput_per_minute = len(durations_ms) / 60.0
    return median_seconds, throughput_per_minute


def _apply_patient_id_filter(
    base: str, params: dict, patient_id: Optional[str]
) -> tuple[str, dict]:
    """Restrict to a single Patient node when patient_id is valid."""
    pid = _normalise_mission_patient_id(patient_id)
    if not pid:
        return base, params
    params = {**params, "patient_id": pid}
    base = base.rstrip() + " AND toString(p.id) = $patient_id "
    return base, params


def _build_filtered_base(
    org_id: Optional[str],
    scope: CallerScope,
    date_from: Optional[str],
    date_to: Optional[str],
    pathway_filter: str,
    cancer_types: list[str],
    closure_reasons: list[str],
    review_status: str,
    patient_id: Optional[str] = None,
    lifecycle_bucket: str = "all",
) -> tuple[str, dict]:
    """Build full filtered match clause from all filter params."""
    base, params = _episode_base(org_id, scope)
    base, params = _add_date_filters(base, params, date_from, date_to)
    base, params = _apply_pathway_filter(base, params, pathway_filter)
    base, params = _apply_lifecycle_bucket_filter(base, params, lifecycle_bucket)
    base, params = _apply_cancer_type_filter(base, params, cancer_types)
    base, params = _apply_closure_reason_filter(base, params, closure_reasons)
    base, params = _apply_review_filter(base, params, review_status)
    base, params = _apply_patient_id_filter(base, params, patient_id)
    return base, params


def _sort_clause(sort_by: str, sort_dir: str) -> str:
    """Return ORDER BY clause for supported sort fields."""
    allowed = {
        "referral_date": "ep.referral_date",
        "reviewed_at": "ep.reviewed_at",
        "diagnostic_interval": "ep.diagnostic_interval_days",
        "cancer_type": "ep.cancer_type",
    }
    field = allowed.get(sort_by, "ep.referral_date")
    direction = "ASC" if sort_dir.upper() == "ASC" else "DESC"
    # Neo4j rejects "NULLS FIRST/LAST" in ORDER BY on this stack (GQL 42I06).
    # Sort non-null before null via (field IS NULL) ASC, then by value.
    return f"ORDER BY ep.reviewed_at IS NOT NULL ASC, ({field} IS NULL) ASC, {field} {direction}"


# ---------------------------------------------------------------------------
# Patients query
# ---------------------------------------------------------------------------


# Per-episode projection shared between the cohort list and the
# per-patient drawer endpoint (DI-5E47FA5D). Both surfaces MUST return
# identical episode shapes so the UI can swap one for the other
# without per-field translation.
_EPISODE_PROJECTION = (
    "{ "
    "  episode_id: ep.episode_id, "
    "  cancer_type: ep.cancer_type, "
    "  condition_type: ep.condition_type, "
    "  status: ep.status, "
    "  cancer_stage: ep.cancer_stage, "
    "  referral_date: toString(ep.referral_date), "
    "  end_date: toString(ep.end_date), "
    "  specialist_visit_date: toString(ep.specialist_visit_date), "
    "  diagnostic_interval_days: ep.diagnostic_interval_days, "
    "  primary_care_interval_days: ep.primary_care_interval_days, "
    "  inferred_outcome: ep.inferred_outcome, "
    "  auto_close_reason: ep.auto_close_reason, "
    "  reviewed_by: ep.reviewed_by, "
    "  reviewed_at: toString(ep.reviewed_at), "
    "  audit_notes: ep.audit_notes, "
    "  audit_flag: coalesce(ep.audit_flag, false), "
    "  linked_encounter_ids: [ "
    "    (ep)<-[:IS_PART_OF]-(enc_all:Encounter) "
    "    | toString(enc_all.id) "
    "  ], "
    "  milestones: [ "
    "    (ep)<-[r:IS_PART_OF]-(enc:Encounter) "
    "    WHERE r.milestone_type IS NOT NULL "
    "    | { "
    "        milestone_type: r.milestone_type, "
    "        encounter_id: toString(enc.id), "
    "        date: toString(enc.date) "
    "      } "
    "  ] "
    "}"
)


def _patients_cypher(
    base: str, params: dict, sort_by: str, sort_dir: str, skip: int, limit: int
) -> tuple[str, str, dict]:
    """Return (count_query, data_query, params) for the patient list."""
    count_q = f"{base}" "WITH count(DISTINCT p) AS total " "RETURN total"
    sort = _sort_clause(sort_by, sort_dir)
    data_q = (
        f"{base}"
        "WITH p, ep "
        f"{sort} "
        "WITH p, collect(DISTINCT ep) AS episodes "
        "WITH p, episodes, "
        "CASE WHEN (episodes[0]).reviewed_at IS NULL THEN 0 ELSE 1 END AS review_rank "
        "ORDER BY review_rank ASC "
        "SKIP $skip LIMIT $limit "
        "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp:Organization) "
        "RETURN "
        "  p.id AS patient_id, "
        "  p.gender AS gender, "
        "  p.birthDate AS birth_date, "
        "  gp.name AS practice_name, "
        f"  [ep IN episodes | {_EPISODE_PROJECTION}] AS episodes "
    )
    params = {**params, "skip": skip, "limit": limit}
    return count_q, data_q, params


def _calculate_age(birth_date: Optional[str]) -> Optional[int]:
    """Approximate age in years from ISO birth date string."""
    if not birth_date:
        return None
    try:
        from datetime import date

        born = date.fromisoformat(str(birth_date)[:10])
        today = date.today()
        return (
            today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        )
    except (ValueError, TypeError):
        return None


def _row_to_patient(row: dict) -> dict:
    """Map a Neo4j result row to the patient response shape."""
    return {
        "patient_id": row["patient_id"],
        "gender": row.get("gender"),
        "age": _calculate_age(row.get("birth_date")),
        "practice_name": row.get("practice_name"),
        "episodes": row.get("episodes") or [],
    }


def _patient_only_query(
    scope: CallerScope,
    org_id: Optional[str],
    patient_id: str,
) -> tuple[str, dict[str, Any]]:
    """Build scoped patient-only query for exact-id fallback."""
    prefix, extra = _patient_pipeline_audit_prefix(scope, org_id)
    query = (
        f"{prefix}"
        "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp:Organization) "
        "RETURN "
        "  p.id AS patient_id, "
        "  p.gender AS gender, "
        "  p.birthDate AS birth_date, "
        "  gp.name AS practice_name "
        "LIMIT 1"
    )
    return query, {**extra, "patient_id": patient_id}


# ---------------------------------------------------------------------------
# KPI query
# ---------------------------------------------------------------------------


def _kpis_cypher(base: str, params: dict) -> tuple[str, dict]:
    """Return (query, params) for the Mission Control KPI aggregation.

    DI-LEO-AI-214 (Mission Control KPI unit clarity): the KPI block returns
    BOTH episode counts (canonical NCDA, what the audit endpoint reports)
    AND patient counts (what the KPI strip label promises). The UI shows
    patients as the headline number and episodes as a sub-line so the
    label "Patients with..." matches what is on screen.

    confirmed_cancer / confirmed_cancer_patients use the canonical NCDA
    cohort helper so the headline figure agrees with /audit/summary
    (DI-LEO-AI-134).
    """
    confirmed = confirmed_cancer_where("ep")
    q = (
        f"{base}"
        "WITH ep, p "
        "RETURN "
        "  count(DISTINCT p) AS total_patients, "
        f"  count(DISTINCT CASE WHEN ({confirmed}) THEN ep END) "
        "    AS confirmed_cancer, "
        f"  count(DISTINCT CASE WHEN ({confirmed}) THEN p END) "
        "    AS confirmed_cancer_patients, "
        "  count(DISTINCT CASE WHEN ep.status IN "
        f"    {_CLOSURE_STATUSES!r} THEN ep END) AS pathway_closures, "
        "  count(DISTINCT CASE WHEN ep.status IN "
        f"    {_CLOSURE_STATUSES!r} THEN p END) AS pathway_closure_patients, "
        "  percentileCont(toFloat(ep.diagnostic_interval_days), 0.5) AS median_diagnostic_interval_days, "
        "  toFloat(count(DISTINCT CASE WHEN ep.safety_netting_milestone IS NOT NULL "
        "    AND ep.safety_netting_milestone <> '' THEN ep END)) / "
        "  CASE WHEN count(ep) > 0 THEN toFloat(count(ep)) ELSE 1.0 END AS safety_netting_rate, "
        "  count(DISTINCT CASE WHEN ep.reviewed_at IS NULL THEN ep END) AS needs_review_count "
    )
    return q, params


def _cohort_denominator_cypher(
    org_id: Optional[str],
    scope: CallerScope,
    date_from: Optional[str],
    date_to: Optional[str],
) -> tuple[str, dict]:
    """Return (query, params) for the cohort denominator + excluded buckets.

    DI-LEO-AI-214: the KPI strip filter context can hide patients whose
    only EpisodeOfCare nodes either (a) do not exist, (b) all carry an
    excluded status (merged / closed_phantom / closed_related), or
    (c) have a NULL or out-of-window referral_date. These patients
    silently disappear from "Patients in view" today; the cohort
    denominator surfaces them so the user always knows the headline
    figure (89) sits inside a known cohort total (107) with a known
    excluded breakdown (no pathway / outside window / missing referral
    date).

    The query is intentionally scoped by org / caller scope ONLY -- the
    date / pathway / cancer-type / closure-reason filters do NOT apply.
    """
    if scope.is_admin and not org_id:
        scope_match = "MATCH (p:Patient) "
        scope_params: dict = {}
    elif org_id or scope.primary_org_id:
        effective_org = org_id or scope.primary_org_id
        scope_match = (
            "MATCH (_scope:Organization {id: $org}) "
            "MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
            "WHERE (gp.id = $org) OR (gp)-[:COMMISSIONED_BY]->(_scope) "
            "   OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(_scope) "
        )
        scope_params = {"org": effective_org}
    else:
        scope_match = "MATCH (p:Patient) " f"WHERE {ORG_PATIENT_FILTER} "
        scope_params = scope.to_query_params()

    # DI-LEO-AI-214: an episode is "in view" for the KPI strip when its
    # status is not in the always-excluded list AND its referral_date
    # falls inside the configured window. Anything else means the
    # patient is hidden by either status, missing referral date, or an
    # out-of-window referral. We split the excluded bucket so the user
    # can see WHY a patient is hidden.
    date_lo = date_from or "0001-01-01"
    date_hi = date_to or "9999-12-31"
    excluded = list(_ALWAYS_EXCLUDE)
    in_view_predicate = (
        f"NOT ep.status IN {excluded!r} "
        "AND ep.referral_date IS NOT NULL "
        f"AND ep.referral_date >= '{date_lo}' "
        f"AND ep.referral_date <= '{date_hi}' "
    )
    has_any_episode = "EXISTS { MATCH (p)-[:HAS_EPISODE_OF_CARE]->(:EpisodeOfCare) }"
    has_in_view_episode = (
        "EXISTS { MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
        f"WHERE {in_view_predicate}}}"
    )
    has_episode_with_null_ref = (
        "EXISTS { MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
        f"WHERE NOT ep.status IN {excluded!r} "
        "AND ep.referral_date IS NULL }"
    )

    q = (
        f"{scope_match}"
        "RETURN "
        "  count(DISTINCT p) AS cohort_total_patients, "
        "  count(DISTINCT p) - count(DISTINCT CASE WHEN "
        f"    {has_in_view_episode} THEN p END) AS excluded_total, "
        "  count(DISTINCT CASE WHEN NOT "
        f"    {has_any_episode} THEN p END) AS excluded_no_pathway, "
        "  count(DISTINCT CASE WHEN "
        f"    {has_any_episode} AND NOT {has_in_view_episode} "
        f"    AND {has_episode_with_null_ref} "
        "    THEN p END) AS excluded_missing_referral_date, "
        "  count(DISTINCT CASE WHEN "
        f"    {has_any_episode} AND NOT {has_in_view_episode} "
        f"    AND NOT {has_episode_with_null_ref} "
        "    THEN p END) AS excluded_outside_window "
    )
    return q, scope_params


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/mission-control/patients")
def get_mission_control_patients(
    org_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    pathway_filter: str = Query("all", pattern="^(confirmed|closures|all)$"),
    lifecycle_bucket: str = Query(
        "all",
        pattern=LIFECYCLE_BUCKET_PATTERN,
        description=(
            "Lifecycle bucket from the dashboard cohort summary: "
            "active, in_review, cancer_excluded, confirmed_cancer "
            "(four MECE hero cards), no_pathway (patients in cohort "
            "with no EpisodeOfCare), or all."
        ),
    ),
    cancer_types: Optional[str] = Query(
        None, description="Comma-separated cancer type keys"
    ),
    closure_reasons: Optional[str] = Query(
        None, description="Comma-separated closure statuses"
    ),
    review_status: str = Query("all", pattern="^(all|reviewed|unreviewed)$"),
    patient_id: Optional[str] = Query(
        None,
        max_length=_MAX_MISSION_PATIENT_ID_LEN,
        description="Optional exact patient id (matches Patient.id)",
    ),
    sort_by: str = Query("referral_date"),
    sort_dir: str = Query("DESC"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return paginated, filtered list of patients with nested episode data."""
    cancer_type_list = (
        [t.strip() for t in cancer_types.split(",")] if cancer_types else []
    )
    closure_reason_list = (
        [r.strip() for r in closure_reasons.split(",")] if closure_reasons else []
    )

    skip = (page - 1) * page_size

    # The 'no_pathway' bucket lists patients in scope who have NO
    # EpisodeOfCare. The standard filtered-base joins through
    # HAS_EPISODE_OF_CARE and would return zero rows, so we use a
    # dedicated query path that returns each patient with episodes=[].
    # See DI-CA1B4C6E.
    if lifecycle_bucket == NO_PATHWAY_BUCKET:
        np_base, np_params = _no_pathway_scope_match(org_id, scope)
        count_q, data_q, qparams = _no_pathway_patients_cypher(
            np_base, np_params, skip, page_size
        )
    else:
        base, params = _build_filtered_base(
            org_id,
            scope,
            date_from,
            date_to,
            pathway_filter,
            cancer_type_list,
            closure_reason_list,
            review_status,
            patient_id,
            lifecycle_bucket=lifecycle_bucket,
        )
        count_q, data_q, qparams = _patients_cypher(
            base, params, sort_by, sort_dir, skip, page_size
        )

    client = PatientGraphClient()
    try:
        count_rows = client.run(count_q, **qparams)
        total = count_rows[0]["total"] if count_rows else 0

        data_rows = client.run(data_q, **qparams)
        patients = [_row_to_patient(r) for r in data_rows]

        pid = _normalise_mission_patient_id(patient_id)
        if pid and total == 0 and lifecycle_bucket != NO_PATHWAY_BUCKET:
            fallback_q, fallback_params = _patient_only_query(scope, org_id, pid)
            fallback_rows = client.run(fallback_q, **fallback_params)
            if fallback_rows:
                patient = _row_to_patient({**dict(fallback_rows[0]), "episodes": []})
                patients = [patient]
                total = 1
    finally:
        client.close()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "patients": patients,
    }


@router.get("/mission-control/kpis")
def get_mission_control_kpis(
    org_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    pathway_filter: str = Query("all", pattern="^(confirmed|closures|all)$"),
    lifecycle_bucket: str = Query(
        "all",
        pattern=LIFECYCLE_BUCKET_PATTERN,
        description=(
            "Lifecycle bucket from the dashboard cohort summary: "
            "active, in_review, cancer_excluded, confirmed_cancer "
            "(four MECE hero cards), no_pathway (patients in cohort "
            "with no EpisodeOfCare), or all."
        ),
    ),
    cancer_types: Optional[str] = Query(None),
    closure_reasons: Optional[str] = Query(None),
    review_status: str = Query("all", pattern="^(all|reviewed|unreviewed)$"),
    patient_id: Optional[str] = Query(
        None,
        max_length=_MAX_MISSION_PATIENT_ID_LEN,
        description="Optional exact patient id (matches Patient.id)",
    ),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return 6 aggregate KPI values for the current Mission Control filter context."""
    cancer_type_list = (
        [t.strip() for t in cancer_types.split(",")] if cancer_types else []
    )
    closure_reason_list = (
        [r.strip() for r in closure_reasons.split(",")] if closure_reasons else []
    )

    cohort_q, cohort_params = _cohort_denominator_cypher(
        org_id, scope, date_from, date_to
    )

    # The 'no_pathway' bucket has no EpisodeOfCare nodes by
    # construction, so every episode-derived KPI is zero. We still
    # compute the cohort denominator so the KPI strip can render
    # "Showing N of <cohort> patients - <cohort - N> hidden". See
    # DI-CA1B4C6E.
    if lifecycle_bucket == NO_PATHWAY_BUCKET:
        np_base, np_params = _no_pathway_scope_match(org_id, scope)
        np_count_q = f"{np_base}RETURN count(DISTINCT p) AS no_pathway_patients"
        client = PatientGraphClient()
        try:
            np_rows = client.run(np_count_q, **np_params)
            cohort_rows = client.run(cohort_q, **cohort_params)
        finally:
            client.close()
        np_patients = int((np_rows or [{}])[0].get("no_pathway_patients") or 0)
        rows = [
            {
                "total_patients": np_patients,
                "confirmed_cancer": 0,
                "confirmed_cancer_patients": 0,
                "pathway_closures": 0,
                "pathway_closure_patients": 0,
                "median_diagnostic_interval_days": None,
                "safety_netting_rate": 0.0,
                "needs_review_count": 0,
            }
        ]
    else:
        base, params = _build_filtered_base(
            org_id,
            scope,
            date_from,
            date_to,
            pathway_filter,
            cancer_type_list,
            closure_reason_list,
            review_status,
            patient_id,
            lifecycle_bucket=lifecycle_bucket,
        )
        q, qparams = _kpis_cypher(base, params)
        client = PatientGraphClient()
        try:
            rows = client.run(q, **qparams)
            cohort_rows = client.run(cohort_q, **cohort_params)
        finally:
            client.close()

    cohort = cohort_rows[0] if cohort_rows else {}
    cohort_block = {
        "total_patients": int(cohort.get("cohort_total_patients", 0) or 0),
        "excluded_total": int(cohort.get("excluded_total", 0) or 0),
        "excluded_no_pathway": int(cohort.get("excluded_no_pathway", 0) or 0),
        "excluded_missing_referral_date": int(
            cohort.get("excluded_missing_referral_date", 0) or 0
        ),
        "excluded_outside_window": int(cohort.get("excluded_outside_window", 0) or 0),
    }

    if not rows:
        return {
            "total_patients": 0,
            "confirmed_cancer": 0,
            "confirmed_cancer_patients": 0,
            "pathway_closures": 0,
            "pathway_closure_patients": 0,
            "median_diagnostic_interval_days": None,
            "safety_netting_rate": 0.0,
            "needs_review_count": 0,
            "cohort": cohort_block,
        }

    row = rows[0]
    return {
        "total_patients": row.get("total_patients", 0),
        "confirmed_cancer": row.get("confirmed_cancer", 0),
        "confirmed_cancer_patients": row.get("confirmed_cancer_patients", 0),
        "pathway_closures": row.get("pathway_closures", 0),
        "pathway_closure_patients": row.get("pathway_closure_patients", 0),
        "median_diagnostic_interval_days": row.get("median_diagnostic_interval_days"),
        "safety_netting_rate": float(row.get("safety_netting_rate") or 0.0),
        "needs_review_count": row.get("needs_review_count", 0),
        "cohort": cohort_block,
    }


def _row_to_pipeline_event(row: dict[str, Any]) -> dict[str, Any]:
    """Map a Neo4j result row to a JSON-serialisable pipeline audit entry."""
    return {
        # Identity
        "id": row.get("id"),
        "pipeline_kind": row.get("pipeline_kind"),
        "status": row.get("status"),
        "created_at": row.get("created_at"),
        "encounter_id": row.get("encounter_id") or "",
        "run_id": row.get("run_id"),
        "event_type": row.get("event_type"),
        "plan_definition_id": row.get("plan_definition_id"),
        # Run outcome (flat scalars)
        "step_count": row.get("step_count"),
        "total_duration_ms": row.get("total_duration_ms"),
        "entity_count": row.get("entity_count"),
        "error_count": row.get("error_count"),
        "first_error": row.get("first_error"),
        # LLM spend
        "llm_input_tokens": row.get("llm_input_tokens"),
        "llm_output_tokens": row.get("llm_output_tokens"),
        "llm_cached_tokens": row.get("llm_cached_tokens"),
        "llm_cost_usd": row.get("llm_cost_usd"),
        # Extraction step provenance (flat scalars -- enables model regression display)
        "extraction_prompt_name": row.get("extraction_prompt_name") or "",
        "extraction_prompt_version": row.get("extraction_prompt_version"),
        "extraction_prompt_hash": row.get("extraction_prompt_hash") or "",
        "extraction_provider": row.get("extraction_provider") or "",
        "extraction_model_tier": row.get("extraction_model_tier") or "",
        # Detail blobs (JSON strings for UI rendering, not for analytics)
        "steps_json": _truncate_audit_text(row.get("steps_json")),
        "errors_json": _truncate_audit_text(row.get("errors_json")),
    }


@router.get("/mission-control/patients/{patient_id}/pipeline-events")
async def get_patient_pipeline_events(
    patient_id: str,
    org_id: Optional[str] = Query(None),
    episode_id: Optional[str] = Query(
        None,
        description="When set, only runs for this episode's encounters or patient-wide runs",
    ),
    limit: int = Query(50, ge=1, le=200),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return recent PipelineRun AuditEvent rows for Mission Control audit trail."""
    pid = _normalise_mission_patient_id(patient_id)
    if not pid:
        raise HTTPException(status_code=400, detail="Invalid patient_id")

    eid = _normalise_mission_episode_id(episode_id)
    prefix, extra = _patient_pipeline_audit_prefix(scope, org_id)

    if eid:
        middle = (
            "WITH p "
            "OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare {episode_id: $episode_id}) "
            "OPTIONAL MATCH (ep)<-[:IS_PART_OF]-(enc:Encounter) "
            "WITH p, collect(DISTINCT toString(enc.id)) AS allowed "
        )
        episode_clause = (
            "AND (size(allowed) = 0 "
            "OR trim(coalesce(ae.encounter_id, '')) = '' "
            "OR ae.encounter_id IN allowed) "
        )
        extra = {**extra, "episode_id": eid}
    else:
        middle = "WITH p "
        episode_clause = ""

    full_q = (
        f"{prefix}"
        f"{middle}"
        "MATCH (ae:AuditEvent)-[:AUDIT_FOR]->(p) "
        "WHERE coalesce(ae.`type`, '') = 'PipelineRun' "
        f"{episode_clause}"
        "RETURN ae.id AS id, ae.`type` AS pipeline_kind, ae.status AS status, "
        "toString(ae.created_at) AS created_at, ae.encounter_id AS encounter_id, "
        "ae.run_id AS run_id, ae.event_type AS event_type, "
        "ae.plan_definition_id AS plan_definition_id, "
        "ae.step_count AS step_count, "
        "ae.total_duration_ms AS total_duration_ms, ae.entity_count AS entity_count, "
        "ae.error_count AS error_count, ae.first_error AS first_error, "
        "ae.llm_input_tokens AS llm_input_tokens, "
        "ae.llm_output_tokens AS llm_output_tokens, "
        "ae.llm_cached_tokens AS llm_cached_tokens, "
        "ae.llm_cost_usd AS llm_cost_usd, "
        "ae.extraction_prompt_name AS extraction_prompt_name, "
        "ae.extraction_prompt_version AS extraction_prompt_version, "
        "ae.extraction_prompt_hash AS extraction_prompt_hash, "
        "ae.extraction_provider AS extraction_provider, "
        "ae.extraction_model_tier AS extraction_model_tier, "
        "ae.steps AS steps_json, ae.errors AS errors_json "
        "ORDER BY ae.created_at DESC "
        "LIMIT $limit"
    )

    params: dict[str, Any] = {**extra, "patient_id": pid, "limit": limit}

    client = PatientGraphClient()
    try:
        rows = client.run(full_q, **params)
    finally:
        client.close()

    events = [_row_to_pipeline_event(r) for r in rows]
    return {"patient_id": pid, "episode_id": eid, "events": events}


def _row_to_manual_event(row: dict[str, Any]) -> dict[str, Any]:
    """Coerce a manual EpisodeManual* AuditEvent row into a JSON-safe
    dict for the audit trail tab. Mirrors _row_to_pipeline_event but
    surfaces the actor / before / after fields the curator dialogs
    write via write_episode_audit_event."""
    return {
        "id": row.get("id"),
        "event_type": row.get("event_type"),
        "subtype": row.get("subtype"),
        "created_at": row.get("created_at"),
        "actor_email": row.get("actor_email") or "",
        "actor_role": row.get("actor_role") or "",
        "episode_id": row.get("episode_id") or "",
        "patient_id": row.get("patient_id") or "",
        "notes": row.get("notes") or "",
        # before/after JSON blobs are written by
        # write_episode_audit_event for full traceability of every
        # property change. The UI only renders a short summary of
        # them so we truncate aggressively for safety.
        "before_json": _truncate_audit_text(row.get("before_json")),
        "after_json": _truncate_audit_text(row.get("after_json")),
    }


@router.get("/mission-control/patients/{patient_id}/manual-events")
async def get_patient_manual_events(
    patient_id: str,
    org_id: Optional[str] = Query(None),
    episode_id: Optional[str] = Query(
        None,
        description=(
            "When set, only manual events targeting this episode are "
            "returned (so each episode tab only shows its own audit "
            "trail). Patient-wide manual events (e.g. episode CREATE) "
            "are also returned so the create event of the in-focus "
            "episode is visible."
        ),
    ),
    limit: int = Query(50, ge=1, le=200),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return EpisodeManual* AuditEvent rows for the audit trail tab.

    Manual events are written by the EpisodeOfCare CRUD endpoints in
    services/analytics_api/app/routers/episode_crud.py via
    write_episode_audit_event. They carry the curator's email/role
    and a before/after property snapshot so QA / RA leads can
    reconstruct any human change to a pathway.

    DI-3A19BE12 (audit trail visibility), R-A737EE12 (no untracked
    manual mutation).
    """
    pid = _normalise_mission_patient_id(patient_id)
    if not pid:
        raise HTTPException(status_code=400, detail="Invalid patient_id")

    eid = _normalise_mission_episode_id(episode_id)
    prefix, extra = _patient_pipeline_audit_prefix(scope, org_id)

    # Filter on the EpisodeManual* family of event_type values
    # (Create / Update / Delete / Attach / Detach / Replace). Using a
    # STARTS WITH filter keeps the endpoint forward-compatible if we
    # add more verbs later.
    episode_clause = (
        "AND (ae.episode_id = $episode_id OR coalesce(ae.episode_id, '') = '') "
        if eid
        else ""
    )

    full_q = (
        f"{prefix}"
        "WITH p "
        "MATCH (ae:AuditEvent)-[:AUDIT_FOR]->(p) "
        "WHERE coalesce(ae.`type`, '') STARTS WITH 'EpisodeManual' "
        f"{episode_clause}"
        "RETURN ae.id AS id, ae.`type` AS event_type, ae.subtype AS subtype, "
        "toString(ae.created_at) AS created_at, "
        "ae.actor_email AS actor_email, ae.actor_role AS actor_role, "
        "ae.episode_id AS episode_id, ae.patient_id AS patient_id, "
        "ae.notes AS notes, "
        "ae.before_json AS before_json, ae.after_json AS after_json "
        "ORDER BY ae.created_at DESC "
        "LIMIT $limit"
    )

    params: dict[str, Any] = {**extra, "patient_id": pid, "limit": limit}
    if eid:
        params["episode_id"] = eid

    client = PatientGraphClient()
    try:
        rows = client.run(full_q, **params)
    finally:
        client.close()

    events = [_row_to_manual_event(r) for r in rows]
    return {"patient_id": pid, "episode_id": eid, "events": events}


@router.get("/mission-control/patients/{patient_id}/rebuild-status")
async def get_patient_rebuild_status(
    patient_id: str,
    org_id: Optional[str] = Query(None),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return live rebuild status plus queue/ETA estimates for Awaiting rebuild rows."""
    pid = _normalise_mission_patient_id(patient_id)
    if not pid:
        raise HTTPException(status_code=400, detail="Invalid patient_id")

    prefix, extra = _patient_pipeline_audit_prefix(scope, org_id)
    exists_q = f"{prefix} RETURN count(p) AS c LIMIT 1"
    client = PatientGraphClient()
    try:
        visible = client.run(exists_q, **{**extra, "patient_id": pid})
    finally:
        client.close()
    if not visible or int(visible[0].get("c") or 0) == 0:
        raise HTTPException(status_code=404, detail="Patient not found")

    status = get_rebuild_status(pid) or {}
    queue_depth = _pipeline_queue_depth()
    median_s, throughput_per_minute = _duration_and_throughput_estimate()

    queue_position_estimate: Optional[int] = None
    eta_seconds_estimate: Optional[int] = None
    state = str(status.get("status") or "idle")
    if state == "queued" and queue_depth is not None:
        queue_position_estimate = max(queue_depth - 1, 0)
    if state in {"queued", "running"} and median_s is not None:
        if (
            state == "queued"
            and queue_position_estimate is not None
            and throughput_per_minute
        ):
            wait_seconds = int((queue_position_estimate / throughput_per_minute) * 60.0)
            eta_seconds_estimate = max(wait_seconds + int(median_s), int(median_s))
        elif state == "running":
            eta_seconds_estimate = max(int(median_s), 1)

    return {
        "patient_id": pid,
        "run_id": status.get("run_id"),
        "status": state,
        "message": status.get("message"),
        "updated_at": status.get("updated_at"),
        "queued_jobs": status.get("queued_jobs"),
        "queue_depth": queue_depth,
        "queue_position_estimate": queue_position_estimate,
        "median_duration_seconds": median_s,
        "throughput_per_minute": throughput_per_minute,
        "eta_seconds_estimate": eta_seconds_estimate,
    }


@router.get("/mission-control/patients/{patient_id}/episodes")
async def get_patient_episodes(
    patient_id: str,
    org_id: Optional[str] = Query(None),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return every EpisodeOfCare attached to ``patient_id``.

    Mirrors the per-episode shape used by the cohort list endpoint
    (``_EPISODE_PROJECTION``) but applies NO cohort filters
    (lifecycle_bucket / pathway_filter / review_status / cancer_types
    / closure_reasons). Used by the Mission Control patient drawer so
    a manually-created in_review episode is visible to the curator
    immediately, even when the dashboard is filtered to a different
    bucket (DI-5E47FA5D, mitigates R-A737EE12).

    Same org-scope contract as get_patient_pipeline_events:
      - in-scope patient -> 200 with episodes (possibly empty)
      - out-of-scope or unknown patient -> 404
      - malformed patient_id -> 400
    """
    pid = _normalise_mission_patient_id(patient_id)
    if not pid:
        raise HTTPException(status_code=400, detail="Invalid patient_id")

    prefix, extra = _patient_pipeline_audit_prefix(scope, org_id)
    query = (
        f"{prefix}"
        "WITH p "
        "OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
        "WITH p, ep "
        "ORDER BY ep.referral_date DESC, ep.episode_id ASC "
        "WITH p, collect(DISTINCT ep) AS raw_episodes "
        "WITH p, [ep IN raw_episodes WHERE ep IS NOT NULL] AS episodes "
        f"RETURN [ep IN episodes | {_EPISODE_PROJECTION}] AS episodes, "
        "  p.id AS patient_id"
    )
    params: dict[str, Any] = {**extra, "patient_id": pid}

    client = PatientGraphClient()
    try:
        rows = client.run(query, **params)
    finally:
        client.close()

    if not rows:
        raise HTTPException(status_code=404, detail="Patient not found")

    row = rows[0]
    return {
        "patient_id": row.get("patient_id") or pid,
        "episodes": row.get("episodes") or [],
    }


@router.patch("/mission-control/episodes/{episode_id}/review")
async def patch_episode_review(
    episode_id: str,
    body: ReviewRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, str]:
    """Write audit tracking fields to an EpisodeOfCare node.

    Only sets reviewed_by, reviewed_at, audit_notes, audit_flag.
    Never modifies clinical coding data.
    """
    if not scope.email:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Clear BOTH the legacy ``needs_review`` and the canonical
    # ``needs_human_review`` flags when a curator signs off so the
    # two parallel fields cannot drift (DI-C4CEFA32). The v2 detector
    # reads needs_human_review; the legacy dashboards still read
    # needs_review; keeping both in lockstep until the legacy field
    # can be removed.
    q = (
        "MATCH (ep:EpisodeOfCare {episode_id: $episode_id}) "
        "SET ep.reviewed_by = $reviewed_by, "
        "    ep.reviewed_at = datetime(), "
        "    ep.audit_notes = $audit_notes, "
        "    ep.audit_flag = $audit_flag, "
        "    ep.needs_review = false, "
        "    ep.needs_human_review = false "
        "RETURN ep.episode_id AS episode_id"
    )

    client = PatientGraphClient()
    try:
        rows = client.run(
            q,
            episode_id=episode_id,
            reviewed_by=body.reviewed_by,
            audit_notes=body.audit_notes or "",
            audit_flag=body.audit_flag,
        )
    finally:
        client.close()

    if not rows:
        raise HTTPException(status_code=404, detail=f"Episode {episode_id!r} not found")

    return {"episode_id": episode_id, "status": "reviewed"}


# ---------------------------------------------------------------------------
# PATCH /mission-control/episodes/{episode_id}/reconcile
# ---------------------------------------------------------------------------


_RECONCILE_SNAPSHOT_QUERY = (
    "MATCH (ep:EpisodeOfCare {episode_id: $episode_id}) "
    "OPTIONAL MATCH (enc:Encounter)-[r:IS_PART_OF]->(ep) "
    "WHERE r.milestone_type IS NOT NULL "
    "WITH ep, collect(DISTINCT { "
    "  slot: r.milestone_type, "
    "  milestone_type: r.milestone_type, "
    "  encounter_id: toString(enc.id) "
    "}) AS slots "
    "RETURN ep.episode_id AS episode_id, ep.status AS status, "
    "  EXISTS { "
    "    MATCH (e2:Encounter)-[r2:IS_PART_OF]->(ep) "
    "    WHERE r2.milestone_type IN ['diagnosis', 'diagnosis_confirmed'] "
    "  } AS has_diagnosis_milestone, "
    "  coalesce(ep.letter_inferred_benign, false) AS letter_inferred_benign, "
    "  slots AS slots"
)


def _read_reconcile_snapshot(episode_id: str) -> Optional[EpisodeSnapshot]:
    """Read live state of an episode for the reconcile flow."""
    client = PatientGraphClient()
    try:
        rows = client.run(_RECONCILE_SNAPSHOT_QUERY, episode_id=episode_id)
    finally:
        client.close()
    if not rows:
        return None
    row = rows[0]
    return EpisodeSnapshot(
        episode_id=row["episode_id"],
        status=row.get("status"),
        has_diagnosis_milestone=bool(row.get("has_diagnosis_milestone", False)),
        letter_inferred_benign=bool(row.get("letter_inferred_benign", False)),
        slots=[
            {
                "slot": s.get("slot"),
                "milestone_type": s.get("milestone_type"),
                "encounter_id": s.get("encounter_id"),
            }
            for s in (row.get("slots") or [])
            if s and s.get("slot") is not None
        ],
    )


@router.patch("/mission-control/episodes/{episode_id}/reconcile")
async def patch_episode_reconcile(
    episode_id: str,
    body: ReconcileRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Apply reconcile actions and write a VerificationLock per slot.

    Refuses with HTTP 412 ``Precondition Failed`` when the proposed
    actions would silently move the episode into a different lifecycle
    bucket and the client did not explicitly opt in via
    ``confirm_bucket_flip=true``.
    """
    if not scope.email:
        raise HTTPException(status_code=401, detail="Authentication required")

    eid = _normalise_mission_episode_id(episode_id)
    if not eid:
        raise HTTPException(status_code=400, detail="Invalid episode_id")

    lock_client = PatientGraphClient()
    try:
        result = reconcile_episode(
            episode_id=eid,
            request=body,
            snapshot_reader=_read_reconcile_snapshot,
            lock_client=lock_client,
        )
    except EpisodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnknownSlotError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BucketFlipNotConfirmedError as exc:
        raise HTTPException(
            status_code=412,
            detail={
                "message": str(exc),
                "current_bucket": exc.flip.current_bucket.value,
                "proposed_bucket": exc.flip.proposed_bucket.value,
            },
        ) from exc
    finally:
        lock_client.close()

    return {
        "episode_id": result.episode_id,
        "bucket": result.bucket.value,
        "flipped": result.flip.flips,
        "current_bucket": result.flip.current_bucket.value,
        "proposed_bucket": result.flip.proposed_bucket.value,
        "locks": [
            {
                "slot": action.slot,
                "lock_id": lock.lock_id,
                "entity_type": lock.entity_type,
                "entity_id": lock.entity_id,
            }
            for action, lock in zip(body.actions, result.locks)
        ],
    }


# ---------------------------------------------------------------------------
# GET /mission-control/episodes/{episode_id}/locks
# ---------------------------------------------------------------------------


@router.get("/mission-control/episodes/{episode_id}/locks")
async def list_episode_locks(
    episode_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return every VerificationLock attached to an episode.

    The UI uses this to render lock chips on milestone nodes and
    encounter cards inside the Reconcile Pathway drawer.
    """
    if not scope.email:
        raise HTTPException(status_code=401, detail="Authentication required")

    eid = _normalise_mission_episode_id(episode_id)
    if not eid:
        raise HTTPException(status_code=400, detail="Invalid episode_id")

    from libs.locks import list_locks_for_episode

    client = PatientGraphClient()
    try:
        locks = list_locks_for_episode(client, episode_id=eid)
    finally:
        client.close()

    return {
        "episode_id": eid,
        "locks": [
            {
                "lock_id": lock.lock_id,
                "entity_type": lock.entity_type,
                "entity_id": lock.entity_id,
                "locked_by": lock.locked_by,
                "locked_by_role": lock.locked_by_role,
                "locked_at": lock.locked_at,
                "lock_reason": lock.lock_reason,
                "source": lock.source,
            }
            for lock in locks
        ],
    }
