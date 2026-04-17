"""NCDA Audit endpoints.

Provides retrospective audit data mirroring the 14 sections of the
National Cancer Diagnosis Audit (NCDA) report.

Multi-scope response: each section endpoint returns live data for up to three
comparison levels simultaneously:

  practice   -- the selected GP/organisation (org_id param)
  alliance   -- the CancerAlliance that GP belongs to (resolved automatically)
  england    -- all patients across the patient graph (no org filter)

When no org_id is provided (All Organisations mode), only 'practice' is
populated (and contains England-wide live data).

A static benchmark can be overlaid by passing benchmark_set_id, which reads
BenchmarkValue nodes from the Knowledge Graph.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from libs.analytics import (
    confirmed_cancer_where,
    suspected_cancer_referral_where,
)
from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.neo4j_client.client import PatientGraphClient

from ._audit_comorbidities import (  # noqa: F401 -- re-exported for main.py
    _ensure_registry,
    _q_comorbidities,
)
from ._audit_helpers import (
    _add_date_filters,
    _ENGLAND_BASE,
    _episode_base,
    _fetch_benchmark_metrics,
    _ORG_PATIENT_MATCH,
    _run_multi_scope,
)
from ._audit_intervals import (
    INFERRED_CANCER_DIAG_CASE,
    FP_DATE_EXPR,
    _q_intervals,
)
from ._audit_sections import (
    _q_avoidable_delays,
    _q_cancer_stage,
    _q_cancer_type,
    _q_consultations,
    _q_demographics,
    _q_investigations,
    _q_place,
    _q_referrals,
    _q_safety_netting,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


@router.get("/audit/summary")
def audit_summary(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    audit_year: Optional[str] = Query(default=None),
):
    """High-level summary metrics across all NCDA sections."""
    base, params = _episode_base(org_id, scope)
    base, params = _add_date_filters(base, params, date_from, date_to)
    if audit_year:
        params = {**params, "audit_year": audit_year}

    client = PatientGraphClient()
    try:
        rows = client.run(
            f"{base}"
            "AND ep.referral_date IS NOT NULL "
            "WITH p, ep "
            "WHERE EXISTS { "
            "  MATCH (:Encounter)-[rr:IS_PART_OF]->(ep) "
            "  WHERE rr.milestone_type = 'referral' "
            "} "
            "OPTIONAL MATCH (diag_enc:Encounter)-[dr:IS_PART_OF]->(ep) "
            "  WHERE dr.milestone_type IN "
            "['diagnosis', 'diagnosis_confirmed'] "
            "WITH p, ep, min(toString(diag_enc.date)) AS diag_date "
            f"WITH p, ep, diag_date, "
            f"{INFERRED_CANCER_DIAG_CASE} AS effective_diag_date, "
            f"{FP_DATE_EXPR} AS fp_date, "
            "  CASE "
            "    WHEN trim(coalesce(toString(ep.referral_date), '')) = '' "
            "      THEN NULL "
            "    ELSE date(toString(ep.referral_date)) "
            "  END AS referral_date_value, "
            "  CASE "
            "    WHEN trim(coalesce(toString(ep.first_presentation_date), '')) = '' "
            "      THEN NULL "
            "    ELSE date(toString(ep.first_presentation_date)) "
            "  END AS first_presentation_date_value, "
            "  (diag_date IS NULL AND ep.inferred_outcome = 'cancer' "
            "   AND ep.inferred_outcome_date IS NOT NULL) AS diag_is_inferred "
            "OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc2:Encounter) "
            "  WHERE enc2.date IS NOT NULL "
            "    AND ep.referral_date IS NOT NULL "
            "    AND coalesce(enc2.classification_content_type, "
            "'clinical') = 'clinical' "
            "    AND referral_date_value IS NOT NULL "
            "    AND enc2.date <= referral_date_value "
            "    AND enc2.date >= coalesce("
            "      first_presentation_date_value, "
            "      referral_date_value - duration('P365D')) "
            "WITH ep.status AS ep_status, "
            "     fp_date, "
            "     toString(ep.referral_date) AS ref_date, "
            "     ep.safety_netting_recorded AS sn, "
            "     effective_diag_date AS diag_date, "
            "     diag_is_inferred, "
            "     count(DISTINCT enc2) AS consultation_count "
            "RETURN ep_status, fp_date, ref_date, sn, "
            "diag_date, diag_is_inferred, consultation_count",
            **params,
        )

        # Canonical confirmed-cancer count -- single source of truth.
        # See DI-LEO-AI-134 / R-LEO-AI-092.
        confirmed_rows = client.run(
            f"{base}"
            f"AND {confirmed_cancer_where('ep')} "
            "RETURN count(DISTINCT ep) AS n",
            **params,
        )
        via_2ww_rows = client.run(
            f"{base}"
            f"AND {suspected_cancer_referral_where('ep')} "
            "RETURN count(DISTINCT ep) AS n",
            **params,
        )

        _CLOSED = {
            "closed",
            "completed",
            "merged",
            "excluded",
            "closed_benign",
            "closed_related",
            "closed_phantom",
            "stale_no_diagnosis",
            "stale_post_specialist",
        }

        def _safe_days(a: Any, b: Any) -> Optional[float]:
            try:
                from datetime import date as _date

                da = _date.fromisoformat(str(a)) if a else None
                db = _date.fromisoformat(str(b)) if b else None
                return (db - da).days if da and db else None
            except Exception:
                return None

        total = len(rows)
        active = sum(1 for r in rows if r.get("ep_status") not in _CLOSED)
        # Headline 'Confirmed Cancers' uses the NCDA canonical cohort:
        # completed episode + not letter-inferred-benign + has a
        # diagnosis-milestone encounter. A second field surfaces the
        # narrower '2WW-route' subset alongside.
        confirmed = (
            int((confirmed_rows[0] or {}).get("n") or 0) if confirmed_rows else 0
        )
        confirmed_via_2ww = (
            int((via_2ww_rows[0] or {}).get("n") or 0) if via_2ww_rows else 0
        )
        confirmed_via_2ww_pct = (
            round(confirmed_via_2ww * 100.0 / confirmed, 1) if confirmed else None
        )

        pci_vals = sorted(
            v
            for r in rows
            if (v := _safe_days(r.get("fp_date"), r.get("ref_date"))) is not None
        )
        di_vals = sorted(
            v
            for r in rows
            if (v := _safe_days(r.get("fp_date"), r.get("diag_date"))) is not None
        )
        consult_vals = [
            r["consultation_count"]
            for r in rows
            if r.get("consultation_count") is not None
        ]
        sn_count = sum(1 for r in rows if r.get("sn") is True)

        def _median(vals: list) -> Optional[float]:
            n = len(vals)
            if not n:
                return None
            mid = n // 2
            return float(vals[mid]) if n % 2 else (vals[mid - 1] + vals[mid]) / 2.0

        return {
            "total_episodes": total,
            "active_episodes": active,
            "confirmed_cancers": confirmed,
            "confirmed_cancers_via_2ww": confirmed_via_2ww,
            "confirmed_cancers_via_2ww_pct": confirmed_via_2ww_pct,
            "median_pci_days": (round(_median(pci_vals), 1) if pci_vals else None),
            "median_di_days": (round(_median(di_vals), 1) if di_vals else None),
            "avg_consultations": (
                round(sum(consult_vals) / len(consult_vals), 1)
                if consult_vals
                else None
            ),
            "safety_netting_pct": (
                round(sn_count * 100.0 / total, 1) if total else None
            ),
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Section endpoints -- all return the multi-scope envelope
# ---------------------------------------------------------------------------


@router.get("/audit/cancer-type")
def audit_cancer_type(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    benchmark_set_id: Optional[str] = Query(default=None),
):
    """Distribution of cancer types -- multi-scope live data + optional benchmark."""
    client = PatientGraphClient()
    try:
        return _run_multi_scope(
            _q_cancer_type,
            org_id,
            scope,
            date_from,
            date_to,
            benchmark_set_id,
            "condition_type",
            client,
        )
    finally:
        client.close()


@router.get("/audit/cancer-stage")
def audit_cancer_stage(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    benchmark_set_id: Optional[str] = Query(default=None),
):
    """Early vs late stage at diagnosis."""
    client = PatientGraphClient()
    try:
        return _run_multi_scope(
            _q_cancer_stage,
            org_id,
            scope,
            date_from,
            date_to,
            benchmark_set_id,
            "cancer_stage",
            client,
        )
    finally:
        client.close()


@router.get("/audit/demographics")
def audit_demographics(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    benchmark_set_id: Optional[str] = Query(default=None),
):
    """Sex, age bands, and ethnicity breakdown."""
    client = PatientGraphClient()
    try:
        return _run_multi_scope(
            _q_demographics,
            org_id,
            scope,
            date_from,
            date_to,
            benchmark_set_id,
            "demographics",
            client,
        )
    finally:
        client.close()


@router.get("/audit/place-of-presentation")
def audit_place_of_presentation(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    benchmark_set_id: Optional[str] = Query(default=None),
):
    """Where patients first presented with cancer-related symptoms."""
    client = PatientGraphClient()
    try:
        return _run_multi_scope(
            _q_place,
            org_id,
            scope,
            date_from,
            date_to,
            benchmark_set_id,
            "place_of_presentation",
            client,
        )
    finally:
        client.close()


@router.get("/audit/consultations")
def audit_consultations(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    benchmark_set_id: Optional[str] = Query(default=None),
):
    """Consultations before referral: <3 vs 3+, median and IQR."""
    client = PatientGraphClient()
    try:
        return _run_multi_scope(
            _q_consultations,
            org_id,
            scope,
            date_from,
            date_to,
            benchmark_set_id,
            "consultations",
            client,
        )
    finally:
        client.close()


@router.get("/audit/investigations")
def audit_investigations(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    benchmark_set_id: Optional[str] = Query(default=None),
):
    """Primary care investigations ordered prior to referral."""
    client = PatientGraphClient()
    try:
        return _run_multi_scope(
            _q_investigations,
            org_id,
            scope,
            date_from,
            date_to,
            benchmark_set_id,
            "investigations",
            client,
        )
    finally:
        client.close()


@router.get("/audit/referrals")
def audit_referrals(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    benchmark_set_id: Optional[str] = Query(default=None),
):
    """Referral routes (TWW, Urgent, MDC/RDC, Emergency, etc.)."""
    client = PatientGraphClient()
    try:
        return _run_multi_scope(
            _q_referrals,
            org_id,
            scope,
            date_from,
            date_to,
            benchmark_set_id,
            "referrals",
            client,
        )
    finally:
        client.close()


@router.get("/audit/intervals")
def audit_intervals(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    benchmark_set_id: Optional[str] = Query(default=None),
):
    """Primary care interval (PCI) and diagnostic interval (DI).

    Returns aggregate stats plus individual patient data points (capped at 500)
    for strip/dot plot visualisation.  Multi-scope: only aggregates for
    alliance/england (patient-level points are practice only).
    """
    client = PatientGraphClient()
    try:
        result = _run_multi_scope(
            _q_intervals,
            org_id,
            scope,
            date_from,
            date_to,
            benchmark_set_id,
            "primary_care_interval",
            client,
        )
        if benchmark_set_id and result.get("benchmark"):
            di_bm = _fetch_benchmark_metrics(benchmark_set_id, "diagnostic_interval")
            if di_bm and di_bm.get("metrics"):
                result["benchmark"]["metrics"].update(di_bm["metrics"])

        for scope_key in ("alliance_live", "england_live"):
            scope_data = result["scopes"].get(scope_key)
            if scope_data and isinstance(scope_data, dict):
                scope_data.pop("patients", None)

        return result
    finally:
        client.close()


@router.get("/audit/safety-netting")
def audit_safety_netting(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    benchmark_set_id: Optional[str] = Query(default=None),
):
    """Safety netting documentation rates."""
    client = PatientGraphClient()
    try:
        return _run_multi_scope(
            _q_safety_netting,
            org_id,
            scope,
            date_from,
            date_to,
            benchmark_set_id,
            "safety_netting",
            client,
        )
    finally:
        client.close()


@router.get("/audit/avoidable-delays")
def audit_avoidable_delays(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    benchmark_set_id: Optional[str] = Query(default=None),
):
    """GP-assessed avoidable delay rates and phase breakdown."""
    client = PatientGraphClient()
    try:
        return _run_multi_scope(
            _q_avoidable_delays,
            org_id,
            scope,
            date_from,
            date_to,
            benchmark_set_id,
            "avoidable_delays",
            client,
        )
    finally:
        client.close()


@router.get("/audit/comorbidities")
def audit_comorbidities(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    benchmark_set_id: Optional[str] = Query(default=None),
):
    """Comorbidity prevalence from HAS_DISEASE relationships.

    Concept list is read dynamically from the cancer_audit/comorbidities
    subdomain.  Each top-level concept is expanded via the SNOMED IS_A
    hierarchy so all clinical variants are captured and results are grouped
    back to the top-level category.
    """
    client = PatientGraphClient()
    try:
        return _run_multi_scope(
            _q_comorbidities,
            org_id,
            scope,
            date_from,
            date_to,
            benchmark_set_id,
            "comorbidities",
            client,
        )
    finally:
        client.close()
