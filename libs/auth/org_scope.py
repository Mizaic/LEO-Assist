"""Org-scoped access control for multi-tenant NHS cancer audit platform.

Resolves a caller's email to their organizational scope using the Neo4j
Practitioner/WORKS_AT graph.  Platform admins bypass all scope checks.

Org hierarchy:
    (GPPractice)-[:COMMISSIONED_BY]->(ICB)-[:PART_OF_ALLIANCE]->(CancerAlliance)
    (Practitioner)-[:WORKS_AT]->(GPPractice | ICB | CancerAlliance)

Usage in FastAPI endpoints::

    from libs.auth.org_scope import CallerScope, get_caller_scope

    @router.get("/things")
    def list_things(scope: CallerScope = Depends(get_caller_scope)):
        ...
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Literal, Optional

from fastapi import Header, HTTPException

from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger("libs.auth.org_scope")

ScopeType = Literal["gp", "icb", "alliance"]

_LABEL_TO_SCOPE: dict[str, ScopeType] = {
    "GPPractice": "gp",
    "ICB": "icb",
    "CancerAlliance": "alliance",
}

# Reusable Cypher fragment that restricts patients to an org hierarchy.
# Expects ``$scope_org_ids`` parameter (list of org IDs).
# Binds: ``p`` (Patient), ``_gp`` (GPPractice or Organization).
ORG_PATIENT_FILTER = (
    "EXISTS { "
    "  MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(_gp) "
    "  WHERE _gp.id IN $scope_org_ids "
    "}"
)


@dataclass(frozen=True)
class CallerScope:
    """Resolved caller identity and organizational visibility."""

    email: str
    is_admin: bool
    org_ids: List[str] = field(default_factory=list)
    scope_type: Optional[ScopeType] = None
    primary_org_id: Optional[str] = None

    def to_query_params(self) -> dict:
        """Return params dict suitable for Cypher query injection."""
        return {"scope_org_ids": self.org_ids}


def resolve_caller_scope(
    client: PatientGraphClient,
    email: str,
) -> CallerScope:
    """Resolve a user email to their full organizational scope.

    For GP users: returns the GP id + parent ICB + parent Alliance.
    For ICB users: returns the ICB id + all child GPs + parent Alliance.
    For Alliance users: returns the Alliance id + all child ICBs + all child GPs.
    Platform admins: is_admin=True, empty org_ids (meaning unrestricted).
    """
    normalized = email.lower().strip()

    practitioner = client.run(
        "MATCH (pr:Practitioner {email: $email}) "
        "RETURN pr.id AS id, pr.email AS email, "
        "       pr.is_platform_admin AS is_platform_admin",
        email=normalized,
    )
    if not practitioner:
        raise HTTPException(status_code=401, detail="Unknown user")

    user = practitioner[0]
    is_admin = bool(user.get("is_platform_admin", False))

    if is_admin:
        return CallerScope(
            email=normalized,
            is_admin=True,
            org_ids=[],
            scope_type=None,
            primary_org_id=None,
        )

    # Fetch the org the practitioner WORKS_AT and determine scope type.
    orgs = client.run(
        "MATCH (pr:Practitioner {email: $email})-[:WORKS_AT]->(o) "
        "WHERE o:GPPractice OR o:ICB OR o:CancerAlliance OR o:Organization "
        "RETURN o.id AS id, labels(o) AS nodeLabels",
        email=normalized,
    )
    if not orgs:
        raise HTTPException(
            status_code=403,
            detail="User has no organization assignment",
        )

    primary = orgs[0]
    primary_id: str = primary["id"]
    labels = primary.get("nodeLabels") or []
    scope_type: ScopeType = "gp"
    for label in labels:
        if label in _LABEL_TO_SCOPE:
            scope_type = _LABEL_TO_SCOPE[label]
            break

    # Expand to all orgs in the hierarchy visible from this scope level.
    if scope_type == "gp":
        all_ids = _expand_gp_scope(client, primary_id)
    elif scope_type == "icb":
        all_ids = _expand_icb_scope(client, primary_id)
    else:
        all_ids = _expand_alliance_scope(client, primary_id)

    return CallerScope(
        email=normalized,
        is_admin=False,
        org_ids=all_ids,
        scope_type=scope_type,
        primary_org_id=primary_id,
    )


def _expand_gp_scope(client: PatientGraphClient, gp_id: str) -> list[str]:
    """GP scope: own GP + parent ICB + grandparent Alliance."""
    rows = client.run(
        "MATCH (gp {id: $gp_id}) "
        "OPTIONAL MATCH (gp)-[:COMMISSIONED_BY]->(icb:ICB) "
        "OPTIONAL MATCH (icb)-[:PART_OF_ALLIANCE]->(ca:CancerAlliance) "
        "RETURN gp.id AS gp_id, icb.id AS icb_id, ca.id AS ca_id",
        gp_id=gp_id,
    )
    ids = {gp_id}
    if rows:
        if rows[0].get("icb_id"):
            ids.add(rows[0]["icb_id"])
        if rows[0].get("ca_id"):
            ids.add(rows[0]["ca_id"])
    return list(ids)


def _expand_icb_scope(client: PatientGraphClient, icb_id: str) -> list[str]:
    """ICB scope: own ICB + all child GPs + parent Alliance."""
    rows = client.run(
        "MATCH (icb:ICB {id: $icb_id}) "
        "OPTIONAL MATCH (gp:GPPractice)-[:COMMISSIONED_BY]->(icb) "
        "OPTIONAL MATCH (icb)-[:PART_OF_ALLIANCE]->(ca:CancerAlliance) "
        "RETURN collect(DISTINCT gp.id) AS gp_ids, ca.id AS ca_id",
        icb_id=icb_id,
    )
    ids = {icb_id}
    if rows:
        for gid in (rows[0].get("gp_ids") or []):
            if gid:
                ids.add(gid)
        if rows[0].get("ca_id"):
            ids.add(rows[0]["ca_id"])
    return list(ids)


def _expand_alliance_scope(client: PatientGraphClient, ca_id: str) -> list[str]:
    """Alliance scope: own Alliance + all child ICBs + all grandchild GPs."""
    rows = client.run(
        "MATCH (ca:CancerAlliance {id: $ca_id}) "
        "OPTIONAL MATCH (icb:ICB)-[:PART_OF_ALLIANCE]->(ca) "
        "OPTIONAL MATCH (gp:GPPractice)-[:COMMISSIONED_BY]->(icb) "
        "RETURN collect(DISTINCT icb.id) AS icb_ids, "
        "       collect(DISTINCT gp.id) AS gp_ids",
        ca_id=ca_id,
    )
    ids = {ca_id}
    if rows:
        for iid in (rows[0].get("icb_ids") or []):
            if iid:
                ids.add(iid)
        for gid in (rows[0].get("gp_ids") or []):
            if gid:
                ids.add(gid)
    return list(ids)


def get_caller_scope(
    leo_session: Optional[str] = Header(default=None, alias="X-Leo-Session"),
) -> CallerScope:
    """FastAPI dependency that resolves the caller's org scope from session.

    GAP-001: X-User-Email header and ?email= query param removed.
    Prefer using app.deps.get_caller_scope_from_request in service routers,
    which reads from the secure session cookie. This function is kept for
    internal callers that pass the session token via X-Leo-Session header.
    """
    if not leo_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from app.services.session_store import load_session
    data = load_session(leo_session) or {}
    caller_email = (data.get("email") or "").strip().lower()
    if not caller_email:
        raise HTTPException(status_code=401, detail="Session has no user email")
    client = PatientGraphClient()
    try:
        return resolve_caller_scope(client, caller_email)
    finally:
        client.close()


def require_patient_in_scope(
    client: PatientGraphClient,
    scope: CallerScope,
    patient_id: str,
) -> None:
    """Raise 404 if the patient is not visible to the caller.

    Admins always pass.  For scoped users, checks that the patient's GP
    is within the caller's org_ids.
    """
    if scope.is_admin:
        return
    rows = client.run(
        "MATCH (p:Patient) WHERE toString(p.id) = $pid "
        "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
        "RETURN gp.id AS gp_id",
        pid=patient_id,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Patient not found")
    gp_id = rows[0].get("gp_id")
    if gp_id not in scope.org_ids:
        raise HTTPException(status_code=404, detail="Patient not found")
