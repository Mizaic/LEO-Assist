"""Patient-focused Pathway Explorer missions.

Missions: groups (Leiden), similar (node similarity), gaps (WCC), circles (SCC).
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List

from libs.auth.org_scope import CallerScope
from libs.neo4j_client.client import PatientGraphClient
from services.analytics_api.app.services.algorithm_runner_helpers import (
    AlgorithmResult,
    CoverageInfo,
    _ensure_projection,
    _gds_client_from_env,
    _get_coverage,
    _enrich_leiden_communities,
)
from services.analytics_api.app.services.gds_projection_manager import (
    PROJ_PATIENT_CONDITION,
    PROJ_PATIENT_JOURNEY,
)
from services.analytics_api.app.services.headline_generator import (
    generate_headline,
    generate_method_text,
)

logger = logging.getLogger(__name__)


def _run_groups(
    client, scope, area, period, detail, limit, scope_label, patient_id=None,
    confidence_min=0.5, context_filter="current",
) -> AlgorithmResult:
    """Leiden community detection -> natural patient groups."""
    _ensure_projection(client, scope, PROJ_PATIENT_CONDITION)
    gds = _gds_client_from_env()
    coverage = _get_coverage(client, scope, area, period)
    method = generate_method_text("groups", scope_label)

    # Leiden requires UNDIRECTED projection -- patient-condition is created
    # via native gds.graph.project() with orientation: UNDIRECTED.
    try:
        g = gds.graph.get(PROJ_PATIENT_CONDITION)
        communities_df = gds.leiden.stream(g)
        communities = communities_df.to_dict("records")
    finally:
        gds.close()

    community_sizes: Counter = Counter()
    community_members: Dict[int, List[int]] = {}
    for row in communities:
        cid = row["communityId"]
        community_sizes[cid] += 1
        community_members.setdefault(cid, []).append(int(row["nodeId"]))

    top_cids = [cid for cid, _ in community_sizes.most_common(limit)]
    top_map = {cid: community_members[cid] for cid in top_cids}
    enriched = _enrich_leiden_communities(client, top_map)

    items: List[Dict[str, Any]] = []
    for i, cid in enumerate(top_cids):
        extra = enriched.get(cid, {})
        items.append({"community_id": cid, "size": community_sizes[cid],
                      "rank": i + 1, **extra})

    headline = generate_headline("groups", items, scope_label, detail)
    return AlgorithmResult(
        mission_id="groups", headline=headline, items=items,
        total_count=len(community_sizes), coverage=coverage,
        method_plain=method["plain"], method_technical=method["technical"],
        next_steps=NEXT_STEPS["groups"], detail_level=detail, data_available=True,
    )


def _run_similar(
    client, scope, area, period, detail, limit, scope_label, patient_id=None,
    confidence_min=0.5, context_filter="current",
) -> AlgorithmResult:
    """KNN + Jaccard similarity -> patients like this one."""
    if not patient_id:
        return AlgorithmResult(
            mission_id="similar",
            headline="Please select a patient to find similar records.",
            items=[], total_count=0, coverage=CoverageInfo(),
            method_plain="", method_technical="", next_steps=[],
            detail_level=detail, data_available=False,
            unavailable_reason="patient_id is required for similarity search",
        )

    _ensure_projection(client, scope, PROJ_PATIENT_CONDITION)
    gds = _gds_client_from_env()
    coverage = _get_coverage(client, scope, area, period)
    method = generate_method_text("similar", scope_label)

    try:
        g = gds.graph.get(PROJ_PATIENT_CONDITION)
        rows = client.run(
            "MATCH (p:Patient) WHERE toString(p.id) = $pid RETURN id(p) AS nid",
            pid=patient_id,
        )
        if not rows:
            gds.close()
            return AlgorithmResult(
                mission_id="similar", headline="Patient not found.",
                items=[], total_count=0, coverage=coverage,
                method_plain=method["plain"], method_technical=method["technical"],
                next_steps=[], detail_level=detail, data_available=False,
                unavailable_reason="Patient not found in graph",
            )
        target_node_id = rows[0]["nid"]
        ns_result = gds.nodeSimilarity.stream(g, topK=limit, similarityCutoff=0.1)
        ns_rows = ns_result.to_dict("records")
        similar = [
            {"node_id": int(r["node2"]), "similarity_score": float(r["similarity"]),
             "rank": i + 1}
            for i, r in enumerate(
                sorted(
                    [x for x in ns_rows if int(x["node1"]) == target_node_id],
                    key=lambda x: -x["similarity"],
                )[:limit]
            )
        ]
    finally:
        gds.close()

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
        mission_id="similar", headline=headline, items=similar,
        total_count=len(similar), coverage=coverage,
        method_plain=method["plain"], method_technical=method["technical"],
        next_steps=NEXT_STEPS["similar"], detail_level=detail,
    )


def _run_gaps(
    client, scope, area, period, detail, limit, scope_label, patient_id=None,
    confidence_min=0.5, context_filter="current",
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

    comp_sizes: Counter = Counter(row["componentId"] for row in wcc_rows)
    if not comp_sizes:
        headline = generate_headline("gaps", [], scope_label, detail)
        return AlgorithmResult(
            mission_id="gaps", headline=headline, items=[], total_count=0,
            coverage=coverage, method_plain=method["plain"],
            method_technical=method["technical"], next_steps=NEXT_STEPS["gaps"],
            detail_level=detail,
        )

    main_comp = comp_sizes.most_common(1)[0][0]
    isolated = [
        {"component_id": cid, "size": size, "rank": i + 1, "is_main": False}
        for i, (cid, size) in enumerate(comp_sizes.most_common())
        if cid != main_comp and size >= 2
    ][:limit]
    total = len([s for cid, s in comp_sizes.items() if cid != main_comp and s >= 2])

    headline = generate_headline("gaps", isolated, scope_label, detail)
    return AlgorithmResult(
        mission_id="gaps", headline=headline, items=isolated, total_count=total,
        coverage=coverage, method_plain=method["plain"],
        method_technical=method["technical"], next_steps=NEXT_STEPS["gaps"],
        detail_level=detail,
    )


def _run_circles(
    client, scope, area, period, detail, limit, scope_label, patient_id=None,
    confidence_min=0.5, context_filter="current",
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

    comp_sizes: Counter = Counter(row["componentId"] for row in scc_rows)
    circular = [
        {"component_id": cid, "size": size, "rank": i + 1}
        for i, (cid, size) in enumerate(
            [(c, s) for c, s in comp_sizes.most_common() if s >= 2][:limit]
        )
    ]
    total = sum(1 for s in comp_sizes.values() if s >= 2)

    headline = generate_headline("circles", circular, scope_label, detail)
    return AlgorithmResult(
        mission_id="circles", headline=headline, items=circular, total_count=total,
        coverage=coverage, method_plain=method["plain"],
        method_technical=method["technical"], next_steps=NEXT_STEPS["circles"],
        detail_level=detail,
    )


NEXT_STEPS: Dict[str, list] = {
    "groups": [
        {"label": "Find patients like one from a group", "target": "similar"},
        {"label": "Which conditions matter most in groups?", "target": "critical"},
    ],
    "similar": [
        {"label": "What groups do similar patients belong to?", "target": "groups"},
        {"label": "Which conditions are these patients missing?", "target": "missing"},
    ],
    "gaps": [
        {"label": "Find patients similar to the isolated ones", "target": "similar"},
        {"label": "Which conditions are isolated patients missing?",
         "target": "missing"},
    ],
    "circles": [
        {"label": "Are patients also falling through the gaps?", "target": "gaps"},
        {"label": "Which conditions drive circular patterns?", "target": "critical"},
    ],
}
