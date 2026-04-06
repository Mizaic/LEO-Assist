"""NCDA Audit endpoints.

Provides retrospective audit data mirroring the 14 sections of the
National Cancer Diagnosis Audit (NCDA) report.

Multi-scope response: each section endpoint returns live data for up to three
comparison levels simultaneously:

  practice   – the selected GP/organisation (org_id param)
  alliance   – the CancerAlliance that GP belongs to (resolved automatically)
  england    – all patients across the patient graph (no org filter)

When no org_id is provided (All Organisations mode), only 'practice' is
populated (and contains England-wide live data).

A static benchmark can be overlaid by passing benchmark_set_id, which reads
BenchmarkValue nodes from the Knowledge Graph.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from libs.auth.org_scope import CallerScope, ORG_PATIENT_FILTER, get_caller_scope
from libs.domain_config.registry import DomainRegistry
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient

router = APIRouter()

# ---------------------------------------------------------------------------
# Match templates
# ---------------------------------------------------------------------------

_ORG_PATIENT_MATCH = (
    "MATCH (_scope:Organization {id: $org}) "
    "MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
    "WHERE (gp.id = $org) OR (gp)-[:COMMISSIONED_BY]->(_scope) "
    "   OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(_scope) "
    "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
)

_ENGLAND_BASE = "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _episode_base(org_id: Optional[str], scope: CallerScope) -> tuple[str, dict]:
    """Return (match_clause, params) for the practice/org scope."""
    effective_org = org_id if scope.is_admin else (org_id or scope.primary_org_id)
    if effective_org:
        return _ORG_PATIENT_MATCH, {"org": effective_org}
    if scope.is_admin:
        return _ENGLAND_BASE, {}
    return (
        "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
        f"WHERE {ORG_PATIENT_FILTER} ",
        scope.to_query_params(),
    )


def _add_date_filters(
    base: str, params: dict, date_from: Optional[str], date_to: Optional[str]
) -> tuple[str, dict]:
    """Append optional referral_date range filters."""
    clauses: list[str] = []
    if date_from:
        clauses.append("ep.referral_date >= $date_from")
        params = {**params, "date_from": date_from}
    if date_to:
        clauses.append("ep.referral_date <= $date_to")
        params = {**params, "date_to": date_to}
    if clauses:
        connector = "AND " if ("WHERE " in base) else "WHERE "
        base = base.rstrip() + f" {connector}" + " AND ".join(clauses) + " "
    return base, params


def _resolve_alliance_id(org_id: str, client: PatientGraphClient) -> Optional[str]:
    """Resolve the CancerAlliance parent organisation id for a given GP."""
    rows = client.run(
        "MATCH (gp:Organization {id: $org}) "
        "OPTIONAL MATCH (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(ca:CancerAlliance) "
        "RETURN ca.id AS alliance_id",
        org=org_id,
    )
    return rows[0].get("alliance_id") if rows else None


def _resolve_org_ods_code(org_id: str, client: PatientGraphClient) -> Optional[str]:
    """Resolve the ODS code for a given org_id (tries ods_code property first, then id)."""
    rows = client.run(
        "MATCH (o:Organization {id: $org_id}) RETURN coalesce(o.ods_code, o.id) AS ods_code",
        org_id=org_id,
    )
    return rows[0]["ods_code"] if rows else None


def _fetch_benchmark_metrics(
    set_id: str,
    category: str,
    org_id: Optional[str] = None,
    org_ods_code: Optional[str] = None,
    alliance_id: Optional[str] = None,
) -> Optional[dict]:
    """Fetch all BenchmarkValues for a category from the Knowledge Graph.

    Returns {set_id, set_name, metrics: {metric_id: {national, alliance, practice}}}
    or None if the set is not found or has no values for this category.

    When org_id/org_ods_code are provided the practice-level benchmark is resolved:
      - primary match: BenchmarkValue.scope_id == ods_code (canonical ODS match)
      - fallback: BenchmarkValue.scope_type == 'gp_practice' nearest name match
    When alliance_id is provided the cancer_alliance row for that id is mapped.
    """
    kg = KnowledgeGraphClient()
    try:
        set_rows = kg.run(
            "MATCH (s:BenchmarkSet {id: $set_id}) RETURN s.name AS set_name",
            set_id=set_id,
        )
        set_name = set_rows[0]["set_name"] if set_rows else set_id

        rows = kg.run(
            "MATCH (v:BenchmarkValue) "
            "WHERE v.audit_id = $set_id AND v.category = $category "
            "RETURN v.metric_id AS metric_id, v.scope_type AS scope_type, "
            "v.scope_id AS scope_id, v.scope_name AS scope_name, v.value AS value",
            set_id=set_id,
            category=category,
        )
        if not rows:
            return None

        # Index rows by (scope_type, scope_id)
        metrics: dict[str, dict] = {}
        practice_rows: dict[str, list] = {}  # metric_id -> list of gp_practice rows
        alliance_rows: dict[str, list] = {}  # metric_id -> list of cancer_alliance rows

        for r in rows:
            mid = r["metric_id"]
            if mid not in metrics:
                metrics[mid] = {"national": None, "alliance": None, "practice": None}
            st = r.get("scope_type", "")
            if st == "national":
                metrics[mid]["national"] = r["value"]
            elif st == "cancer_alliance":
                alliance_rows.setdefault(mid, []).append(r)
            elif st == "gp_practice":
                practice_rows.setdefault(mid, []).append(r)

        # Resolve alliance benchmark
        for mid, arows in alliance_rows.items():
            # 1. Exact match on scope_id (graph org id)
            matched = next((a for a in arows if a.get("scope_id") == alliance_id), None) if alliance_id else None
            if matched is None:
                # 2. Fallback: use the only/first cancer_alliance row in the set
                #    This handles the common case where the benchmark entity id differs from graph org id
                matched = arows[0] if arows else None
            if matched:
                metrics[mid]["alliance"] = matched["value"]

        # Resolve practice benchmark
        if practice_rows and (org_ods_code or org_id):
            ods = org_ods_code or org_id
            for mid, prows in practice_rows.items():
                # ODS-first exact match
                matched = next((pr for pr in prows if pr.get("scope_id") == ods), None)
                if matched is None:
                    # Fallback: normalised name contains org_id
                    norm_id = (org_id or "").lower().replace(" ", "").replace("-", "")
                    matched = next(
                        (
                            pr for pr in prows
                            if norm_id and norm_id in (pr.get("scope_name") or "").lower().replace(" ", "").replace("-", "")
                        ),
                        None,
                    )
                if matched:
                    metrics[mid]["practice"] = matched["value"]

        return {"set_id": set_id, "set_name": set_name, "metrics": metrics}
    finally:
        kg.close()


def _make_response(
    practice: Any,
    alliance: Any,
    england: Any,
    benchmark: Optional[dict],
) -> dict:
    """Wrap multi-scope results into the standard audit response envelope."""
    return {
        "scopes": {
            "practice": practice,
            "alliance_live": alliance,
            "england_live": england,
        },
        "benchmark": benchmark,
    }


# ---------------------------------------------------------------------------
# Per-section query helpers
# Each takes (base, params, client) and returns the section payload.
# ---------------------------------------------------------------------------


def _q_cancer_type(base: str, params: dict, client: PatientGraphClient) -> list:
    rows = client.run(
        f"{base}"
        "OPTIONAL MATCH (diag_enc:Encounter)-[dr:IS_PART_OF]->(ep) "
        "  WHERE dr.milestone_type IN ['diagnosis', 'diagnosis_confirmed'] "
        "WITH ep, count(diag_enc) AS diag_events "
        "WHERE coalesce(ep.condition_type, ep.cancer_type) IS NOT NULL "
        "  AND (diag_events > 0 OR coalesce(ep.status, '') IN ['confirmed','completed','closed']) "
        "RETURN coalesce(ep.condition_type, ep.cancer_type) AS cancer_type, count(DISTINCT ep) AS n "
        "ORDER BY n DESC",
        **params,
    )
    total = sum(r["n"] for r in rows) or 1
    return [{"cancer_type": r["cancer_type"], "n": r["n"], "pct": round(r["n"] * 100.0 / total, 1)} for r in rows]


def _q_cancer_stage(base: str, params: dict, client: PatientGraphClient) -> list:
    rows = client.run(
        f"{base}"
        "WHERE ep.cancer_stage IS NOT NULL "
        "WITH ep, "
        "  CASE WHEN ep.cancer_stage IN ['0','1','2','I','II'] THEN 'early' "
        "       WHEN ep.cancer_stage IN ['3','4','III','IV'] THEN 'late' "
        "       ELSE 'unknown' END AS stage_group "
        "RETURN stage_group, count(ep) AS n "
        "ORDER BY stage_group",
        **params,
    )
    total = sum(r["n"] for r in rows) or 1
    return [{"stage_group": r["stage_group"], "n": r["n"], "pct": round(r["n"] * 100.0 / total, 1)} for r in rows]


def _q_demographics(base: str, params: dict, client: PatientGraphClient) -> dict:
    sex_rows = client.run(
        f"{base}"
        "WHERE p.gender IS NOT NULL "
        "RETURN p.gender AS gender, count(DISTINCT p) AS n ORDER BY n DESC",
        **params,
    )
    age_rows = client.run(
        f"{base}"
        "WHERE p.birthDate IS NOT NULL AND ep.referral_date IS NOT NULL "
        "WITH p, ep, "
        "  duration.inDays(date(p.birthDate), date(toString(ep.referral_date))).days / 365 AS age_at_referral "
        "WITH age_at_referral, "
        "  CASE WHEN age_at_referral < 25 THEN '0-24' "
        "       WHEN age_at_referral < 50 THEN '25-49' "
        "       WHEN age_at_referral < 65 THEN '50-64' "
        "       WHEN age_at_referral < 75 THEN '65-74' "
        "       WHEN age_at_referral < 85 THEN '75-84' "
        "       ELSE '85+' END AS age_band "
        "RETURN age_band, count(*) AS n ORDER BY age_band",
        **params,
    )
    age_vals_rows = client.run(
        f"{base}"
        "WHERE p.birthDate IS NOT NULL AND ep.referral_date IS NOT NULL "
        "WITH duration.inDays(date(p.birthDate), date(toString(ep.referral_date))).days / 365 AS age "
        "RETURN age ORDER BY age",
        **params,
    )
    eth_rows = client.run(
        f"{base}"
        "WHERE p.ethnicity IS NOT NULL "
        "RETURN p.ethnicity AS ethnicity, count(DISTINCT p) AS n ORDER BY n DESC",
        **params,
    )
    ts = sum(r["n"] for r in sex_rows) or 1
    ta = sum(r["n"] for r in age_rows) or 1
    te = sum(r["n"] for r in eth_rows) or 1
    age_vals = sorted([r["age"] for r in age_vals_rows if r.get("age") is not None])
    n_age = len(age_vals)
    median_age = round(
        (age_vals[n_age // 2] if n_age % 2 else (age_vals[n_age // 2 - 1] + age_vals[n_age // 2]) / 2), 1
    ) if age_vals else None
    return {
        "sex": [{"gender": r["gender"], "n": r["n"], "pct": round(r["n"] * 100.0 / ts, 1)} for r in sex_rows],
        "age_bands": [{"age_band": r["age_band"], "n": r["n"], "pct": round(r["n"] * 100.0 / ta, 1)} for r in age_rows],
        "median_age": median_age,
        "ethnicity": [{"ethnicity": r["ethnicity"], "n": r["n"], "pct": round(r["n"] * 100.0 / te, 1)} for r in eth_rows],
    }


def _q_place(base: str, params: dict, client: PatientGraphClient) -> list:
    rows = client.run(
        f"{base}"
        "RETURN coalesce(ep.place_of_presentation, 'Not recorded') AS place, count(ep) AS n "
        "ORDER BY n DESC",
        **params,
    )
    total = sum(r["n"] for r in rows) or 1
    return [{"place": r["place"], "n": r["n"], "pct": round(r["n"] * 100.0 / total, 1)} for r in rows]


def _q_consultations(base: str, params: dict, client: PatientGraphClient) -> dict:
    rows = client.run(
        f"{base}"
        "OPTIONAL MATCH (enc:Encounter)-[:IS_PART_OF]->(ep) "
        "WITH ep, count(enc) AS consult_count "
        "RETURN "
        "  sum(CASE WHEN consult_count < 3 THEN 1 ELSE 0 END) AS fewer_than_3, "
        "  sum(CASE WHEN consult_count >= 3 THEN 1 ELSE 0 END) AS three_or_more, "
        "  count(ep) AS total_episodes, "
        "  avg(consult_count) AS avg_consultations",
        **params,
    )
    per_ep = client.run(
        f"{base}"
        "OPTIONAL MATCH (enc:Encounter)-[:IS_PART_OF]->(ep) "
        "WITH ep, count(enc) AS consult_count "
        "RETURN consult_count ORDER BY consult_count",
        **params,
    )
    counts = sorted([r["consult_count"] for r in per_ep if r.get("consult_count") is not None])
    n = len(counts)
    median_val = counts[n // 2] if n % 2 else ((counts[n // 2 - 1] + counts[n // 2]) / 2) if n else None
    iqr_low = counts[n // 4] if n else None
    iqr_high = counts[3 * n // 4] if n else None

    s = rows[0] if rows else {}
    total = s.get("total_episodes") or 1
    fewer = s.get("fewer_than_3") or 0
    three_plus = s.get("three_or_more") or 0
    return {
        "fewer_than_3_pct": round(fewer * 100.0 / total, 1),
        "three_or_more_pct": round(three_plus * 100.0 / total, 1),
        "fewer_than_3_n": fewer,
        "three_or_more_n": three_plus,
        "total_episodes": total,
        "median_consultations": median_val,
        "iqr_low": iqr_low,
        "iqr_high": iqr_high,
    }


def _q_investigations(base: str, params: dict, client: PatientGraphClient) -> dict:
    summary_rows = client.run(
        f"{base}"
        "OPTIONAL MATCH (enc:Encounter)-[:IS_PART_OF]->(ep) "
        "  WHERE enc.encounter_type IN ['investigation','blood_test','imaging','urinalysis','biopsy','endoscopy','symptomatic_fit','other_investigation'] "
        "WITH ep, count(enc) AS inv_count "
        "RETURN "
        "  count(ep) AS total_episodes, "
        "  sum(CASE WHEN inv_count > 0 THEN 1 ELSE 0 END) AS has_investigation, "
        "  sum(CASE WHEN inv_count = 0 THEN 1 ELSE 0 END) AS no_investigation",
        **params,
    )
    type_rows = client.run(
        f"{base}"
        "MATCH (enc:Encounter)-[:IS_PART_OF]->(ep) "
        "  WHERE enc.encounter_type IN ['investigation','blood_test','imaging','urinalysis','biopsy','endoscopy','symptomatic_fit','other_investigation'] "
        "RETURN enc.encounter_type AS investigation_type, count(DISTINCT ep.episode_id) AS n "
        "ORDER BY n DESC",
        **params,
    )
    s = summary_rows[0] if summary_rows else {}
    total = s.get("total_episodes") or 1
    has_inv = s.get("has_investigation") or 0
    inv_total = sum(r["n"] for r in type_rows) or 1
    return {
        "has_investigation_pct": round(has_inv * 100.0 / total, 1),
        "no_investigation_pct": round((s.get("no_investigation") or 0) * 100.0 / total, 1),
        "total_episodes": total,
        "types": [
            {"type": r["investigation_type"], "n": r["n"], "pct": round(r["n"] * 100.0 / inv_total, 1)}
            for r in type_rows
        ],
    }


def _q_referrals(base: str, params: dict, client: PatientGraphClient) -> list:
    rows = client.run(
        f"{base}"
        "RETURN coalesce(ep.referral_route, 'Not recorded') AS referral_route, count(ep) AS n "
        "ORDER BY n DESC",
        **params,
    )
    total = sum(r["n"] for r in rows) or 1
    return [{"referral_route": r["referral_route"], "n": r["n"], "pct": round(r["n"] * 100.0 / total, 1)} for r in rows]


def _q_intervals(base: str, params: dict, client: PatientGraphClient) -> dict:
    agg = client.run(
        f"{base}"
        "WHERE ep.first_presentation_date IS NOT NULL "
        "OPTIONAL MATCH (diag_enc:Encounter)-[dr:IS_PART_OF]->(ep) "
        "  WHERE dr.milestone_type IN ['diagnosis', 'diagnosis_confirmed'] "
        "WITH ep, min(toString(diag_enc.date)) AS diag_date "
        "RETURN "
        "  sum(CASE WHEN ep.referral_date IS NOT NULL THEN 1 ELSE 0 END) AS pci_n, "
        "  avg(CASE WHEN ep.referral_date IS NOT NULL "
        "      THEN duration.inDays(date(ep.first_presentation_date), date(toString(ep.referral_date))).days "
        "      ELSE null END) AS mean_pci, "
        "  sum(CASE WHEN diag_date IS NOT NULL THEN 1 ELSE 0 END) AS di_n, "
        "  avg(CASE WHEN diag_date IS NOT NULL "
        "      THEN duration.inDays(date(ep.first_presentation_date), date(diag_date)).days "
        "      ELSE null END) AS mean_di",
        **params,
    )
    pts = client.run(
        f"{base}"
        "WHERE ep.first_presentation_date IS NOT NULL "
        "OPTIONAL MATCH (diag_enc:Encounter)-[dr:IS_PART_OF]->(ep) "
        "  WHERE dr.milestone_type IN ['diagnosis', 'diagnosis_confirmed'] "
        "WITH ep, min(toString(diag_enc.date)) AS diag_date "
        "RETURN "
        "  ep.episode_id AS episode_id, ep.condition_type AS cancer_type, "
        "  CASE WHEN ep.referral_date IS NOT NULL "
        "       THEN duration.inDays(date(ep.first_presentation_date), date(toString(ep.referral_date))).days "
        "       ELSE null END AS pci_days, "
        "  CASE WHEN diag_date IS NOT NULL "
        "       THEN duration.inDays(date(ep.first_presentation_date), date(diag_date)).days "
        "       ELSE null END AS di_days "
        "ORDER BY ep.referral_date LIMIT 500",
        **params,
    )

    def _median(vals: list) -> Optional[float]:
        if not vals:
            return None
        n = len(vals)
        return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2

    def _iqr(vals: list) -> tuple[Optional[float], Optional[float]]:
        if not vals:
            return None, None
        n = len(vals)
        return vals[n // 4], vals[3 * n // 4]

    pci_vals = sorted([r["pci_days"] for r in pts if r.get("pci_days") is not None])
    di_vals = sorted([r["di_days"] for r in pts if r.get("di_days") is not None])
    pci_q1, pci_q3 = _iqr(pci_vals)
    di_q1, di_q3 = _iqr(di_vals)
    s = agg[0] if agg else {}

    return {
        "pci": {"n": s.get("pci_n"), "mean": s.get("mean_pci"), "median": _median(pci_vals), "q1": pci_q1, "q3": pci_q3},
        "di": {"n": s.get("di_n"), "mean": s.get("mean_di"), "median": _median(di_vals), "q1": di_q1, "q3": di_q3},
        "patients": [
            {"episode_id": r["episode_id"], "cancer_type": r.get("cancer_type"),
             "pci_days": r.get("pci_days"), "di_days": r.get("di_days")}
            for r in pts
        ],
    }


def _q_safety_netting(base: str, params: dict, client: PatientGraphClient) -> dict:
    rows = client.run(
        f"{base}"
        "RETURN "
        "  count(ep) AS total_episodes, "
        "  sum(CASE WHEN ep.safety_netting_recorded = true THEN 1 ELSE 0 END) AS recorded",
        **params,
    )
    s = rows[0] if rows else {}
    total = s.get("total_episodes") or 1
    recorded = s.get("recorded") or 0
    return {
        "recorded_pct": round(recorded * 100.0 / total, 1),
        "not_recorded_pct": round((total - recorded) * 100.0 / total, 1),
        "recorded_n": recorded,
        "total_episodes": total,
    }


def _q_avoidable_delays(base: str, params: dict, client: PatientGraphClient) -> dict:
    rows = client.run(
        f"{base}"
        "RETURN "
        "  count(ep) AS total_episodes, "
        "  sum(CASE WHEN ep.avoidable_delay = true THEN 1 ELSE 0 END) AS has_delay, "
        "  sum(CASE WHEN ep.avoidable_delay_phase = 'before_presentation' THEN 1 ELSE 0 END) AS before_pres, "
        "  sum(CASE WHEN ep.avoidable_delay_phase = 'pres_to_referral' THEN 1 ELSE 0 END) AS pres_to_ref, "
        "  sum(CASE WHEN ep.avoidable_delay_phase = 'after_referral' THEN 1 ELSE 0 END) AS after_ref",
        **params,
    )
    s = rows[0] if rows else {}
    total = s.get("total_episodes") or 1
    delay_total = s.get("has_delay") or 1
    has_delay = s.get("has_delay") or 0
    return {
        "avoidable_delay_pct": round(has_delay * 100.0 / total, 1),
        "avoidable_delay_n": has_delay,
        "total_episodes": total,
        "delay_before_presentation_pct": round((s.get("before_pres") or 0) * 100.0 / delay_total, 1),
        "delay_pres_to_referral_pct": round((s.get("pres_to_ref") or 0) * 100.0 / delay_total, 1),
        "delay_after_referral_pct": round((s.get("after_ref") or 0) * 100.0 / delay_total, 1),
    }


# ---------------------------------------------------------------------------
# Multi-scope runner
# ---------------------------------------------------------------------------


def _run_multi_scope(
    query_fn,
    org_id: Optional[str],
    scope: CallerScope,
    date_from: Optional[str],
    date_to: Optional[str],
    benchmark_set_id: Optional[str],
    benchmark_category: str,
    client: PatientGraphClient,
) -> dict:
    """Run a section query across practice / alliance / england scopes."""
    practice_base, practice_params = _episode_base(org_id, scope)
    practice_base, practice_params = _add_date_filters(practice_base, practice_params, date_from, date_to)
    practice_data = query_fn(practice_base, practice_params, client)

    alliance_data = None
    england_data = None
    alliance_id: Optional[str] = None
    org_ods_code: Optional[str] = None

    effective_org = org_id if scope.is_admin else (org_id or scope.primary_org_id)
    if effective_org:
        alliance_id = _resolve_alliance_id(effective_org, client)
        org_ods_code = _resolve_org_ods_code(effective_org, client)
        if alliance_id:
            a_base, a_params = _ORG_PATIENT_MATCH, {"org": alliance_id}
            a_base, a_params = _add_date_filters(a_base, a_params, date_from, date_to)
            try:
                alliance_data = query_fn(a_base, a_params, client)
            except Exception:
                alliance_data = None

        e_base, e_params = _ENGLAND_BASE, {}
        e_base, e_params = _add_date_filters(e_base, e_params, date_from, date_to)
        try:
            england_data = query_fn(e_base, e_params, client)
        except Exception:
            england_data = None

    benchmark = None
    if benchmark_set_id:
        try:
            benchmark = _fetch_benchmark_metrics(
                benchmark_set_id,
                benchmark_category,
                org_id=effective_org,
                org_ods_code=org_ods_code,
                alliance_id=alliance_id,
            )
        except Exception:
            benchmark = None

    return _make_response(practice_data, alliance_data, england_data, benchmark)


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
            "OPTIONAL MATCH (diag_enc:Encounter)-[dr:IS_PART_OF]->(ep) "
            "  WHERE dr.milestone_type IN ['diagnosis', 'diagnosis_confirmed'] "
            "WITH ep, min(toString(diag_enc.date)) AS diag_date "
            "OPTIONAL MATCH (enc2:Encounter)-[:IS_PART_OF]->(ep) "
            "WITH ep.status AS ep_status, "
            "     ep.first_presentation_date AS fp_date, "
            "     toString(ep.referral_date) AS ref_date, "
            "     ep.safety_netting_recorded AS sn, "
            "     diag_date, "
            "     count(DISTINCT enc2) AS consultation_count "
            "RETURN ep_status, fp_date, ref_date, sn, diag_date, consultation_count",
            **params,
        )

        _CLOSED = {"closed", "completed", "merged", "excluded"}

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
        confirmed = sum(1 for r in rows if r.get("diag_date") is not None)

        pci_vals = [
            v for r in rows
            if (v := _safe_days(r.get("fp_date"), r.get("ref_date"))) is not None
        ]
        di_vals = [
            v for r in rows
            if (v := _safe_days(r.get("fp_date"), r.get("diag_date"))) is not None
        ]
        consult_vals = [
            r["consultation_count"] for r in rows
            if r.get("consultation_count") is not None
        ]
        sn_count = sum(1 for r in rows if r.get("sn") is True)

        return {
            "total_episodes": total,
            "active_episodes": active,
            "confirmed_cancers": confirmed,
            "median_pci_days": round(sum(pci_vals) / len(pci_vals), 1) if pci_vals else None,
            "median_di_days": round(sum(di_vals) / len(di_vals), 1) if di_vals else None,
            "avg_consultations": round(sum(consult_vals) / len(consult_vals), 1) if consult_vals else None,
            "safety_netting_pct": round(sn_count * 100.0 / total, 1) if total else None,
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Section endpoints – all return the multi-scope envelope
# ---------------------------------------------------------------------------


@router.get("/audit/cancer-type")
def audit_cancer_type(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    benchmark_set_id: Optional[str] = Query(default=None),
):
    """Distribution of cancer types – multi-scope live data + optional benchmark."""
    client = PatientGraphClient()
    try:
        return _run_multi_scope(_q_cancer_type, org_id, scope, date_from, date_to, benchmark_set_id, "condition_type", client)
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
        return _run_multi_scope(_q_cancer_stage, org_id, scope, date_from, date_to, benchmark_set_id, "cancer_stage", client)
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
        return _run_multi_scope(_q_demographics, org_id, scope, date_from, date_to, benchmark_set_id, "demographics", client)
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
        return _run_multi_scope(_q_place, org_id, scope, date_from, date_to, benchmark_set_id, "place_of_presentation", client)
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
        return _run_multi_scope(_q_consultations, org_id, scope, date_from, date_to, benchmark_set_id, "consultations", client)
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
        return _run_multi_scope(_q_investigations, org_id, scope, date_from, date_to, benchmark_set_id, "investigations", client)
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
        return _run_multi_scope(_q_referrals, org_id, scope, date_from, date_to, benchmark_set_id, "referrals", client)
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
    for strip/dot plot visualisation. Multi-scope: only aggregates for
    alliance/england (patient-level points are practice only).
    """
    client = PatientGraphClient()
    try:
        # For intervals, patient-level points are only returned for the practice scope.
        # Alliance / England just return aggregate stats without the patient array
        # (to avoid huge payloads).
        result = _run_multi_scope(
            _q_intervals, org_id, scope, date_from, date_to, benchmark_set_id, "primary_care_interval", client
        )
        # Fetch DI benchmarks separately (different category key)
        if benchmark_set_id and result.get("benchmark"):
            di_bm = _fetch_benchmark_metrics(benchmark_set_id, "diagnostic_interval")
            if di_bm and di_bm.get("metrics"):
                result["benchmark"]["metrics"].update(di_bm["metrics"])

        # Strip patient-level data from alliance/england to reduce payload
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
        return _run_multi_scope(_q_safety_netting, org_id, scope, date_from, date_to, benchmark_set_id, "safety_netting", client)
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
        return _run_multi_scope(_q_avoidable_delays, org_id, scope, date_from, date_to, benchmark_set_id, "avoidable_delays", client)
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Comorbidities (dynamic — reads config from cancer_audit domain)
# ---------------------------------------------------------------------------


