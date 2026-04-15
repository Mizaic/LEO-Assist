"""GDS graph projection management for the Pathway Explorer research workspace.

Manages four named in-memory graph projections used by research algorithms:

  patient-condition   -- Patient <-> SNOMED entity nodes (Layer A, available now)
  condition-cooccur   -- Derived condition co-occurrence graph (Layer A)
  patient-journey     -- Patient -> Encounter -> EpisodeOfCare (Layer A)
  referral-network    -- GPPractice -> Organization via ReferralRequest (Layer B, data-gated)

Projections are org-scoped so multi-tenant data never leaks across boundaries.
Admins get unscoped projections across all orgs.

GDS Python client docs:
  https://neo4j.com/docs/graph-data-science-client/current/
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from libs.auth.org_scope import CallerScope
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)

# Projection names - kept short to fit GDS naming limits.
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

# Minimum patient count before we consider Layer B data available.
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


def _gds_client(client: PatientGraphClient):
    """Return a GDS client wrapping the patient graph driver."""
    try:
        from graphdatascience import GraphDataScience

        uri = (
            os.getenv("NEO4J_URI", "")
            or os.getenv("NEO4J_PATIENT_URI", "")
        )
        user = (
            os.getenv("NEO4J_USER", "")
            or os.getenv("NEO4J_PATIENT_USER", "")
        )
        password = (
            os.getenv("NEO4J_PASSWORD", "")
            or os.getenv("NEO4J_PATIENT_PASSWORD", "")
        )
        return GraphDataScience(uri, auth=(user, password))
    except ImportError as exc:
        raise RuntimeError(
            "graphdatascience package not installed. "
            "Add graphdatascience>=1.10 to requirements.txt."
        ) from exc


def _org_filter(scope: CallerScope) -> str:
    """Return a Cypher WHERE fragment for org-scoped patient filtering."""
    if scope.is_admin:
        return ""
    return (
        "WHERE EXISTS { "
        "  (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
        "  WHERE gp.id IN $scope_org_ids "
        "}"
    )


def check_referral_data_available(client: PatientGraphClient) -> tuple[bool, int]:
    """Check whether ReferralRequest data exists in the graph.

    Returns (available, count) tuple.  Count is capped at 1000 for speed.
    """
    try:
        rows = client.run(
            "MATCH (rr:ReferralRequest) RETURN count(rr) AS cnt LIMIT 1"
        )
        count = rows[0]["cnt"] if rows else 0
        return count >= _MIN_REFERRAL_COUNT, count
    except Exception as exc:
        logger.warning("Could not check referral data availability: %s", exc)
        return False, 0


def list_projections(
    client: PatientGraphClient,
    scope: CallerScope,
) -> ProjectionSummary:
    """List existing GDS projections and their stats."""
    gds = _gds_client(client)
    referral_available, referral_count = check_referral_data_available(client)
    statuses: List[ProjectionStatus] = []

    try:
        existing = {row["graphName"] for row in gds.graph.list().to_dict("records")}
    except Exception as exc:
        logger.error("Failed to list GDS projections: %s", exc)
        existing = set()

    all_names = _LAYER_A_PROJECTIONS + _LAYER_B_PROJECTIONS
    for name in all_names:
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
) -> ProjectionStatus:
    """Create or refresh a named GDS projection.

    Drops the existing projection first if it exists, then recreates it.
    """
    if projection_name in _LAYER_B_PROJECTIONS:
        available, count = check_referral_data_available(client)
        if not available:
            return ProjectionStatus(
                name=projection_name,
                exists=False,
                layer="B",
                data_available=False,
                unavailable_reason=(
                    f"Referral data not yet available "
                    f"(found {count} records, need {_MIN_REFERRAL_COUNT})"
                ),
            )

    gds = _gds_client(client)
    try:
        _drop_if_exists(gds, projection_name)

        if projection_name == PROJ_PATIENT_CONDITION:
            status = _create_patient_condition(gds, client, scope)
        elif projection_name == PROJ_CONDITION_COOCCUR:
            status = _create_condition_cooccur(gds, client, scope)
        elif projection_name == PROJ_PATIENT_JOURNEY:
            status = _create_patient_journey(gds, client, scope)
        elif projection_name == PROJ_REFERRAL_NETWORK:
            status = _create_referral_network(gds, client, scope)
        else:
            raise ValueError(f"Unknown projection: {projection_name!r}")

        logger.info(
            "Created projection %s: %d nodes, %d rels",
            projection_name,
            status.node_count,
            status.relationship_count,
        )
        return status
    except Exception as exc:
        logger.error("Failed to create projection %s: %s", projection_name, exc)
        return ProjectionStatus(
            name=projection_name,
            exists=False,
            layer="B" if projection_name in _LAYER_B_PROJECTIONS else "A",
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
    """Drop a named GDS projection. Returns True if dropped, False if not found."""
    gds = _gds_client(client)
    try:
        dropped = _drop_if_exists(gds, projection_name)
        return dropped
    finally:
        try:
            gds.close()
        except Exception:
            pass


def _drop_if_exists(gds, name: str) -> bool:
    """Drop a projection if it exists. Returns True if it was dropped."""
    try:
        existing_names = {
            row["graphName"] for row in gds.graph.list().to_dict("records")
        }
        if name in existing_names:
            gds.graph.drop(gds.graph.get(name))
            return True
        return False
    except Exception as exc:
        logger.warning("Could not drop projection %s: %s", name, exc)
        return False


def _scope_params(scope: CallerScope) -> Dict[str, Any]:
    """Return params dict for org-scoped Cypher queries."""
    return {"scope_org_ids": scope.org_ids} if not scope.is_admin else {}


def _build_scope_where(scope: CallerScope, patient_alias: str = "p") -> str:
    """Build a Cypher WHERE fragment for org-scoped patients."""
    if scope.is_admin:
        return ""
    return (
        f"WHERE EXISTS {{ "
        f"  ({patient_alias})-[:HAS_GENERAL_PRACTITIONER]->(gp) "
        f"  WHERE gp.id IN $scope_org_ids "
        f"}}"
    )


def _create_patient_condition(
    gds,
    client: PatientGraphClient,
    scope: CallerScope,
) -> ProjectionStatus:
    """Project Patient <-> SNOMED entity bipartite graph."""
    scope_params = _scope_params(scope)
    scope_where = _build_scope_where(scope)

    # Node query: patients in scope + all SNOMED entity node types
    node_q = (
        f"MATCH (p:Patient) {scope_where} RETURN id(p) AS id, labels(p) AS labels "
        "UNION ALL "
        "MATCH (e) WHERE e:Clinical_finding OR e:Disease OR e:Observable_entity "
        "  OR e:Procedure OR e:Situation OR e:SnomedConcept "
        "RETURN id(e) AS id, labels(e) AS labels"
    )

    # Relationship query: patient -> condition edges
    rel_q = (
        f"MATCH (p:Patient) {scope_where} "
        "MATCH (p)-[r:HAS_FINDING|HAS_DISORDER|HAS_OBSERVABLE|HAS_PROCEDURE|"
        "       HAS_SITUATION|HAS_CONCEPT]->(e) "
        "RETURN id(p) AS source, id(e) AS target, type(r) AS type"
    )

    g, result = gds.graph.cypher.project(
        PROJ_PATIENT_CONDITION,
        node_q,
        rel_q,
        **scope_params,
    )
    return ProjectionStatus(
        name=PROJ_PATIENT_CONDITION,
        exists=True,
        node_count=g.node_count(),
        relationship_count=g.relationship_count(),
        layer="A",
        data_available=True,
    )


def _create_condition_cooccur(
    gds,
    client: PatientGraphClient,
    scope: CallerScope,
) -> ProjectionStatus:
    """Build condition co-occurrence graph from shared patient coding.

    Two SNOMED entity nodes are connected with weight = number of patients
    that have both coded.  Excludes very rare co-occurrences (< 2 patients).
    """
    scope_where = _build_scope_where(scope)
    scope_params = _scope_params(scope)

    # Materialise co-occurrence pairs via Cypher before projecting.
    # We collect entity IDs and weights first, then project the subgraph.
    cooccur_q = (
        f"MATCH (p:Patient) {scope_where} "
        "MATCH (p)-[:HAS_FINDING|HAS_DISORDER|HAS_OBSERVABLE|HAS_PROCEDURE|"
        "       HAS_SITUATION|HAS_CONCEPT]->(e1) "
        "MATCH (p)-[:HAS_FINDING|HAS_DISORDER|HAS_OBSERVABLE|HAS_PROCEDURE|"
        "       HAS_SITUATION|HAS_CONCEPT]->(e2) "
        "WHERE id(e1) < id(e2) "
        "WITH e1, e2, count(DISTINCT p) AS weight "
        "WHERE weight >= 2 "
        "RETURN id(e1) AS source, id(e2) AS target, weight"
    )

    node_q = (
        "MATCH (e) WHERE e:Clinical_finding OR e:Disease OR e:Observable_entity "
        "  OR e:Procedure OR e:Situation OR e:SnomedConcept "
        "RETURN id(e) AS id, labels(e) AS labels"
    )

    # Use Cypher aggregation projection for weighted edges
    g, result = gds.graph.cypher.project(
        PROJ_CONDITION_COOCCUR,
        node_q,
        cooccur_q,
        **scope_params,
    )
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
    """Project Patient -> Encounter -> EpisodeOfCare pathway graph."""
    scope_where = _build_scope_where(scope)
    scope_params = _scope_params(scope)

    node_q = (
        f"MATCH (p:Patient) {scope_where} "
        "RETURN id(p) AS id, labels(p) AS labels "
        "UNION ALL "
        f"MATCH (p:Patient) {scope_where} "
        "MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter) "
        "RETURN id(e) AS id, labels(e) AS labels "
        "UNION ALL "
        f"MATCH (p:Patient) {scope_where} "
        "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
        "RETURN id(ep) AS id, labels(ep) AS labels"
    )

    rel_q = (
        f"MATCH (p:Patient) {scope_where} "
        "MATCH (p)-[r:HAS_ENCOUNTER]->(e:Encounter) "
        "RETURN id(p) AS source, id(e) AS target, type(r) AS type "
        "UNION ALL "
        f"MATCH (p:Patient) {scope_where} "
        "MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:IS_PART_OF]->(ep:EpisodeOfCare) "
        "RETURN id(e) AS source, id(ep) AS target, type(r) AS type"
    )

    g, result = gds.graph.cypher.project(
        PROJ_PATIENT_JOURNEY,
        node_q,
        rel_q,
        **scope_params,
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
    """Project GPPractice -> Organization referral network.

    Derives weighted org-to-org edges from the multi-hop path:
    GPPractice <- Patient <- ReferralRequest -> Workflow <- Service -> Organization
    """
    scope_params = _scope_params(scope)
    scope_where = _build_scope_where(scope, patient_alias="p")

    node_q = (
        "MATCH (o) WHERE o:GPPractice OR o:Organization "
        "RETURN id(o) AS id, labels(o) AS labels"
    )

    rel_q = (
        "MATCH (rr:ReferralRequest)-[:FOR_PATIENT]->(p:Patient) "
        f"{scope_where} "
        "MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp:GPPractice) "
        "MATCH (rr)-[:IN_WORKFLOW]->(w:Workflow)<-[:HAS_WORKFLOW]-(s:Service) "
        "-[:PROVIDES_SERVICE_FOR]->(org:Organization) "
        "WITH gp, org, count(rr) AS weight "
        "RETURN id(gp) AS source, id(org) AS target, weight"
    )

    g, result = gds.graph.cypher.project(
        PROJ_REFERRAL_NETWORK,
        node_q,
        rel_q,
        **scope_params,
    )
    return ProjectionStatus(
        name=PROJ_REFERRAL_NETWORK,
        exists=True,
        node_count=g.node_count(),
        relationship_count=g.relationship_count(),
        layer="B",
        data_available=True,
    )
