"""Shared helpers for NCDA audit endpoints.

Match templates, scope resolution, benchmark fetching, multi-scope runner.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from libs.auth.org_scope import CallerScope, ORG_PATIENT_FILTER
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Match templates
# ---------------------------------------------------------------------------

_EPISODE_EXCLUDE = "NOT ep.status IN ['merged', 'closed_phantom', 'closed_related'] "

_ORG_PATIENT_MATCH = (
    "MATCH (_scope:Organization {id: $org}) "
    "MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
    "WHERE (gp.id = $org) OR (gp)-[:COMMISSIONED_BY]->(_scope) "
    "   OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(_scope) "
    "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    f"WHERE {_EPISODE_EXCLUDE}"
)

_ENGLAND_BASE = (
    "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    f"WHERE {_EPISODE_EXCLUDE}"
)


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
        f"WHERE {ORG_PATIENT_FILTER} AND {_EPISODE_EXCLUDE}",
        scope.to_query_params(),
    )


def _add_date_filters(
    base: str, params: dict, date_from: Optional[str], date_to: Optional[str]
) -> tuple[str, dict]:
    """Append optional referral_date range filters.

    All base templates end with an active WHERE clause (WHERE true, or a real
    predicate), so predicates are always joined with AND -- never a bare WHERE.
    """
    clauses: list[str] = []
    if date_from:
        clauses.append("ep.referral_date >= $date_from")
        params = {**params, "date_from": date_from}
    if date_to:
        clauses.append("ep.referral_date <= $date_to")
        params = {**params, "date_to": date_to}
    if clauses:
        base = base.rstrip() + " AND " + " AND ".join(clauses) + " "
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
    """Resolve the ODS code for a given org_id."""
    rows = client.run(
        "MATCH (o:Organization {id: $org_id}) "
        "RETURN coalesce(o.ods_code, o.id) AS ods_code",
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

        metrics: dict[str, dict] = {}
        practice_rows: dict[str, list] = {}
        alliance_rows: dict[str, list] = {}

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

        for mid, arows in alliance_rows.items():
            matched = (
                next((a for a in arows if a.get("scope_id") == alliance_id), None)
                if alliance_id
                else None
            )
            if matched is None:
                matched = arows[0] if arows else None
            if matched:
                metrics[mid]["alliance"] = matched["value"]

        if practice_rows and (org_ods_code or org_id):
            ods = org_ods_code or org_id
            for mid, prows in practice_rows.items():
                matched = next((pr for pr in prows if pr.get("scope_id") == ods), None)
                if matched is None:
                    norm_id = (org_id or "").lower().replace(" ", "").replace("-", "")
                    matched = next(
                        (
                            pr
                            for pr in prows
                            if norm_id
                            and norm_id
                            in (pr.get("scope_name") or "")
                            .lower()
                            .replace(" ", "")
                            .replace("-", "")
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


def _run_multi_scope(
    query_fn: Callable,
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
    practice_base, practice_params = _add_date_filters(
        practice_base, practice_params, date_from, date_to
    )
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
                logger.exception("Alliance scope query failed for %s", alliance_id)
                alliance_data = None

        e_base, e_params = _ENGLAND_BASE, {}
        e_base, e_params = _add_date_filters(e_base, e_params, date_from, date_to)
        try:
            england_data = query_fn(e_base, e_params, client)
        except Exception:
            logger.exception("England scope query failed")
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
