"""Mission Control endpoints for Clinical Audit case management.

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
from libs.neo4j_client.client import PatientGraphClient
from libs.redis_client.rebuild_status import get_rebuild_status
from services.analytics_api.app.routers._audit_helpers import (
    _add_date_filters,
    _episode_base,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Status groupings
# ---------------------------------------------------------------------------

_CLOSURE_STATUSES = [
    "closed_benign",
    "stale_no_diagnosis",
    "stale_post_specialist",
    "closed_related",
]
_ALWAYS_EXCLUDE = ["merged", "closed_phantom"]

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
) -> tuple[str, dict]:
    """Build full filtered match clause from all filter params."""
    base, params = _episode_base(org_id, scope)
    base, params = _add_date_filters(base, params, date_from, date_to)
    base, params = _apply_pathway_filter(base, params, pathway_filter)
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
        "  [ep IN episodes | { "
        "    episode_id: ep.episode_id, "
        "    cancer_type: ep.cancer_type, "
        "    condition_type: ep.condition_type, "
        "    status: ep.status, "
        "    cancer_stage: ep.cancer_stage, "
        "    referral_date: ep.referral_date, "
        "    end_date: ep.end_date, "
        "    specialist_visit_date: ep.specialist_visit_date, "
        "    diagnostic_interval_days: ep.diagnostic_interval_days, "
        "    primary_care_interval_days: ep.primary_care_interval_days, "
        "    inferred_outcome: ep.inferred_outcome, "
        "    auto_close_reason: ep.auto_close_reason, "
        "    reviewed_by: ep.reviewed_by, "
        "    reviewed_at: toString(ep.reviewed_at), "
        "    audit_notes: ep.audit_notes, "
        "    audit_flag: coalesce(ep.audit_flag, false), "
        "    linked_encounter_ids: [ "
        "      (ep)<-[:IS_PART_OF]-(enc_all:Encounter) "
        "      | toString(enc_all.id) "
        "    ], "
        "    milestones: [ "
        "      (ep)<-[r:IS_PART_OF]-(enc:Encounter) "
        "      WHERE r.milestone_type IS NOT NULL "
        "      | { "
        "          milestone_type: r.milestone_type, "
        "          encounter_id: toString(enc.id), "
        "          date: toString(enc.date) "
        "        } "
        "    ] "
        "  }] AS episodes "
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
        scope_match = (
            "MATCH (p:Patient) "
            f"WHERE {ORG_PATIENT_FILTER} "
        )
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
async def get_mission_control_patients(
    org_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    pathway_filter: str = Query("all", pattern="^(confirmed|closures|all)$"),
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
    )

    skip = (page - 1) * page_size
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
        if pid and total == 0:
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
async def get_mission_control_kpis(
    org_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    pathway_filter: str = Query("all", pattern="^(confirmed|closures|all)$"),
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
    )

    q, qparams = _kpis_cypher(base, params)
    cohort_q, cohort_params = _cohort_denominator_cypher(
        org_id, scope, date_from, date_to
    )
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
        "excluded_outside_window": int(
            cohort.get("excluded_outside_window", 0) or 0
        ),
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

    q = (
        "MATCH (ep:EpisodeOfCare {episode_id: $episode_id}) "
        "SET ep.reviewed_by = $reviewed_by, "
        "    ep.reviewed_at = datetime(), "
        "    ep.audit_notes = $audit_notes, "
        "    ep.audit_flag = $audit_flag "
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
