"""Org-scoped access control for multi-tenant NHS cancer audit platform.

Atlas trace:
  DO: DO-DB7F8D52
  DI: DI-4DBE1A18, DI-87CCCB18
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-DB7F8D52")

Resolves a caller's email to their organizational scope using the Neo4j
Practitioner/WORKS_AT graph.  Platform admins bypass all scope checks.

Org hierarchy:
    (GPPractice)-[:PART_OF_PCN]->(PCN)-[:COMMISSIONED_BY]->(ICB)-[:PART_OF_ALLIANCE]->(CancerAlliance)
    (GPPractice)-[:COMMISSIONED_BY]->(ICB)  # direct link still supported
    (Practitioner)-[:WORKS_AT]->(GPPractice | PCN | ICB | CancerAlliance)

Usage in FastAPI endpoints::

    from libs.auth.org_scope import CallerScope, get_caller_scope

    @router.get("/things")
    def list_things(scope: CallerScope = Depends(get_caller_scope)):
        ...
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any, List, Literal, Optional

from fastapi import Header, HTTPException

from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger("libs.auth.org_scope")

# Local-dev only bypass for get_caller_scope. When set to "true" the dependency
# returns an unrestricted admin CallerScope without consulting Redis sessions.
# Mirrors the pattern in libs/auth/service_auth.py for inter-service auth.
# MUST stay false in any deployed environment (dev/val/prod). Opt-in is
# explicit and centralised here so a single grep finds every callsite.
_LOCAL_DEV_BYPASS_ENV = "LEO_LOCAL_DEV_BYPASS"
_LOCAL_DEV_BYPASS_EMAIL = "local-dev@leo.local"


def _local_dev_bypass_enabled() -> bool:
    return os.environ.get(_LOCAL_DEV_BYPASS_ENV, "").strip().lower() == "true"


ScopeType = Literal["gp", "pcn", "icb", "alliance", "service_provider"]

_LABEL_TO_SCOPE: dict[str, ScopeType] = {
    "GPPractice": "gp",
    "PCN": "pcn",
    "ICB": "icb",
    "CancerAlliance": "alliance",
    "ServiceProvider": "service_provider",
}

# Reusable Cypher fragment that restricts patients to an org hierarchy.
# Expects ``$scope_org_ids`` parameter (list of org IDs).
# Binds: ``p`` (Patient), ``_gp`` (GPPractice or Organization).
# Two-arm filter: GP registration path OR Service Provider referral path.
ORG_PATIENT_FILTER = (
    "("
    "  EXISTS { "
    "    MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(_gp) "
    "    WHERE _gp.id IN $scope_org_ids "
    "  } "
    "  OR EXISTS { "
    "    MATCH (p)<-[:FOR_PATIENT]-(:ReferralRequest)-[:IN_WORKFLOW]->(:Workflow)"
    "    -[:FOR_SERVICE]->(:Service)<-[:PROVIDES_SERVICE]-(_sp:Organization) "
    "    WHERE _sp.id IN $scope_org_ids "
    "  } "
    "  OR EXISTS { "
    "    MATCH (p)<-[:FOR_PATIENT]-(:ReferralRequest)-[:FOR_SERVICE]->(:Service)"
    "    <-[:PROVIDES_SERVICE]-(_sp2:Organization) "
    "    WHERE _sp2.id IN $scope_org_ids "
    "  } "
    ")"
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


# -- Redis-backed CallerScope cache -----------------------------------------
# Resolving a CallerScope previously fired 2-3 sequential Aura queries on every
# authenticated request. The result is stable for a given user email until org
# membership changes (rare), so we cache it in Redis with a short TTL. A
# tenant-admin invalidator (see :func:`invalidate_caller_scope_cache`) flushes
# the cache when memberships are mutated.
_SCOPE_CACHE_PREFIX_DEFAULT = "auth:caller-scope:"
_SCOPE_CACHE_TTL_SECONDS = int(os.getenv("CALLER_SCOPE_CACHE_TTL_SECONDS", "60"))


def _scope_cache_prefix() -> str:
    ns = (
        os.getenv("SESSION_KEY_NAMESPACE")
        or os.getenv("ENVIRONMENT")
        or os.getenv("APP_ENV")
        or "default"
    )
    ns = ns.strip().lower() or "default"
    return f"auth:{ns}:caller-scope:"


def _scope_cache_key(email: str) -> str:
    return f"{_scope_cache_prefix()}{email.strip().lower()}"


def _get_redis_for_scope():
    """Return a redis client (or None) using the same URL as the session store."""
    if os.getenv("DISABLE_REDIS") in ("true", "1"):
        return None
    url = os.getenv("REDIS_URL") or None
    if not url:
        return None
    try:
        import redis  # type: ignore

        return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
    except Exception as exc:
        logger.debug("CallerScope cache: redis unavailable (%s)", exc)
        return None


def _serialize_scope(scope: "CallerScope") -> str:
    return json.dumps(asdict(scope))


def _deserialize_scope(raw: str) -> Optional["CallerScope"]:
    try:
        data: dict[str, Any] = json.loads(raw)
        return CallerScope(
            email=str(data.get("email", "")),
            is_admin=bool(data.get("is_admin", False)),
            org_ids=list(data.get("org_ids", []) or []),
            scope_type=data.get("scope_type"),
            primary_org_id=data.get("primary_org_id"),
        )
    except Exception:
        return None


def _cache_get(email: str) -> Optional["CallerScope"]:
    if _SCOPE_CACHE_TTL_SECONDS <= 0:
        return None
    rc = _get_redis_for_scope()
    if rc is None:
        return None
    try:
        raw = rc.get(_scope_cache_key(email))
    except Exception:
        return None
    if not raw:
        return None
    return _deserialize_scope(raw)


def _cache_put(scope: "CallerScope") -> None:
    if _SCOPE_CACHE_TTL_SECONDS <= 0:
        return
    rc = _get_redis_for_scope()
    if rc is None:
        return
    try:
        rc.setex(
            _scope_cache_key(scope.email),
            _SCOPE_CACHE_TTL_SECONDS,
            _serialize_scope(scope),
        )
    except Exception:
        return


def invalidate_caller_scope_cache(email: Optional[str] = None) -> int:
    """Invalidate cached CallerScope entries.

    Call from any code path that mutates a Practitioner's WORKS_AT, role
    assignment, or platform-admin flag (admin / onboarding routers).
    Returns the number of keys deleted (0 if Redis unavailable).
    """
    rc = _get_redis_for_scope()
    if rc is None:
        return 0
    try:
        if email:
            return int(rc.delete(_scope_cache_key(email)) or 0)
        # Bulk wipe under prefix; SCAN to avoid blocking on big keyspaces.
        deleted = 0
        prefix = _scope_cache_prefix() + "*"
        for key in rc.scan_iter(match=prefix, count=500):
            try:
                deleted += int(rc.delete(key) or 0)
            except Exception:
                continue
        return deleted
    except Exception:
        return 0


def resolve_caller_scope(
    client: PatientGraphClient,
    email: str,
) -> CallerScope:
    """Resolve a user email to their full organizational scope.

    For GP users: returns the GP id + parent ICB + parent Alliance.
    For ICB users: returns the ICB id + all child GPs + parent Alliance.
    For Alliance users: returns the Alliance id + all child ICBs + all child GPs.
    Platform admins: is_admin=True, empty org_ids (meaning unrestricted).

    Results are cached in Redis for a short TTL to avoid the 2-3 sequential
    Aura queries on every authenticated request. Mutating endpoints must
    call :func:`invalidate_caller_scope_cache` after changing membership.
    """
    normalized = email.lower().strip()
    cached = _cache_get(normalized)
    if cached is not None:
        return cached

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
        scope = CallerScope(
            email=normalized,
            is_admin=True,
            org_ids=[],
            scope_type=None,
            primary_org_id=None,
        )
        _cache_put(scope)
        return scope

    # Fetch the org the practitioner WORKS_AT and determine scope type.
    orgs = client.run(
        "MATCH (pr:Practitioner {email: $email})-[:WORKS_AT]->(o) "
        "WHERE o:GPPractice OR o:ICB OR o:CancerAlliance "
        "   OR o:ServiceProvider OR o:Organization "
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
    elif scope_type == "pcn":
        all_ids = _expand_pcn_scope(client, primary_id)
    elif scope_type == "icb":
        all_ids = _expand_icb_scope(client, primary_id)
    elif scope_type == "service_provider":
        all_ids = _expand_service_provider_scope(client, primary_id)
    else:
        all_ids = _expand_alliance_scope(client, primary_id)

    scope = CallerScope(
        email=normalized,
        is_admin=False,
        org_ids=all_ids,
        scope_type=scope_type,
        primary_org_id=primary_id,
    )
    _cache_put(scope)
    return scope


def _expand_gp_scope(client: PatientGraphClient, gp_id: str) -> list[str]:
    """GP scope: own GP + parent PCN (if any) + parent ICB + grandparent Alliance."""
    rows = client.run(
        "MATCH (gp {id: $gp_id}) "
        "OPTIONAL MATCH (gp)-[:PART_OF_PCN]->(pcn:PCN) "
        "OPTIONAL MATCH (gp)-[:COMMISSIONED_BY]->(icb_direct:ICB) "
        "OPTIONAL MATCH (pcn)-[:COMMISSIONED_BY]->(icb_via_pcn:ICB) "
        "WITH gp, pcn, coalesce(icb_direct, icb_via_pcn) AS icb "
        "OPTIONAL MATCH (icb)-[:PART_OF_ALLIANCE]->(ca:CancerAlliance) "
        "RETURN gp.id AS gp_id, pcn.id AS pcn_id, icb.id AS icb_id, ca.id AS ca_id",
        gp_id=gp_id,
    )
    ids = {gp_id}
    if rows:
        if rows[0].get("pcn_id"):
            ids.add(rows[0]["pcn_id"])
        if rows[0].get("icb_id"):
            ids.add(rows[0]["icb_id"])
        if rows[0].get("ca_id"):
            ids.add(rows[0]["ca_id"])
    return list(ids)


def _expand_pcn_scope(client: PatientGraphClient, pcn_id: str) -> list[str]:
    """PCN scope: own PCN + all member GPs (active relationships) + parent ICB + grandparent Alliance."""
    rows = client.run(
        "MATCH (pcn:PCN {id: $pcn_id}) "
        "OPTIONAL MATCH (gp:GPPractice)-[r:PART_OF_PCN]->(pcn) WHERE r.effective_to IS NULL "
        "OPTIONAL MATCH (pcn)-[:COMMISSIONED_BY]->(icb:ICB) "
        "OPTIONAL MATCH (icb)-[:PART_OF_ALLIANCE]->(ca:CancerAlliance) "
        "RETURN collect(DISTINCT gp.id) AS gp_ids, icb.id AS icb_id, ca.id AS ca_id",
        pcn_id=pcn_id,
    )
    ids = {pcn_id}
    if rows:
        for gid in rows[0].get("gp_ids") or []:
            if gid:
                ids.add(gid)
        if rows[0].get("icb_id"):
            ids.add(rows[0]["icb_id"])
        if rows[0].get("ca_id"):
            ids.add(rows[0]["ca_id"])
    return list(ids)


def _expand_icb_scope(client: PatientGraphClient, icb_id: str) -> list[str]:
    """ICB scope: own ICB + all child PCNs + all child GPs + parent Alliance."""
    rows = client.run(
        "MATCH (icb:ICB {id: $icb_id}) "
        "OPTIONAL MATCH (pcn:PCN)-[:COMMISSIONED_BY]->(icb) "
        "OPTIONAL MATCH (gp_direct:GPPractice)-[:COMMISSIONED_BY]->(icb) "
        "OPTIONAL MATCH (gp_via_pcn:GPPractice)-[r:PART_OF_PCN]->(pcn) WHERE r.effective_to IS NULL "
        "OPTIONAL MATCH (icb)-[:PART_OF_ALLIANCE]->(ca:CancerAlliance) "
        "RETURN collect(DISTINCT pcn.id) AS pcn_ids, "
        "       collect(DISTINCT gp_direct.id) AS gp_direct_ids, "
        "       collect(DISTINCT gp_via_pcn.id) AS gp_pcn_ids, "
        "       ca.id AS ca_id",
        icb_id=icb_id,
    )
    ids = {icb_id}
    if rows:
        for pid in rows[0].get("pcn_ids") or []:
            if pid:
                ids.add(pid)
        for gid in rows[0].get("gp_direct_ids") or []:
            if gid:
                ids.add(gid)
        for gid in rows[0].get("gp_pcn_ids") or []:
            if gid:
                ids.add(gid)
        if rows[0].get("ca_id"):
            ids.add(rows[0]["ca_id"])
    return list(ids)


def _expand_service_provider_scope(
    client: PatientGraphClient, sp_id: str
) -> list[str]:
    """Service Provider scope: just the SP org id itself.

    Patient visibility is determined by the referral path filter in
    ORG_PATIENT_FILTER, not by expanding to child orgs.
    """
    return [sp_id]


def _expand_alliance_scope(client: PatientGraphClient, ca_id: str) -> list[str]:
    """Alliance scope: own Alliance + all child ICBs + all PCNs + all grandchild GPs."""
    rows = client.run(
        "MATCH (ca:CancerAlliance {id: $ca_id}) "
        "OPTIONAL MATCH (icb:ICB)-[:PART_OF_ALLIANCE]->(ca) "
        "OPTIONAL MATCH (pcn:PCN)-[:COMMISSIONED_BY]->(icb) "
        "OPTIONAL MATCH (gp_direct:GPPractice)-[:COMMISSIONED_BY]->(icb) "
        "OPTIONAL MATCH (gp_via_pcn:GPPractice)-[r:PART_OF_PCN]->(pcn) WHERE r.effective_to IS NULL "
        "RETURN collect(DISTINCT icb.id) AS icb_ids, "
        "       collect(DISTINCT pcn.id) AS pcn_ids, "
        "       collect(DISTINCT gp_direct.id) AS gp_direct_ids, "
        "       collect(DISTINCT gp_via_pcn.id) AS gp_pcn_ids",
        ca_id=ca_id,
    )
    ids = {ca_id}
    if rows:
        for iid in rows[0].get("icb_ids") or []:
            if iid:
                ids.add(iid)
        for pid in rows[0].get("pcn_ids") or []:
            if pid:
                ids.add(pid)
        for gid in rows[0].get("gp_direct_ids") or []:
            if gid:
                ids.add(gid)
        for gid in rows[0].get("gp_pcn_ids") or []:
            if gid:
                ids.add(gid)
    return list(ids)


def expand_preview_scope(client: PatientGraphClient, org_id: str) -> list[str]:
    """Expand an org ID to all constituent child org IDs for metric preview.

    Used by the audit-metrics run endpoint when an admin supplies preview_org_id.
    Dispatches to the same hierarchy-expansion functions as CallerScope so that
    ICB / Alliance / PCN preview includes all child GP IDs and ORG_GUARD
    produces correct patient counts for each level of the hierarchy.

    Falls back to [org_id] if the node is not found in the graph.
    """
    rows = client.run(
        "MATCH (o {id: $org_id}) RETURN labels(o) AS nodeLabels",
        org_id=org_id,
    )
    if not rows:
        return [org_id]
    labels = rows[0].get("nodeLabels") or []
    scope_type: ScopeType = "gp"
    for label in labels:
        if label in _LABEL_TO_SCOPE:
            scope_type = _LABEL_TO_SCOPE[label]
            break
    if scope_type == "pcn":
        return _expand_pcn_scope(client, org_id)
    if scope_type == "icb":
        return _expand_icb_scope(client, org_id)
    if scope_type == "service_provider":
        return _expand_service_provider_scope(client, org_id)
    if scope_type == "alliance":
        return _expand_alliance_scope(client, org_id)
    return _expand_gp_scope(client, org_id)


def get_caller_scope(
    leo_session: Optional[str] = Header(default=None, alias="X-Leo-Session"),
) -> CallerScope:
    """FastAPI dependency that resolves the caller's org scope from session.

    GAP-001: X-User-Email header and ?email= query param removed.
    Prefer using app.deps.get_caller_scope_from_request in service routers,
    which reads from the secure session cookie. This function is kept for
    internal callers that pass the session token via X-Leo-Session header.

    Local-dev bypass (off by default): when LEO_LOCAL_DEV_BYPASS=true is set
    in the process environment the dependency short-circuits and returns an
    unrestricted admin scope. This is intended for local MCP tooling and the
    docker-compose dev stack only. The flag is never set in any deployed
    env file -- see libs/auth/service_auth.py for the same pattern.
    """
    if _local_dev_bypass_enabled():
        logger.warning(
            "get_caller_scope: %s=true -- returning admin bypass scope. "
            "This MUST NOT appear in deployed environments.",
            _LOCAL_DEV_BYPASS_ENV,
        )
        return CallerScope(
            email=_LOCAL_DEV_BYPASS_EMAIL,
            is_admin=True,
            org_ids=[],
            scope_type=None,
            primary_org_id=None,
        )
    if not leo_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from libs.redis_client.session import load_session

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

    Admins always pass.
    GP / PCN / ICB / Alliance users: patient's GP must be in scope.org_ids.
    Service Provider users: patient must have a ReferralRequest routed to
    a Service owned by the SP org via IN_WORKFLOW->Workflow->FOR_SERVICE or
    directly via FOR_SERVICE.
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
    if gp_id in scope.org_ids:
        return

    if scope.scope_type == "service_provider" and scope.org_ids:
        sp_rows = client.run(
            "MATCH (p:Patient) WHERE toString(p.id) = $pid "
            "OPTIONAL MATCH (p)<-[:FOR_PATIENT]-(:ReferralRequest)"
            "-[:IN_WORKFLOW]->(:Workflow)-[:FOR_SERVICE]->(:Service)"
            "<-[:PROVIDES_SERVICE]-(_sp:Organization) "
            "WHERE _sp.id IN $org_ids "
            "RETURN _sp.id AS sp_id LIMIT 1",
            pid=patient_id,
            org_ids=scope.org_ids,
        )
        if sp_rows and sp_rows[0].get("sp_id"):
            return
        sp_direct = client.run(
            "MATCH (p:Patient) WHERE toString(p.id) = $pid "
            "OPTIONAL MATCH (p)<-[:FOR_PATIENT]-(:ReferralRequest)"
            "-[:FOR_SERVICE]->(:Service)"
            "<-[:PROVIDES_SERVICE]-(_sp2:Organization) "
            "WHERE _sp2.id IN $org_ids "
            "RETURN _sp2.id AS sp_id LIMIT 1",
            pid=patient_id,
            org_ids=scope.org_ids,
        )
        if sp_direct and sp_direct[0].get("sp_id"):
            return

    raise HTTPException(status_code=404, detail="Patient not found")
