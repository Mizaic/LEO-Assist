"""Condition-focused Pathway Explorer missions.

Atlas trace:
  DO: DO-D5B9FE5F
  DI: DI-6E1B71A4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-D5B9FE5F")

Missions: critical (PageRank), busiest (Degree), bridges (Betweenness),
          missing (Adamic-Adar), teams (Label Propagation), bottleneck (Cypher).
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List

from services.analytics_api.app.services.algorithm_runner_helpers import (
    AlgorithmResult,
    _ensure_projection,
    _gds_client_from_env,
    _get_coverage,
    _enrich_snomed_labels,
    _enrich_evidence_text,
    _period_to_months,
)
from services.analytics_api.app.services.gds_projection_manager import (
    PROJ_CONDITION_COOCCUR,
)
from services.analytics_api.app.services.headline_generator import (
    generate_headline,
    generate_method_text,
)

logger = logging.getLogger(__name__)


def _run_critical(
    client,
    scope,
    area,
    period,
    detail,
    limit,
    scope_label,
    patient_id=None,
    confidence_min=0.5,
    context_filter="current",
) -> AlgorithmResult:
    """PageRank on condition co-occurrence -> most important conditions."""
    _ensure_projection(
        client,
        scope,
        PROJ_CONDITION_COOCCUR,
        confidence_min=confidence_min,
        context_filter=context_filter,
    )
    gds = _gds_client_from_env()
    coverage = _get_coverage(client, scope, area, period)
    method = generate_method_text("critical", scope_label)

    try:
        g = gds.graph.get(PROJ_CONDITION_COOCCUR)
        pr_df = gds.pageRank.stream(
            g,
            dampingFactor=0.85,
            maxIterations=20,
            relationshipWeightProperty="weight",
        )
        rows = pr_df.nlargest(limit, "score").to_dict("records")
    finally:
        gds.close()

    items = [
        {"node_id": int(r["nodeId"]), "score": float(r["score"]), "rank": i + 1}
        for i, r in enumerate(rows)
    ]
    items = _enrich_snomed_labels(client, items)
    items = _enrich_evidence_text(client, items)
    headline = generate_headline("critical", items, scope_label, detail)
    return AlgorithmResult(
        mission_id="critical",
        headline=headline,
        items=items,
        total_count=len(items),
        coverage=coverage,
        method_plain=method["plain"],
        method_technical=method["technical"],
        next_steps=NEXT_STEPS["critical"],
        detail_level=detail,
    )


def _run_busiest(
    client,
    scope,
    area,
    period,
    detail,
    limit,
    scope_label,
    patient_id=None,
    confidence_min=0.5,
    context_filter="current",
) -> AlgorithmResult:
    """Degree centrality on condition co-occurrence -> most-connected conditions."""
    _ensure_projection(
        client,
        scope,
        PROJ_CONDITION_COOCCUR,
        confidence_min=confidence_min,
        context_filter=context_filter,
    )
    gds = _gds_client_from_env()
    coverage = _get_coverage(client, scope, area, period)
    method = generate_method_text("busiest", scope_label)

    try:
        g = gds.graph.get(PROJ_CONDITION_COOCCUR)
        dc_df = gds.degree.stream(
            g,
            orientation="UNDIRECTED",
            relationshipWeightProperty="weight",
        )
        rows = dc_df.nlargest(limit, "score").to_dict("records")
    finally:
        gds.close()

    items = [
        {"node_id": int(r["nodeId"]), "degree": float(r["score"]), "rank": i + 1}
        for i, r in enumerate(rows)
    ]
    items = _enrich_snomed_labels(client, items)
    items = _enrich_evidence_text(client, items)
    headline = generate_headline("busiest", items, scope_label, detail)
    return AlgorithmResult(
        mission_id="busiest",
        headline=headline,
        items=items,
        total_count=len(items),
        coverage=coverage,
        method_plain=method["plain"],
        method_technical=method["technical"],
        next_steps=NEXT_STEPS["busiest"],
        detail_level=detail,
    )


def _run_bridges(
    client,
    scope,
    area,
    period,
    detail,
    limit,
    scope_label,
    patient_id=None,
    confidence_min=0.5,
    context_filter="current",
) -> AlgorithmResult:
    """Betweenness Centrality on condition co-occurrence -> bridge conditions."""
    _ensure_projection(
        client,
        scope,
        PROJ_CONDITION_COOCCUR,
        confidence_min=confidence_min,
        context_filter=context_filter,
    )
    gds = _gds_client_from_env()
    coverage = _get_coverage(client, scope, area, period)
    method = generate_method_text("bridges", scope_label)

    try:
        g = gds.graph.get(PROJ_CONDITION_COOCCUR)
        bc_df = gds.betweenness.stream(g, relationshipWeightProperty="weight")
        rows = bc_df.nlargest(limit, "score").to_dict("records")
    finally:
        gds.close()

    items = [
        {"node_id": int(r["nodeId"]), "score": float(r["score"]), "rank": i + 1}
        for i, r in enumerate(rows)
    ]
    items = _enrich_snomed_labels(client, items)
    items = _enrich_evidence_text(client, items)
    headline = generate_headline("bridges", items, scope_label, detail)
    return AlgorithmResult(
        mission_id="bridges",
        headline=headline,
        items=items,
        total_count=len(items),
        coverage=coverage,
        method_plain=method["plain"],
        method_technical=method["technical"],
        next_steps=NEXT_STEPS.get("bridges", []),
        detail_level=detail,
    )


def _run_missing(
    client,
    scope,
    area,
    period,
    detail,
    limit,
    scope_label,
    patient_id=None,
    confidence_min=0.5,
    context_filter="current",
) -> AlgorithmResult:
    """Adamic-Adar link prediction -> likely missing condition co-occurrences.

    Uses the Cypher function gds.linkprediction.adamicAdar(n1, n2) which is
    the GDS 2026 replacement for the removed gds.adamicAdar.stream procedure.
    No projection needed -- runs directly on the stored graph.

    Performance: ~45s on 107 patients / 10k findings. Callers should run this
    via the async research_worker job queue, not in a synchronous request.
    """
    coverage = _get_coverage(client, scope, area, period)
    method = generate_method_text("missing", scope_label)

    try:
        # Pre-filter: only compute Adamic-Adar for pairs that already share
        # at least one patient via HAS_CLINICAL_FINDING.  A cartesian product
        # over all ~2k Clinical_finding nodes (~2M pairs) is too slow.
        rows = client.run(
            "MATCH (n1:Clinical_finding)<-[:HAS_CLINICAL_FINDING]"
            "-(p:Patient)-[:HAS_CLINICAL_FINDING]->(n2:Clinical_finding) "
            "WHERE id(n1) < id(n2) "
            "WITH DISTINCT n1, n2 "
            "WITH n1, n2, gds.linkprediction.adamicAdar(n1, n2) AS score "
            "WHERE score > 0 "
            "RETURN id(n1) AS node_a, id(n2) AS node_b, score "
            "ORDER BY score DESC "
            "LIMIT $limit",
            limit=limit,
        )
    except Exception as exc:
        logger.error("Adamic-Adar Cypher function failed: %s", exc)
        rows = []

    items = [
        {
            "node_a": int(r["node_a"]),
            "node_b": int(r["node_b"]),
            "score": float(r["score"]),
            "rank": i + 1,
        }
        for i, r in enumerate(rows)
    ]

    all_node_ids = list(
        {nid for item in items for nid in (item["node_a"], item["node_b"])}
    )
    if all_node_ids:
        try:
            label_rows = client.run(
                "MATCH (e) WHERE id(e) IN $ids "
                "RETURN id(e) AS nid, "
                "       coalesce(e.preferredTerm, e.fsn, "
                "               toString(e.conceptId)) AS label",
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
        next_steps=NEXT_STEPS["missing"],
        detail_level=detail,
    )


def _run_teams(
    client,
    scope,
    area,
    period,
    detail,
    limit,
    scope_label,
    patient_id=None,
    confidence_min=0.5,
    context_filter="current",
) -> AlgorithmResult:
    """Label Propagation -> tightly-knit condition groups."""
    _ensure_projection(
        client,
        scope,
        PROJ_CONDITION_COOCCUR,
        confidence_min=confidence_min,
        context_filter=context_filter,
    )
    gds = _gds_client_from_env()
    coverage = _get_coverage(client, scope, area, period)
    method = generate_method_text("teams", scope_label)

    # Label Propagation works with directed graphs and finds tightly-knit
    # condition communities -- suitable for the directed co-occur projection.
    try:
        g = gds.graph.get(PROJ_CONDITION_COOCCUR)
        lp_df = gds.labelPropagation.stream(g)
        rows = lp_df.to_dict("records")
    finally:
        gds.close()

    community_sizes: Counter = Counter(row["communityId"] for row in rows)
    top_communities = [cid for cid, _ in community_sizes.most_common(limit)]
    community_members: Dict[int, List[int]] = {
        cid: [int(r["nodeId"]) for r in rows if r["communityId"] == cid]
        for cid in top_communities
    }
    items: List[Dict[str, Any]] = [
        {
            "community_id": cid,
            "size": community_sizes[cid],
            "node_ids": community_members[cid][:5],
            "rank": i + 1,
        }
        for i, cid in enumerate(top_communities)
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
        next_steps=NEXT_STEPS["teams"],
        detail_level=detail,
    )


def _run_bottleneck(
    client,
    scope,
    area,
    period,
    detail,
    limit,
    scope_label,
    patient_id=None,
    confidence_min=0.5,
    context_filter="current",
) -> AlgorithmResult:
    """Shortest path + temporal gap -> where patients wait longest."""
    coverage = _get_coverage(client, scope, area, period)
    method = generate_method_text("bottleneck", scope_label)
    months = _period_to_months(period)

    scope_where = (
        "WHERE EXISTS { "
        "  (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
        "  WHERE gp.id IN $scope_org_ids "
        "}"
        if not scope.is_admin
        else ""
    )
    params: Dict[str, Any] = {"months": months, "limit": limit}
    if not scope.is_admin:
        params["scope_org_ids"] = scope.org_ids

    rows = client.run(
        f"MATCH (p:Patient) {scope_where} "
        "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
        # Guard against empty/null referral_date before calling date()
        "WHERE ep.referral_date IS NOT NULL "
        "  AND trim(toString(ep.referral_date)) <> '' "
        "WITH p, ep, date(toString(ep.referral_date)) AS ref_date "
        "WHERE ref_date >= date() - duration({months: $months}) "
        "MATCH (e1:Encounter)-[r1:IS_PART_OF]->(ep) "
        "MATCH (e2:Encounter)-[r2:IS_PART_OF]->(ep) "
        "WHERE r1.milestone_type IS NOT NULL AND trim(r1.milestone_type) <> '' "
        "  AND r2.milestone_type IS NOT NULL AND trim(r2.milestone_type) <> '' "
        "  AND e1.date IS NOT NULL AND e2.date IS NOT NULL "
        "  AND e2.date > e1.date "
        "WITH r2.milestone_type AS label, "
        "     duration.inDays(date(e1.date), date(e2.date)).days AS wait_days, "
        "     p.id AS patient_id "
        "WITH label, "
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
        next_steps=NEXT_STEPS["bottleneck"],
        detail_level=detail,
    )


NEXT_STEPS: Dict[str, list] = {
    "teams": [
        {"label": "Which conditions are most central?", "target": "critical"},
        {"label": "Are any conditions likely missing?", "target": "missing"},
    ],
    "critical": [
        {"label": "How busy are these conditions?", "target": "busiest"},
        {"label": "Which patients have the most of these?", "target": "groups"},
    ],
    "busiest": [
        {"label": "Which conditions are most important?", "target": "critical"},
        {"label": "Are tightly-linked groups forming?", "target": "teams"},
    ],
    "missing": [
        {"label": "Find patients with these missing conditions", "target": "similar"},
        {"label": "Which conditions matter most overall?", "target": "critical"},
    ],
    "bottleneck": [
        {"label": "Are delayed patients similar to each other?", "target": "similar"},
        {"label": "Which conditions are linked to delays?", "target": "critical"},
        {"label": "Are patients falling through gaps here?", "target": "gaps"},
    ],
    "bridges": [
        {"label": "Which conditions are most important?", "target": "critical"},
        {"label": "Are bridge conditions missing?", "target": "missing"},
    ],
}