# Fallback map for comorbidity concepts that don't yet have benchmark_key in their
# ValueSet designation.  Keys are SNOMED concept IDs (strings); values are
# (friendly display label, ncda_2018_benchmarks key).
_COMORBIDITY_CODE_META: dict[str, tuple[str, str]] = {
    "38341003":  ("Hypertension",           "comorbidity_hypertension_pct"),
    "49601007":  ("Cardiovascular disease",  "comorbidity_cvd_pct"),
    "3723001":   ("Arthritis",              "comorbidity_arthritis_pct"),
    "928000":    ("Musculoskeletal disorder","comorbidity_arthritis_pct"),
    "73211009":  ("Diabetes mellitus",      "comorbidity_diabetes_pct"),
    "13645005":  ("COPD",                   "comorbidity_copd_pct"),
    "62914000":  ("Cerebrovascular disease", "comorbidity_cvd_pct"),
    "386806002": ("Impaired cognition",     "comorbidity_mental_health_pct"),
    "74732009":  ("Mental health disorder",  "comorbidity_mental_health_pct"),
    "21134002":  ("Disability",             "comorbidity_disability_pct"),
    "266987004": ("Previous cancer",        "comorbidity_previous_cancer_pct"),
}


def _ensure_registry(kg: KnowledgeGraphClient) -> DomainRegistry:
    """Return (or lazily bootstrap) the DomainRegistry singleton.

    The registry is normally seeded at startup, but if the analytics-api starts
    before the KG is available the singleton may be uninitialised. This helper
    performs a one-shot bootstrap from ncda-* ValueSet nodes in the KG so that
    the comorbidities query always has a valid registry to work with.
    """
    try:
        return DomainRegistry.get_instance()
    except RuntimeError:
        pass  # Bootstrap below

    rows = kg.run(
        "MATCH (v:ValueSet) WHERE v.id STARTS WITH 'ncda-' "
        "RETURN v.id AS id, v.rawJson AS raw_json"
    )
    valuesets: dict = {}
    import json as _json
    for r in (rows or []):
        raw = r.get("raw_json")
        if not raw:
            continue
        try:
            vs_dict = _json.loads(raw) if isinstance(raw, str) else raw
            valuesets[r["id"]] = vs_dict
        except Exception:
            pass

    if valuesets:
        return DomainRegistry.from_fhir(valuesets)
    raise RuntimeError(
        "DomainRegistry: no ncda-* ValueSet nodes found in the knowledge graph. "
        "Seed the KG with domain ValueSets before starting the analytics-api."
    )


