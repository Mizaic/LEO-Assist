"""Shared data types and helper functions for the Pathway Explorer algorithm runner.

Atlas trace:
  DO: DO-D5B9FE5F
  DI: DI-6E1B71A4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-D5B9FE5F")

Consumed by algorithm_runner.py, algorithm_runner_patient.py, and
algorithm_runner_condition.py.  Kept separate to avoid circular imports.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from libs.auth.org_scope import CallerScope
from libs.neo4j_client.client import PatientGraphClient
from services.analytics_api.app.services.gds_projection_manager import (
    create_projection,
)

logger = logging.getLogger(__name__)

_DETAIL_LIMITS = {"summary": 10, "detailed": 50, "everything": 500}
_DETAIL_GRANULARITY = {
    "summary": "aggregated",
    "detailed": "individual",
    "everything": "full",
}


@dataclass
class AlgorithmResult:
    """Structured result from a Pathway Explorer mission run."""

    mission_id: str
    headline: str
    items: List[Dict[str, Any]]
    total_count: int
    coverage: "CoverageInfo"
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


# -- Scope helpers ------------------------------------------------------------


def _build_scope_label(area: str, period: str) -> str:
    """Human-readable scope description for headlines."""
    period_labels = {
        "3m": "last 3 months",
        "6m": "last 6 months",
        "12m": "last 12 months",
    }
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
    prac_part = (
        f" across {prac} practice{'s' if prac != 1 else ''}" if prac else ""
    )
    base = f"Based on {pat:,} patients{prac_part}."
    if confidence == "low":
        return base + " Results may not represent the full picture."
    return base


# -- Projection helpers -------------------------------------------------------


def _ensure_projection(
    client: PatientGraphClient,
    scope: CallerScope,
    projection_name: str,
    confidence_min: float = 0.5,
    context_filter: str = "current",
) -> None:
    """Create projection if it does not already exist."""
    from services.analytics_api.app.services.gds_projection_manager import (
        list_projections,
    )

    summary = list_projections(client, scope)
    existing = {p.name for p in summary.projections if p.exists}
    if projection_name not in existing:
        create_projection(
            client,
            scope,
            projection_name,
            confidence_min=confidence_min,
            context_filter=context_filter,
        )


def _gds_client_from_env():
    """Return a GDS client for the patient graph."""
    from graphdatascience import GraphDataScience

    uri = os.getenv("NEO4J_URI", "") or os.getenv("NEO4J_PATIENT_URI", "")
    user = os.getenv("NEO4J_USER", "") or os.getenv("NEO4J_PATIENT_USER", "")
    password = (
        os.getenv("NEO4J_PASSWORD", "") or os.getenv("NEO4J_PATIENT_PASSWORD", "")
    )
    return GraphDataScience(uri, auth=(user, password))


# -- Enrichment helpers -------------------------------------------------------


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
            "       coalesce(e.preferredTerm, e.fsn, "
            "               toString(e.conceptId), toString(id(e))) AS label",
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


def _enrich_leiden_communities(
    client: PatientGraphClient,
    community_map: Dict[int, List[int]],
    top_n: int = 3,
) -> Dict[int, Dict[str, Any]]:
    """Return per-community demographic summary and top condition names.

    Args:
        client:        PatientGraphClient for Cypher queries.
        community_map: Mapping of communityId -> list of GDS nodeIds.
        top_n:         Number of top conditions to include per community.
    """
    all_ids = [nid for nids in community_map.values() for nid in nids]
    if not all_ids:
        return {}

    try:
        patient_rows = client.run(
            "MATCH (p:Patient) WHERE id(p) IN $ids "
            "RETURN id(p) AS nid, p.gender AS gender, "
            "       duration.inYears(date(p.birthDate), date()).years AS age",
            ids=all_ids,
        )
        patient_data: Dict[int, Any] = {r["nid"]: r for r in patient_rows}
    except Exception as exc:
        logger.warning("Leiden patient enrichment failed: %s", exc)
        patient_data = {}

    try:
        cond_rows = client.run(
            "MATCH (n) WHERE id(n) IN $ids AND NOT n:Patient "
            "RETURN id(n) AS nid, "
            "       coalesce(n.name, n.preferredTerm, "
            "                toString(n.conceptId)) AS name",
            ids=all_ids,
        )
        condition_data: Dict[int, str] = {r["nid"]: r["name"] for r in cond_rows}
    except Exception as exc:
        logger.warning("Leiden condition enrichment failed: %s", exc)
        condition_data = {}

    enriched: Dict[int, Dict[str, Any]] = {}
    for cid, node_ids in community_map.items():
        patients = [patient_data[n] for n in node_ids if n in patient_data]
        conditions = [condition_data[n] for n in node_ids if n in condition_data]
        if not patients:
            enriched[cid] = {"patient_count": 0}
            continue
        ages = [p["age"] for p in patients if p.get("age") is not None]
        female = sum(1 for p in patients if p.get("gender") == "female")
        enriched[cid] = {
            "patient_count": len(patients),
            "pct_female": round(female / len(patients) * 100),
            "age_min": min(ages) if ages else None,
            "age_max": max(ages) if ages else None,
            "top_conditions": conditions[:top_n],
        }
    return enriched


def _enrich_evidence_text(
    client: PatientGraphClient,
    items: List[Dict[str, Any]],
    id_key: str = "node_id",
) -> List[Dict[str, Any]]:
    """Add top_evidence snippet from HAS_CLINICAL_FINDING for each condition."""
    node_ids = [item[id_key] for item in items if item.get(id_key) is not None]
    if not node_ids:
        return items
    try:
        rows = client.run(
            "MATCH ()-[r:HAS_CLINICAL_FINDING]->(n) "
            "WHERE id(n) IN $ids AND r.evidence IS NOT NULL "
            "WITH id(n) AS nid, r.evidence AS ev, "
            "     coalesce(r.confidence, 0.5) AS conf "
            "ORDER BY conf DESC "
            "WITH nid, collect(ev)[0] AS top_evidence "
            "RETURN nid, top_evidence",
            ids=node_ids,
        )
        ev_map = {r["nid"]: r["top_evidence"] for r in rows}
        for item in items:
            nid = item.get(id_key)
            if nid in ev_map:
                item["top_evidence"] = ev_map[nid]
    except Exception as exc:
        logger.warning("Evidence text enrichment failed: %s", exc)
    return items
