"""GDS algorithm runner for Pathway Explorer research missions.

Maps mission IDs to GDS procedure calls.  Each runner function:
 1. Ensures the required projection exists (creates it if absent).
 2. Calls the appropriate GDS algorithm.
 3. Enriches results with human-readable labels from the graph.
 4. Returns a structured AlgorithmResult with typed results.

Result counts by detail level:
  summary    -- top 10 aggregated results
  detailed   -- top 50 individual results
  everything -- all results (capped at 500 for UI safety)

All algorithms use the graphdatascience Python client (GDS 2.x+).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from libs.auth.org_scope import CallerScope
from libs.neo4j_client.client import PatientGraphClient
from services.analytics_api.app.services.gds_projection_manager import (
    PROJ_CONDITION_COOCCUR,
    PROJ_PATIENT_CONDITION,
    PROJ_PATIENT_JOURNEY,
    PROJ_REFERRAL_NETWORK,
    check_referral_data_available,
    create_projection,
)
from services.analytics_api.app.services.headline_generator import (
    generate_headline,
    generate_method_text,
)

logger = logging.getLogger(__name__)

_DETAIL_LIMITS = {"summary": 10, "detailed": 50, "everything": 500}
_DETAIL_GRANULARITY = {"summary": "aggregated", "detailed": "individual", "everything": "full"}


@dataclass
class AlgorithmResult:
    """Structured result from a Pathway Explorer mission run."""

    mission_id: str
    headline: str
    items: List[Dict[str, Any]]
    total_count: int
    coverage: CoverageInfo
    method_plain: str
    method_technical: str
    next_steps: List[Dict[str, str]]
    detail_level: str
    data_available: bool = True
    unavailable_reason: Optional[str] = None
    error: Optional[str] = None


@dataclass
class CoverageInfo:
    """Data coverage metadata shown alongside every result."""

    patient_count: int = 0
    practice_count: int = 0
    confidence: str = "low"  # "low" | "moderate" | "high"
    confidence_note: str = ""


# -- Public dispatch ----------------------------------------------------------


def run_mission(
    mission_id: str,
    client: PatientGraphClient,
    scope: CallerScope,
    area: str = "all",
    period: str = "12m",
    detail: str = "summary",
    patient_id: Optional[str] = None,
) -> AlgorithmResult:
    """Run a named mission and return structured results.

    Args:
        mission_id:  Mission card ID (e.g. "groups", "bottleneck").
        client:      PatientGraphClient for the org.
        scope:       CallerScope for org-filtering.
        area:        Audit area / cancer site (e.g. "lung", "all").
        period:      Time window (e.g. "6m", "12m").
        detail:      Detail level: "summary" | "detailed" | "everything".
        patient_id:  Required for "similar" mission.
    """
    runner = _RUNNERS.get(mission_id)
    if runner is None:
        return AlgorithmResult(
            mission_id=mission_id,
            headline="This investigation is not yet available.",
            items=[],
            total_count=0,
            coverage=CoverageInfo(),
            method_plain="",
            method_technical="",
            next_steps=[],
            detail_level=detail,
            data_available=False,
            unavailable_reason=f"Mission {mission_id!r} is not implemented.",
        )

    scope_label = _build_scope_label(area, period)
    limit = _DETAIL_LIMITS.get(detail, 10)

    try:
        return runner(
            client=client,
            scope=scope,
            area=area,
            period=period,
            detail=detail,
            limit=limit,
            scope_label=scope_label,
            patient_id=patient_id,
        )
    except Exception as exc:
        logger.error("Mission %s failed: %s", mission_id, exc, exc_info=True)
        return AlgorithmResult(
            mission_id=mission_id,
            headline="Something went wrong running this investigation.",
            items=[],
            total_count=0,
            coverage=CoverageInfo(),
            method_plain="",
            method_technical="",
            next_steps=[],
            detail_level=detail,
            error=str(exc),
        )


# -- Shared helpers -----------------------------------------------------------


def _build_scope_label(area: str, period: str) -> str:
    """Human-readable scope description for headlines."""
    period_labels = {"3m": "last 3 months", "6m": "last 6 months", "12m": "last 12 months"}
    area_label = "all pathways" if area == "all" else f"{area.title()} pathway"
    period_label = period_labels.get(period, period)
    return f"{area_label}, {period_label}"


def _period_to_months(period: str) -> int:
    """Convert period string to integer months."""
    return {"3m": 3, "6m": 6, "12m": 12}.get(period, 12)


def _get_coverage(
    client: PatientGraphClient,
    scope: CallerScope,
    area: str,
    period: str,
) -> CoverageInfo:
    """Fetch patient and practice counts for coverage badge."""
    months = _period_to_months(period)
    scope_where = (
        "WHERE EXISTS { "
        "  (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
        "  WHERE gp.id IN $scope_org_ids "
        "}"
        if not scope.is_admin
        else ""
    )
    params: Dict[str, Any] = {}
    if not scope.is_admin:
        params["scope_org_ids"] = scope.org_ids

    date_filter = (
        f" AND EXISTS {{ "
        f"  (p)-[:HAS_ENCOUNTER]->(e:Encounter) "
        f"  WHERE e.date >= date() - duration('P{months}M') "
        f"}}"
    )

    try:
        rows = client.run(
            f"MATCH (p:Patient) {scope_where}{date_filter} "
            "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
            "RETURN count(DISTINCT p) AS patient_count, "
            "       count(DISTINCT gp) AS practice_count",
            **params,
        )
        if not rows:
            return CoverageInfo()
        pat = rows[0].get("patient_count", 0)
        prac = rows[0].get("practice_count", 0)
        confidence = "high" if pat >= 1000 else "moderate" if pat >= 100 else "low"
        note = _coverage_note(pat, prac, confidence)
        return CoverageInfo(
            patient_count=pat,
            practice_count=prac,
            confidence=confidence,
            confidence_note=note,
        )
    except Exception as exc:
        logger.warning("Coverage check failed: %s", exc)
        return CoverageInfo()


def _coverage_note(pat: int, prac: int, confidence: str) -> str:
    """Plain-English coverage note."""
    prac_part = f" across {prac} practice{'s' if prac != 1 else ''}" if prac else ""
    base = f"Based on {pat:,} patients{prac_part}."
    if confidence == "low":
        return base + " Results may not represent the full picture."
    return base


def _ensure_projection(
    client: PatientGraphClient,
    scope: CallerScope,
    projection_name: str,
) -> None:
    """Create projection if it does not already exist."""
    from services.analytics_api.app.services.gds_projection_manager import (
        list_projections,
    )

    summary = list_projections(client, scope)
    existing = {p.name for p in summary.projections if p.exists}
    if projection_name not in existing:
        create_projection(client, scope, projection_name)


def _gds_client_from_env():
    """Return a GDS client for the patient graph."""
    from graphdatascience import GraphDataScience

    uri = os.getenv("NEO4J_URI", "") or os.getenv("NEO4J_PATIENT_URI", "")
    user = os.getenv("NEO4J_USER", "") or os.getenv("NEO4J_PATIENT_USER", "")
    password = (
        os.getenv("NEO4J_PASSWORD", "") or os.getenv("NEO4J_PATIENT_PASSWORD", "")
    )
    return GraphDataScience(uri, auth=(user, password))


def _enrich_snomed_labels(
    client: PatientGraphClient,
    items: List[Dict[str, Any]],
    id_key: str = "node_id",
) -> List[Dict[str, Any]]:
    """Attach human-readable SNOMED labels to result items."""
    node_ids = [item[id_key] for item in items if item.get(id_key) is not None]
    if not node_ids:
        return items
    try:
        rows = client.run(
            "MATCH (e) WHERE id(e) IN $ids "
            "RETURN id(e) AS nid, "
            "       coalesce(e.preferredTerm, e.fsn, toString(e.conceptId), toString(id(e))) AS label",
            ids=node_ids,
        )
        label_map = {row["nid"]: row["label"] for row in rows}
        for item in items:
            nid = item.get(id_key)
            if nid in label_map:
                item["label"] = label_map[nid]
    except Exception as exc:
        logger.warning("SNOMED label enrichment failed: %s", exc)
    return items


def _enrich_org_labels(
    client: PatientGraphClient,
    items: List[Dict[str, Any]],
    id_key: str = "node_id",
) -> List[Dict[str, Any]]:
    """Attach org names to result items for referral-network missions."""
    node_ids = [item[id_key] for item in items if item.get(id_key) is not None]
    if not node_ids:
        return items
    try:
        rows = client.run(
            "MATCH (o) WHERE id(o) IN $ids "
            "RETURN id(o) AS nid, "
            "       coalesce(o.name, o.id, toString(id(o))) AS label",
            ids=node_ids,
        )
        label_map = {row["nid"]: row["label"] for row in rows}
        for item in items:
            nid = item.get(id_key)
            if nid in label_map:
                item["label"] = label_map[nid]
    except Exception as exc:
        logger.warning("Org label enrichment failed: %s", exc)
    return items


# -- Mission runner functions -------------------------------------------------


def _run_groups(
    client, scope, area, period, detail, limit, scope_label, patient_id=None
) -> AlgorithmResult:
    """Leiden community detection -> natural patient groups."""
    _ensure_projection(client, scope, PROJ_PATIENT_CONDITION)
    gds = _gds_client_from_env()
    coverage = _get_coverage(client, scope, area, period)
    method = generate_method_text("groups", scope_label)

    try:
        g = gds.graph.get(PROJ_PATIENT_CONDITION)
        result = gds.leiden.stats(g)
        communities_df = gds.leiden.stream(g)
        communities = communities_df.to_dict("records")
    finally:
        gds.close()

    # Aggregate: count nodes per community, keep top N
    from collections import Counter

    community_sizes: Counter = Counter()
    for row in communities:
        community_sizes[row["communityId"]] += 1

    items = [
        {"community_id": cid, "size": size, "rank": i + 1}
        for i, (cid, size) in enumerate(community_sizes.most_common(limit))
    ]
    total = len(community_sizes)

    headline = generate_headline("groups", items, scope_label, detail)
    return AlgorithmResult(
        mission_id="groups",
        headline=headline,
        items=items,
        total_count=total,
        coverage=coverage,
        method_plain=method["plain"],
        method_technical=method["technical"],
        next_steps=_NEXT_STEPS["groups"],
        detail_level=detail,
        data_available=True,
    )


def _run_similar(
    client, scope, area, period, detail, limit, scope_label, patient_id=None
) -> AlgorithmResult:
    """KNN + Jaccard similarity -> patients like this one."""
    if not patient_id:
        return AlgorithmResult(
            mission_id="similar",
            headline="Please select a patient to find similar records.",
            items=[],
            total_count=0,
            coverage=CoverageInfo(),
            method_plain="",
            method_technical="",
            next_steps=[],
            detail_level=detail,
            data_available=False,
            unavailable_reason="patient_id is required for similarity search",
        )

    _ensure_projection(client, scope, PROJ_PATIENT_CONDITION)
    gds = _gds_client_from_env()
    coverage = _get_coverage(client, scope, area, period)
    method = generate_method_text("similar", scope_label)

    try:
        g = gds.graph.get(PROJ_PATIENT_CONDITION)
        # Get the internal node id for the target patient
        rows = client.run(
            "MATCH (p:Patient) WHERE toString(p.id) = $pid RETURN id(p) AS nid",
            pid=patient_id,
        )
        if not rows:
            gds.close()
            return AlgorithmResult(
                mission_id="similar",
                headline="Patient not found.",
                items=[],
                total_count=0,
                coverage=coverage,
                method_plain=method["plain"],
                method_technical=method["technical"],
                next_steps=[],
                detail_level=detail,
                data_available=False,
                unavailable_reason="Patient not found in graph",
            )
        target_node_id = rows[0]["nid"]
        knn_result = gds.knn.stream(
            g,
            nodeProperties=["communityId"] if False else [],
            topK=limit,
            similarityCutoff=0.1,
        )
        knn_rows = knn_result.to_dict("records")
        # Filter to rows where node1 is the target patient
        similar = [
            {
                "node_id": int(r["node2"]),
                "similarity_score": float(r["similarity"]),
                "rank": i + 1,
            }
            for i, r in enumerate(
                sorted(
                    [x for x in knn_rows if int(x["node1"]) == target_node_id],
                    key=lambda x: -x["similarity"],
                )[:limit]
            )
        ]
    finally:
        gds.close()

    # Enrich with patient IDs
    node_ids = [item["node_id"] for item in similar]
    if node_ids:
        try:
            pid_rows = client.run(
                "MATCH (p:Patient) WHERE id(p) IN $ids "
                "RETURN id(p) AS nid, toString(p.id) AS patient_id",
                ids=node_ids,
            )
            pid_map = {r["nid"]: r["patient_id"] for r in pid_rows}
            for item in similar:
                item["patient_id"] = pid_map.get(item["node_id"], "")
        except Exception as exc:
            logger.warning("Patient ID enrichment failed: %s", exc)

    headline = generate_headline("similar", similar, scope_label, detail)
    return AlgorithmResult(
        mission_id="similar",
        headline=headline,
        items=similar,
        total_count=len(similar),
        coverage=coverage,
        method_plain=method["plain"],
        method_technical=method["technical"],
        next_steps=_NEXT_STEPS["similar"],
        detail_level=detail,
    )


def _run_critical(
    client, scope, area, period, detail, limit, scope_label, patient_id=None
) -> AlgorithmResult:
    """PageRank on condition co-occurrence -> most important conditions."""
    _ensure_projection(client, scope, PROJ_CONDITION_COOCCUR)
    gds = _gds_client_from_env()
    coverage = _get_coverage(client, scope, area, period)
    method = generate_method_text("critical", scope_label)

    try:
        g = gds.graph.get(PROJ_CONDITION_COOCCUR)
        pr_df = gds.pageRank.stream(g, dampingFactor=0.85, maxIterations=20)
        rows = pr_df.nlargest(limit, "score").to_dict("records")
    finally:
        gds.close()

    items = [
        {"node_id": int(r["nodeId"]), "score": float(r["score"]), "rank": i + 1}
        for i, r in enumerate(rows)
    ]
    items = _enrich_snomed_labels(client, items)
    headline = generate_headline("critical", items, scope_label, detail)
    return AlgorithmResult(
        mission_id="critical",
        headline=headline,
        items=items,
        total_count=len(items),
        coverage=coverage,
        method_plain=method["plain"],
        method_technical=method["technical"],
        next_steps=_NEXT_STEPS["critical"],
        detail_level=detail,
    )


def _run_busiest(
    client, scope, area, period, detail, limit, scope_label, patient_id=None
) -> AlgorithmResult:
    """Degree centrality on condition co-occurrence -> most-connected conditions."""
    _ensure_projection(client, scope, PROJ_CONDITION_COOCCUR)
    gds = _gds_client_from_env()
    coverage = _get_coverage(client, scope, area, period)
    method = generate_method_text("busiest", scope_label)

    try:
        g = gds.graph.get(PROJ_CONDITION_COOCCUR)
        dc_df = gds.degree.stream(g)
        rows = dc_df.nlargest(limit, "score").to_dict("records")
    finally:
        gds.close()

    items = [
        {"node_id": int(r["nodeId"]), "degree": float(r["score"]), "rank": i + 1}
        for i, r in enumerate(rows)
    ]
    items = _enrich_snomed_labels(client, items)
    headline = generate_headline("busiest", items, scope_label, detail)
    return AlgorithmResult(
        mission_id="busiest",
        headline=headline,
        items=items,
        total_count=len(items),
        coverage=coverage,
        method_plain=method["plain"],
        method_technical=method["technical"],
        next_steps=_NEXT_STEPS["busiest"],
        detail_level=detail,
    )


def _run_bottleneck(
    client, scope, area, period, detail, limit, scope_label, patient_id=None
) -> AlgorithmResult:
    """Shortest path + temporal gap -> where patients wait longest."""
    coverage = _get_coverage(client, scope, area, period)
    method = generate_method_text("bottleneck", scope_label)
    months = _period_to_months(period)

    # Use Cypher directly for bottleneck: aggregate wait times per milestone step
    scope_where = (
        "WHERE EXISTS { "
        "  (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
        "  WHERE gp.id IN $scope_org_ids "
        "}"
        if not scope.is_admin
        else ""
    )
    params: Dict[str, Any] = {
        "months": months,
        "limit": limit,
    }
    if not scope.is_admin:
        params["scope_org_ids"] = scope.org_ids

    rows = client.run(
        f"MATCH (p:Patient) {scope_where} "
        "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
        "MATCH (e1:Encounter)-[r1:IS_PART_OF]->(ep) "
        "MATCH (e2:Encounter)-[r2:IS_PART_OF]->(ep) "
        "WHERE r1.milestone_type IS NOT NULL "
        "  AND r2.milestone_type IS NOT NULL "
        "  AND e1.date IS NOT NULL AND e2.date IS NOT NULL "
        "  AND e2.date > e1.date "
        "  AND ep.referral_date >= date() - duration({months: $months}) "
        "WITH r1.milestone_type AS from_milestone, "
        "     r2.milestone_type AS to_milestone, "
        "     duration.inDays(date(toString(e1.date)), "
        "                     date(toString(e2.date))).days AS wait_days, "
        "     p.id AS patient_id "
        "WITH to_milestone AS label, "
        "     avg(wait_days) AS avg_wait_days, "
        "     count(DISTINCT patient_id) AS patient_count "
        "ORDER BY avg_wait_days DESC "
        "RETURN label, avg_wait_days, patient_count "
        "LIMIT $limit",
        **params,
    )

    items = [
        {
            "label": row["label"] or "Unknown step",
            "avg_wait_days": float(row["avg_wait_days"] or 0),
            "patient_count": int(row["patient_count"] or 0),
            "is_bottleneck": (row["avg_wait_days"] or 0) >= 14,
            "rank": i + 1,
        }
        for i, row in enumerate(rows)
    ]

    headline = generate_headline("bottleneck", items, scope_label, detail)
    return AlgorithmResult(
        mission_id="bottleneck",
        headline=headline,
        items=items,
        total_count=len(items),
        coverage=coverage,
        method_plain=method["plain"],
        method_technical=method["technical"],
        next_steps=_NEXT_STEPS["bottleneck"],
        detail_level=detail,
    )


def _run_gaps(
    client, scope, area, period, detail, limit, scope_label, patient_id=None
) -> AlgorithmResult:
    """Weakly Connected Components -> isolated patient groups."""
    _ensure_projection(client, scope, PROJ_PATIENT_CONDITION)
    gds = _gds_client_from_env()
    coverage = _get_coverage(client, scope, area, period)
    method = generate_method_text("gaps", scope_label)

    try:
        g = gds.graph.get(PROJ_PATIENT_CONDITION)
        wcc_df = gds.wcc.stream(g)
        wcc_rows = wcc_df.to_dict("records")
    finally:
        gds.close()

    from collections import Counter

    comp_sizes: Counter = Counter(row["componentId"] for row in wcc_rows)
    # The main component is the largest; isolated = everything else
    if not comp_sizes:
        items = []
        total = 0
    else:
        main_comp = comp_sizes.most_common(1)[0][0]
        isolated = [
            {"component_id": cid, "size": size, "rank": i + 1, "is_main": False}
            for i, (cid, size) in enumerate(
                comp_sizes.most_common()
            )
            if cid != main_comp and size >= 2
        ][:limit]
        items = isolated
        total = len([s for cid, s in comp_sizes.items() if cid != main_comp and s >= 2])

    headline = generate_headline("gaps", items, scope_label, detail)
    return AlgorithmResult(
        mission_id="gaps",
        headline=headline,
        items=items,
        total_count=total,
        coverage=coverage,
        method_plain=method["plain"],
        method_technical=method["technical"],
        next_steps=_NEXT_STEPS["gaps"],
        detail_level=detail,
    )


def _run_circles(
    client, scope, area, period, detail, limit, scope_label, patient_id=None
) -> AlgorithmResult:
    """SCC -> circular patterns in patient journey graph."""
    _ensure_projection(client, scope, PROJ_PATIENT_JOURNEY)
    gds = _gds_client_from_env()
    coverage = _get_coverage(client, scope, area, period)
    method = generate_method_text("circles", scope_label)

    try:
        g = gds.graph.get(PROJ_PATIENT_JOURNEY)
        scc_df = gds.scc.stream(g)
        scc_rows = scc_df.to_dict("records")
    finally:
        gds.close()

    from collections import Counter

    comp_sizes: Counter = Counter(row["componentId"] for row in scc_rows)
    # SCCs with >= 2 members are circular
    circular = [
        {"component_id": cid, "size": size, "rank": i + 1}
        for i, (cid, size) in enumerate(
            [(c, s) for c, s in comp_sizes.most_common() if s >= 2][:limit]
        )
    ]
    total = sum(1 for s in comp_sizes.values() if s >= 2)

    headline = generate_headline("circles", circular, scope_label, detail)
    return AlgorithmResult(
        mission_id="circles",
        headline=headline,
        items=circular,
        total_count=total,
        coverage=coverage,
        method_plain=method["plain"],
        method_technical=method["technical"],
        next_steps=_NEXT_STEPS["circles"],
        detail_level=detail,
    )


def _run_teams(
    client, scope, area, period, detail, limit, scope_label, patient_id=None
) -> AlgorithmResult:
    """Triangle Count + Clustering Coefficient -> tightly-knit condition groups."""
    _ensure_projection(client, scope, PROJ_CONDITION_COOCCUR)
    gds = _gds_client_from_env()
    coverage = _get_coverage(client, scope, area, period)
    method = generate_method_text("teams", scope_label)

    try:
        g = gds.graph.get(PROJ_CONDITION_COOCCUR)
        lcc_df = gds.localClusteringCoefficient.stream(g)
        rows = lcc_df.nlargest(limit, "localClusteringCoefficient").to_dict("records")
    finally:
        gds.close()

    items = [
        {
            "node_id": int(r["nodeId"]),
            "clustering_coefficient": float(r["localClusteringCoefficient"]),
            "rank": i + 1,
        }
        for i, r in enumerate(rows)
    ]
    items = _enrich_snomed_labels(client, items)
    headline = generate_headline("teams", items, scope_label, detail)
    return AlgorithmResult(
        mission_id="teams",
        headline=headline,
        items=items,
        total_count=len(items),
        coverage=coverage,
        method_plain=method["plain"],
        method_technical=method["technical"],
        next_steps=_NEXT_STEPS["teams"],
        detail_level=detail,
    )


def _run_missing(
    client, scope, area, period, detail, limit, scope_label, patient_id=None
) -> AlgorithmResult:
    """Adamic-Adar link prediction -> likely missing condition co-occurrences."""
    _ensure_projection(client, scope, PROJ_CONDITION_COOCCUR)
    gds = _gds_client_from_env()
    coverage = _get_coverage(client, scope, area, period)
    method = generate_method_text("missing", scope_label)

    try:
        g = gds.graph.get(PROJ_CONDITION_COOCCUR)
        aa_df = gds.adamicAdar.stream(g, topK=limit)
        rows = aa_df.to_dict("records")
    finally:
        gds.close()

    items = [
        {
            "node_a": int(r["node1"]),
            "node_b": int(r["node2"]),
            "score": float(r["similarity"]),
            "rank": i + 1,
        }
        for i, r in enumerate(
            sorted(rows, key=lambda x: -x.get("similarity", 0))[:limit]
        )
    ]

    # Enrich both node columns
    all_node_ids = list(
        {nid for item in items for nid in (item["node_a"], item["node_b"])}
    )
    if all_node_ids:
        try:
            label_rows = client.run(
                "MATCH (e) WHERE id(e) IN $ids "
                "RETURN id(e) AS nid, "
                "       coalesce(e.preferredTerm, e.fsn, toString(e.conceptId)) AS label",
                ids=all_node_ids,
            )
            label_map = {r["nid"]: r["label"] for r in label_rows}
            for item in items:
                item["node_a_label"] = label_map.get(item["node_a"], "")
                item["node_b_label"] = label_map.get(item["node_b"], "")
        except Exception as exc:
            logger.warning("Label enrichment failed for missing mission: %s", exc)

    headline = generate_headline("missing", items, scope_label, detail)
    return AlgorithmResult(
        mission_id="missing",
        headline=headline,
        items=items,
        total_count=len(items),
        coverage=coverage,
        method_plain=method["plain"],
        method_technical=method["technical"],
        next_steps=_NEXT_STEPS["missing"],
        detail_level=detail,
    )


# -- Guided next steps --------------------------------------------------------

_NEXT_STEPS: Dict[str, List[Dict[str, str]]] = {
    "groups": [
        {"label": "Find patients like one from a specific group", "target": "similar"},
        {"label": "Which conditions matter most within these groups?", "target": "critical"},
    ],
    "similar": [
        {"label": "What groups do similar patients belong to?", "target": "groups"},
        {"label": "Which conditions are these patients missing?", "target": "missing"},
    ],
    "teams": [
        {"label": "Which of these conditions are most central?", "target": "critical"},
        {"label": "Are any of these conditions likely missing?", "target": "missing"},
    ],
    "critical": [
        {"label": "How busy are these conditions in the pathway?", "target": "busiest"},
        {"label": "Which patients have the most of these conditions?", "target": "groups"},
    ],
    "busiest": [
        {"label": "Which of these conditions are most important?", "target": "critical"},
        {"label": "Are tightly-linked groups forming around these?", "target": "teams"},
    ],
    "missing": [
        {"label": "Find patients who might have these missing conditions", "target": "similar"},
        {"label": "Which conditions matter most overall?", "target": "critical"},
    ],
    "bottleneck": [
        {"label": "Are the delayed patients similar to each other?", "target": "similar"},
        {"label": "Which conditions are associated with delays?", "target": "critical"},
        {"label": "Are patients falling through the gaps at these steps?", "target": "gaps"},
    ],
    "gaps": [
        {"label": "Find patients similar to the isolated ones", "target": "similar"},
        {"label": "Which conditions are these isolated patients missing?", "target": "missing"},
    ],
    "circles": [
        {"label": "Are there also patients falling through the gaps?", "target": "gaps"},
        {"label": "Which conditions drive these circular patterns?", "target": "critical"},
    ],
}

# -- Dispatch table -----------------------------------------------------------

_RUNNERS = {
    "groups": _run_groups,
    "similar": _run_similar,
    "teams": _run_teams,
    "critical": _run_critical,
    "busiest": _run_busiest,
    "missing": _run_missing,
    "bottleneck": _run_bottleneck,
    "gaps": _run_gaps,
    "circles": _run_circles,
}