def _q_comorbidities(base: str, params: dict, client: PatientGraphClient) -> dict:
    """Query comorbidity prevalence from HAS_DISEASE relationships.

    Top-level concepts are loaded from the cancer_audit/comorbidities subdomain.
    Each concept is expanded via IS_A hierarchy to capture all clinical variants.
    Results are grouped back to the top-level category term.
    """
    kg = KnowledgeGraphClient()
    try:
        registry = _ensure_registry(kg)
    except Exception:
        kg.close()
        return {"comorbidities": [], "total_patients": 0}

    try:
        concept_groups = registry.get_concept_id_groups("comorbidities", kg, depth=3)
    finally:
        kg.close()

    if not concept_groups:
        return {"comorbidities": [], "total_patients": 0}

    # Build display-name and benchmark-key lookups from registry concepts.
    # concept_groups is keyed by benchmark_key (when set) or display term.
    # We need both the human-readable label AND the benchmark key per group.
    domain_concepts = registry.get_domain_concepts("comorbidities")
    group_key_to_display: dict[str, str] = {}
    group_key_to_bm_key: dict[str, Optional[str]] = {}
    for concept in domain_concepts:
        gk = concept.benchmark_key or concept.term
        code_str = str(concept.concept_id)
        # Prefer stored benchmark_key; fall back to the hard-coded map for codes
        # where the ValueSet designation was populated before benchmark_key support.
        if code_str in _COMORBIDITY_CODE_META and not concept.benchmark_key:
            friendly_label, fallback_bm_key = _COMORBIDITY_CODE_META[code_str]
        else:
            friendly_label = concept.preferred_term
            fallback_bm_key = concept.benchmark_key
        if gk not in group_key_to_display:
            group_key_to_display[gk] = friendly_label
            group_key_to_bm_key[gk] = fallback_bm_key

    # Build reverse map: child_id (as string) -> group_key
    id_to_term: dict[str, str] = {}
    all_ids: list[str] = []
    for term, ids in concept_groups.items():
        for cid in ids:
            cid_str = str(cid)
            if cid_str not in id_to_term:
                id_to_term[cid_str] = term
            if cid_str not in all_ids:
                all_ids.append(cid_str)

    # Total patients in scope (denominator)
    total_rows = client.run(
        f"{base}"
        "RETURN count(DISTINCT p) AS n",
        **params,
    )
    total = (total_rows[0]["n"] if total_rows else 0) or 1

    # Dual-path query: covers both
    #   Path 1 — HAS_DISEASE (migrated legacy data + future direct writes)
    #   Path 2 — DOCUMENTS (new NER pipeline, any node label — Situation/Clinical_finding/Disease)
    # OPTIONAL MATCH + collect/UNWIND deduplicates patients appearing on both paths.
    # Comorbidities are chronic conditions — we do NOT filter by documentation date.
    # The HAS_DISEASE path covers migrated legacy data + direct writes.
    # The DOCUMENTS path covers the NER pipeline output (any node label).
    disease_rows = client.run(
        f"{base}"
        "WITH p "
        "OPTIONAL MATCH (p)-[r1:HAS_DISEASE]->(d1) "
        "  WHERE d1.conceptId IN $concept_ids AND r1.domain = 'comorbidities' "
        "OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc)-[r2:DOCUMENTS]->(d2) "
        "  WHERE d2.conceptId IN $concept_ids AND r2.domain = 'comorbidities' "
        "WITH p, collect(DISTINCT d1.conceptId) + collect(DISTINCT d2.conceptId) AS cids "
        "UNWIND cids AS concept_id "
        "WITH p, concept_id WHERE concept_id IS NOT NULL "
        "RETURN concept_id, count(DISTINCT p) AS n",
        **{**params, "concept_ids": all_ids},
    )

    # Group by top-level term
    counts: dict[str, int] = {term: 0 for term in concept_groups}
    for row in disease_rows:
        cid_str = str(row.get("concept_id") or "")
        if not cid_str:
            continue
        top_term = id_to_term.get(cid_str)
        if top_term and top_term in counts:
            counts[top_term] += row["n"]

    comorbidities = sorted(
        [
            {
                # Use the human-readable display term for the UI label
                "condition": group_key_to_display.get(term, term),
                "n": n,
                "pct": round(n * 100.0 / total, 1),
                # benchmark_key for resolveBenchmarkValue lookups against ncda_2018_benchmarks
                "benchmark_key": group_key_to_bm_key.get(term),
            }
            for term, n in counts.items()
        ],
        key=lambda x: x["pct"],
        reverse=True,
    )

    return {"comorbidities": comorbidities, "total_patients": total}


@router.get("/audit/comorbidities")
def audit_comorbidities(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    benchmark_set_id: Optional[str] = Query(default=None),
):
    """Comorbidity prevalence from HAS_DISEASE relationships.

    Concept list is read dynamically from the cancer_audit/comorbidities subdomain.
    Each top-level concept is expanded via the SNOMED IS_A hierarchy so all clinical
    variants are captured and results are grouped back to the top-level category.
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
