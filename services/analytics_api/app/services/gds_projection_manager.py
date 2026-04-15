"""GDS graph projection management for the Pathway Explorer research workspace.

Manages three named in-memory graph projections used by research algorithms:

  pe-patient-condition  -- Patient <-> SNOMED entity nodes (Layer A).
                           Native UNDIRECTED projection so Leiden / WCC work.
                           Includes all patient->condition relationship types.
  pe-condition-cooccur  -- Derived condition co-occurrence graph (Layer A).
                           Cypher projection (directed) used for PageRank,
                           Betweenness, Degree, Label Propagation.
                           Filters to active conditions only by default
                           (context='current', confidence >= 0.5).
                           Excludes HAS_FINDING/HAS_DISORDER (no properties)
                           and HAS_SITUATION (always historical by semantic tag).
  pe-patient-journey    -- Patient -> Encounter -> EpisodeOfCare (Layer A).
                           Cypher projection (directed) for SCC.
  pe-referral-network   -- GPPractice -> Organization referral / commissioning
                           network (Layer B).  Uses ReferralRequest when
                           available; falls back to RECORDED_AT + COMMISSIONED_BY
                           geography when ReferralRequest count < threshold.

GDS compatibility: graphdatascience >= 1.20, GDS server >= 2026.
Key API changes vs older versions:
  - gds.graph.cypher.project() takes ONE query ending in RETURN gds.graph.project(...)
  - orientation: 'UNDIRECTED' is NOT supported in Cypher projection config;
    use gds.graph.project() (native API) to get UNDIRECTED relationships.
  - Relationship properties key: 'relationshipProperties' (was 'properties').
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from libs.auth.org_scope import CallerScope
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)

PROJ_PATIENT_CONDITION = "pe-patient-condition"
PROJ_CONDITION_COOCCUR = "pe-condition-cooccur"
PROJ_PATIENT_JOURNEY = "pe-patient-journey"
PROJ_REFERRAL_NETWORK = "pe-referral-network"

_LAYER_A_PROJECTIONS = [
    PROJ_PATIENT_CONDITION,
    PROJ_CONDITION_COOCCUR,
    PROJ_PATIENT_JOURNEY,
]
_LAYER_B_PROJECTIONS = [PROJ_REFERRAL_NETWORK]

# All relationship types connecting Patient to SNOMED entity nodes.
# Used in the native UNDIRECTED projection (pe-patient-condition) for Leiden/WCC.
# Including all types intentionally -- Leiden benefits from historical patterns.
_PATIENT_CONDITION_RELS = [
    "HAS_CLINICAL_FINDING",  # 10,032 edges -- richest, has context + confidence
    "HAS_OBSERVABLE_ENTITY",  # 26,065 edges -- richest, has context + confidence
    "HAS_DISEASE",  # 826 edges -- has context + confidence
    "HAS_FINDING",  # 4,103 edges -- no properties (legacy)
    "HAS_DISORDER",  # 2,099 edges -- no properties (legacy)
    "HAS_PROCEDURE",  # 4,496 edges -- has context + confidence
    "HAS_SITUATION",  # 3,307 edges -- always historical by semantic tag
    "HAS_CONCEPT",  # 397 edges
]

# Relationship types used in the co-occurrence projection.
# Excludes legacy property-free types and HAS_SITUATION (always historical).
_COOCCUR_ACTIVE_RELS = [
    "HAS_CLINICAL_FINDING",
    "HAS_OBSERVABLE_ENTITY",
    "HAS_DISEASE",
    "HAS_PROCEDURE",
    "HAS_CONCEPT",
]

_MIN_REFERRAL_COUNT = 10


@dataclass
class ProjectionStatus:
    """Status of a single GDS projection."""

    name: str
    exists: bool
    node_count: int = 0
    relationship_count: int = 0
    layer: str = "A"
    data_available: bool = True
    unavailable_reason: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ProjectionSummary:
    """Summary of all projections for an org scope."""

    projections: List[ProjectionStatus] = field(default_factory=list)
    referral_data_available: bool = False
    referral_count: int = 0


# -- GDS client factory -------------------------------------------------------


def _gds_client(client: PatientGraphClient):  # noqa: ARG001
    """Return a GDS client wrapping the patient graph driver."""
    try:
        from graphdatascience import GraphDataScience

        uri = os.getenv("NEO4J_URI", "") or os.getenv("NEO4J_PATIENT_URI", "")
        user = (
            os.getenv("NEO4J_USER", "") or os.getenv("NEO4J_PATIENT_USER", "")
        )
        password = (
            os.getenv("NEO4J_PASSWORD", "")
            or os.getenv("NEO4J_PATIENT_PASSWORD", "")
        )
        return GraphDataScience(uri, auth=(user, password))
    except ImportError as exc:
        raise RuntimeError(
            "graphdatascience package not installed. "
            "Add graphdatascience>=1.20 to requirements.txt."
        ) from exc


# -- Public helpers -----------------------------------------------------------


def check_referral_data_available(
    client: PatientGraphClient,
) -> tuple[bool, int]:
    """Check whether ReferralRequest data exists in the graph."""
    try:
        rows = client.run(
            "MATCH (rr:ReferralRequest) RETURN count(rr) AS cnt LIMIT 1"
        )
        count = rows[0]["cnt"] if rows else 0
        return count >= _MIN_REFERRAL_COUNT, count
    except Exception as exc:
        logger.warning("Could not check referral data availability: %s", exc)
        return False, 0


def check_encounter_network_available(client: PatientGraphClient) -> bool:
    """Check whether RECORDED_AT + COMMISSIONED_BY edges exist for fallback."""
    try:
        rows = client.run(
            "MATCH ()-[:RECORDED_AT]->(:GPPractice)-[:COMMISSIONED_BY]->()"
            " RETURN count(*) AS cnt LIMIT 1"
        )
        cnt = rows[0]["cnt"] if rows else 0
        return isinstance(cnt, int) and cnt > 0
    except Exception as exc:
        logger.warning("Could not check encounter network availability: %s", exc)
        return False


def list_projections(
    client: PatientGraphClient,
    scope: CallerScope,
) -> ProjectionSummary:
    """List existing GDS projections and their stats."""
    gds = _gds_client(client)
    referral_available, referral_count = check_referral_data_available(client)
    statuses: List[ProjectionStatus] = []

    try:
        df = gds.graph.list()
        existing = set(df["graphName"].tolist()) if len(df) > 0 else set()
    except Exception as exc:
        logger.error("Failed to list GDS projections: %s", exc)
        existing = set()

    for name in _LAYER_A_PROJECTIONS + _LAYER_B_PROJECTIONS:
        layer = "B" if name in _LAYER_B_PROJECTIONS else "A"
        if name not in existing:
            statuses.append(
                ProjectionStatus(
                    name=name,
                    exists=False,
                    layer=layer,
                    data_available=(
                        referral_available if layer == "B" else True
                    ),
                    unavailable_reason=(
                        "No referral data loaded yet"
                        if layer == "B" and not referral_available
                        else None
                    ),
                )
            )
            continue
        try:
            g = gds.graph.get(name)
            statuses.append(
                ProjectionStatus(
                    name=name,
                    exists=True,
                    node_count=g.node_count(),
                    relationship_count=g.relationship_count(),
                    layer=layer,
                    data_available=True,
                )
            )
        except Exception as exc:
            statuses.append(
                ProjectionStatus(
                    name=name,
                    exists=True,
                    layer=layer,
                    data_available=True,
                    error=str(exc),
                )
            )

    try:
        gds.close()
    except Exception:
        pass

    return ProjectionSummary(
        projections=statuses,
        referral_data_available=referral_available,
        referral_count=referral_count,
    )


def create_projection(
    client: PatientGraphClient,
    scope: CallerScope,
    projection_name: str,
    confidence_min: float = 0.5,
    context_filter: str = "current",
) -> ProjectionStatus:
    """Create or refresh a named GDS projection.

    Args:
        client:           PatientGraphClient for the org.
        scope:            CallerScope for org-filtering.
        projection_name:  One of the PROJ_* constants.
        confidence_min:   Minimum confidence for co-occurrence edges (0.0-1.0).
        context_filter:   "current" (active conditions only) or "all".
    """
    # Data gate for Layer B: check both sources before connecting to GDS.
    if projection_name == PROJ_REFERRAL_NETWORK:
        gate_result = _check_referral_network_data(client)
        if gate_result is not None:
            return gate_result

    gds = _gds_client(client)
    try:
        _drop_if_exists(gds, projection_name)

        dispatch = {
            PROJ_PATIENT_CONDITION: _create_patient_condition,
            PROJ_CONDITION_COOCCUR: _create_condition_cooccur,
            PROJ_PATIENT_JOURNEY: _create_patient_journey,
            PROJ_REFERRAL_NETWORK: _create_referral_network,
        }
        creator = dispatch.get(projection_name)
        if creator is None:
            raise ValueError(f"Unknown projection: {projection_name!r}")

        if projection_name == PROJ_CONDITION_COOCCUR:
            status = creator(
                gds,
                client,
                scope,
                confidence_min=confidence_min,
                context_filter=context_filter,
            )
        else:
            status = creator(gds, client, scope)

        logger.info(
            "Created projection %s: %d nodes, %d rels",
            projection_name,
            status.node_count,
            status.relationship_count,
        )
        return status
    except Exception as exc:
        logger.error(
            "Failed to create projection %s: %s", projection_name, exc
        )
        layer = "B" if projection_name in _LAYER_B_PROJECTIONS else "A"
        return ProjectionStatus(
            name=projection_name,
            exists=False,
            layer=layer,
            data_available=True,
            error=str(exc),
        )
    finally:
        try:
            gds.close()
        except Exception:
            pass


def drop_projection(
    client: PatientGraphClient,
    projection_name: str,
) -> bool:
    """Drop a named GDS projection. Returns True if dropped."""
    gds = _gds_client(client)
    try:
        return _drop_if_exists(gds, projection_name)
    finally:
        try:
            gds.close()
        except Exception:
            pass


# -- Internal helpers ---------------------------------------------------------


def _drop_if_exists(gds, name: str) -> bool:
    """Drop a projection if it exists."""
    try:
        df = gds.graph.list()
        existing = set(df["graphName"].tolist()) if len(df) > 0 else set()
        if name in existing:
            gds.graph.drop(gds.graph.get(name))
            return True
        return False
    except Exception as exc:
        logger.warning("Could not drop projection %s: %s", name, exc)
        return False


def _scope_params(scope: CallerScope) -> Dict[str, Any]:
    """Return Cypher params dict for org-scoped queries."""
    return {"scope_org_ids": scope.org_ids} if not scope.is_admin else {}


def _build_scope_where(
    scope: CallerScope, patient_alias: str = "p"
) -> str:
    """Build a Cypher WHERE clause fragment for org-scoped patients."""
    if scope.is_admin:
        return ""
    return (
        f"WHERE EXISTS {{ "
        f"  ({patient_alias})-[:HAS_GENERAL_PRACTITIONER]->(gp) "
        f"  WHERE gp.id IN $scope_org_ids "
        f"}}"
    )


# -- Internal gate check ------------------------------------------------------


def _check_referral_network_data(
    client: PatientGraphClient,
) -> Optional[ProjectionStatus]:
    """Return a blocked status if no network data exists, else None.

    Checks both ReferralRequest and RECORDED_AT sources.  Returns None when
    at least one source is available so the caller can proceed.
    """
    referral_available, count = check_referral_data_available(client)
    if referral_available:
        return None
    encounter_available = check_encounter_network_available(client)
    if encounter_available:
        return None
    return ProjectionStatus(
        name=PROJ_REFERRAL_NETWORK,
        exists=False,
        layer="B",
        data_available=False,
        unavailable_reason=(
            f"No network data available (found {count} referral records, "
            f"need {_MIN_REFERRAL_COUNT}; no RECORDED_AT encounter edges found)"
        ),
    )


# LONG FUNCTION FILE: single-responsibility GDS projection module. All
# individual functions are within the 60-LOC limit. File exceeds 500 lines
# due to 9 projection builder functions + their Cypher query builders, all
# part of the same domain. Further splitting creates circular imports.

# -- Projection creators ------------------------------------------------------


def _create_patient_condition(
    gds,
    client: PatientGraphClient,
    scope: CallerScope,
) -> ProjectionStatus:
    """Native UNDIRECTED projection: Patient <-> SNOMED entity nodes.

    Uses gds.graph.project() (native API) so relationships can be marked
    UNDIRECTED -- required for Leiden community detection.
    Includes all patient->condition relationship types ordered by richness.
    """
    rel_types = {
        rt: {"orientation": "UNDIRECTED"} for rt in _PATIENT_CONDITION_RELS
    }
    node_types = {
        "Patient": {},
        "Clinical_finding": {},
        "Disease": {},
        "Observable_entity": {},
        "Procedure": {},
        "Situation": {},
        "SnomedConcept": {},
    }
    # Org-scoped native projections are handled by post-filtering on results
    # because native projection does not support parameterised WHERE clauses.
    # For admin scope this is a no-op.
    g, result = gds.graph.project(
        PROJ_PATIENT_CONDITION, node_types, rel_types
    )
    return ProjectionStatus(
        name=PROJ_PATIENT_CONDITION,
        exists=True,
        node_count=g.node_count(),
        relationship_count=g.relationship_count(),
        layer="A",
        data_available=True,
    )


def _build_cooccur_query(
    scope: CallerScope,
    context_filter: str = "current",
    confidence_min: float = 0.5,
) -> tuple[str, Dict[str, Any]]:
    """Build the Cypher projection query for condition co-occurrence.

    Uses _COOCCUR_ACTIVE_RELS (excludes legacy property-free types and
    HAS_SITUATION which is always historical).  Optionally filters to
    context='current' and a minimum confidence threshold.

    Args:
        scope:           CallerScope for org-filtering.
        context_filter:  "current" (active only) or "all" (include historical).
        confidence_min:  Min confidence on both relationship ends (default 0.5).
    """
    scope_where = _build_scope_where(scope)
    scope_params = _scope_params(scope)
    rels = "|".join(_COOCCUR_ACTIVE_RELS)

    context_clause = (
        "AND (r1.context IS NULL OR r1.context = 'current') "
        "AND (r2.context IS NULL OR r2.context = 'current') "
        if context_filter == "current"
        else ""
    )
    conf_clause = (
        "AND coalesce(r1.confidence, 1.0) >= $confidence_min "
        "AND coalesce(r2.confidence, 1.0) >= $confidence_min "
        if confidence_min > 0
        else ""
    )

    # UNION ALL projects both directions so graph is effectively undirected.
    # PageRank / Betweenness / Degree all work on this bidirectional repr.
    branch = (
        f"MATCH (p:Patient) {scope_where} "
        f"MATCH (p)-[r1:{rels}]->(e1) "
        f"MATCH (p)-[r2:{rels}]->(e2) "
        f"WHERE id(e1) < id(e2) {context_clause}{conf_clause}"
        "WITH e1, e2, count(DISTINCT p) AS weight WHERE weight >= 2 "
    )
    query = (
        "CALL { "
        + branch
        + "RETURN e1, e2, weight "
        "UNION ALL "
        + branch
        + "RETURN e2 AS e1, e1 AS e2, weight "
        "} "
        "RETURN gds.graph.project("
        "  $graph_name, e1, e2, {"
        "    sourceNodeLabels: labels(e1),"
        "    targetNodeLabels: labels(e2),"
        "    relationshipType: 'CO_OCCURS_WITH',"
        "    relationshipProperties: {weight: weight}"
        "  })"
    )
    extra: Dict[str, Any] = {}
    if confidence_min > 0:
        extra["confidence_min"] = confidence_min
    return query, {**scope_params, "graph_name": PROJ_CONDITION_COOCCUR, **extra}


def _create_condition_cooccur(
    gds,
    client: PatientGraphClient,
    scope: CallerScope,
    context_filter: str = "current",
    confidence_min: float = 0.5,
) -> ProjectionStatus:
    """Cypher projection: SNOMED entity co-occurrence weighted graph."""
    query, params = _build_cooccur_query(scope, context_filter, confidence_min)
    g, result = gds.graph.cypher.project(query, **params)
    return ProjectionStatus(
        name=PROJ_CONDITION_COOCCUR,
        exists=True,
        node_count=g.node_count(),
        relationship_count=g.relationship_count(),
        layer="A",
        data_available=True,
    )


def _create_patient_journey(
    gds,
    client: PatientGraphClient,
    scope: CallerScope,
) -> ProjectionStatus:
    """Cypher projection: Patient -> Encounter -> EpisodeOfCare pathway."""
    scope_params = _scope_params(scope)
    query = (
        "MATCH (source)-[r]->(target) "
        "WHERE (source:Patient AND target:Encounter "
        "       AND type(r) = 'HAS_ENCOUNTER') "
        "   OR (source:Encounter AND target:EpisodeOfCare "
        "       AND type(r) = 'IS_PART_OF') "
        "RETURN gds.graph.project("
        "  $graph_name, source, target, {"
        "    sourceNodeLabels: labels(source),"
        "    targetNodeLabels: labels(target),"
        "    relationshipType: type(r)"
        "  })"
    )
    g, result = gds.graph.cypher.project(
        query, graph_name=PROJ_PATIENT_JOURNEY, **scope_params
    )
    return ProjectionStatus(
        name=PROJ_PATIENT_JOURNEY,
        exists=True,
        node_count=g.node_count(),
        relationship_count=g.relationship_count(),
        layer="A",
        data_available=True,
    )


def _create_referral_network(
    gds,
    client: PatientGraphClient,
    scope: CallerScope,
) -> ProjectionStatus:
    """Cypher projection: GPPractice -> Organization referral / commissioning.

    Primary path: ReferralRequest-based network (referral volume as weight).
    Fallback:     RECORDED_AT + COMMISSIONED_BY when ReferralRequest is absent
                  (encounter volume as weight -- shows practice load distribution).

    Data availability is pre-checked by create_projection before this is called.
    """
    referral_available, _ = check_referral_data_available(client)
    if referral_available:
        return _create_referral_network_primary(gds, client, scope)
    return _create_referral_network_fallback(gds, client, scope)


def _create_referral_network_primary(
    gds,
    client: PatientGraphClient,
    scope: CallerScope,
) -> ProjectionStatus:
    """ReferralRequest-based referral network projection."""
    scope_params = _scope_params(scope)
    scope_where = _build_scope_where(scope, patient_alias="p")

    query = (
        "MATCH (rr:ReferralRequest)-[:FOR_PATIENT]->(p:Patient) "
        f"{scope_where} "
        "MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp:GPPractice) "
        "MATCH (rr)-[:IN_WORKFLOW]->(w:Workflow)"
        "<-[:HAS_WORKFLOW]-(s:Service) "
        "-[:PROVIDES_SERVICE_FOR]->(org:Organization) "
        "WITH gp, org, count(rr) AS weight "
        "RETURN gds.graph.project("
        "  $graph_name, gp, org, {"
        "    sourceNodeLabels: ['GPPractice'],"
        "    targetNodeLabels: ['Organization'],"
        "    relationshipType: 'REFERRED_TO',"
        "    relationshipProperties: {weight: weight}"
        "  })"
    )
    g, _ = gds.graph.cypher.project(
        query, graph_name=PROJ_REFERRAL_NETWORK, **scope_params
    )
    return ProjectionStatus(
        name=PROJ_REFERRAL_NETWORK,
        exists=True,
        node_count=g.node_count(),
        relationship_count=g.relationship_count(),
        layer="B",
        data_available=True,
    )


def _create_referral_network_fallback(
    gds,
    client: PatientGraphClient,
    scope: CallerScope,
) -> ProjectionStatus:
    """RECORDED_AT + COMMISSIONED_BY fallback when ReferralRequest is absent.

    Creates a GPPractice -> Organization commissioning network where
    weight = number of encounters recorded at the practice.  Useful for
    understanding practice load distribution even without referral data.
    """
    scope_params = _scope_params(scope)

    query = (
        "MATCH (e:Encounter)-[:RECORDED_AT]->(gp:GPPractice) "
        "MATCH (gp)-[:COMMISSIONED_BY]->(org:Organization) "
        "WITH gp, org, count(DISTINCT e) AS weight "
        "RETURN gds.graph.project("
        "  $graph_name, gp, org, {"
        "    sourceNodeLabels: ['GPPractice'],"
        "    targetNodeLabels: ['Organization'],"
        "    relationshipType: 'COMMISSIONED_BY',"
        "    relationshipProperties: {weight: weight}"
        "  })"
    )
    g, _ = gds.graph.cypher.project(
        query, graph_name=PROJ_REFERRAL_NETWORK, **scope_params
    )
    return ProjectionStatus(
        name=PROJ_REFERRAL_NETWORK,
        exists=True,
        node_count=g.node_count(),
        relationship_count=g.relationship_count(),
        layer="B",
        data_available=True,
    )
