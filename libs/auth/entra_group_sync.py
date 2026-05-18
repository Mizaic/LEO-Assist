"""Resolve LEO roles from the Entra `groups` claim and sync HAS_ROLE edges.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Covers the runtime side of DI-D9D4BA02. The seeder side lives in
``scripts/seed_roles_and_groups.py``.

Flow on every successful OIDC callback:

1. Inspect the verified ID-token claims for the `groups` array.
2. If `groups` is missing and `_claim_names.groups` is present (overage),
   audit `groups_claim_overage` and return ``GroupSyncResult.fallthrough``.
3. If `groups` is missing entirely, audit `groups_claim_missing` and return
   ``GroupSyncResult.fallthrough``. Roles fall back to existing HAS_ROLE
   edges so an account that pre-dates this feature still works.
4. Resolve the group object IDs to role names via the Neo4j catalogue
   (`:Group {entra_object_id} -[:GRANTS_ROLE]-> :Role`).
5. Audit any unknown group IDs (no `:Group` row) so tenant admins can spot
   stale catalogue entries.
6. Synchronise the practitioner's outgoing [:HAS_ROLE] edges to exactly the
   resolved role-name set (delete edges no longer granted, add new ones).

This module never calls Microsoft Graph -- the security DI (DI-3610585D)
forbids it. The overage path explicitly falls through.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from libs.audit.security_log import (
    emit_entra_groups_resolved,
    emit_groups_claim_missing,
    emit_groups_claim_overage,
    emit_unknown_entra_group,
)
from libs.cypher.entra_group_queries import (
    ADD_HAS_ROLE_EDGES,
    DROP_STALE_HAS_ROLE,
    READ_HAS_ROLE,
    RESOLVE_ROLES_FROM_ENTRA_GROUPS,
)
from libs.cypher.role_queries import CANONICAL_ROLES
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GroupSyncResult:
    """Outcome of one Entra-group resolution + sync pass."""

    role_names: list[str]
    unknown_group_ids: list[str]
    fallthrough: bool

    @classmethod
    def empty_fallthrough(cls) -> "GroupSyncResult":
        return cls(role_names=[], unknown_group_ids=[], fallthrough=True)


def _normalise_email(email: Optional[str]) -> str:
    return (email or "").strip().lower()


def _coerce_group_ids(value: Any) -> list[str]:
    """Return a clean list of GUID strings from a claim value."""
    if not value:
        return []
    if isinstance(value, str):
        items: Iterable[Any] = [value]
    elif isinstance(value, (list, tuple, set)):
        items = value
    else:
        return []
    out: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if cleaned:
            out.append(cleaned)
    return out


def _filter_canonical(names: Iterable[str]) -> list[str]:
    """Drop any role name that is not in CANONICAL_ROLES.

    Defence in depth: if the catalogue ever points an Entra group at a role
    that has been retired, we silently ignore it rather than write a broken
    HAS_ROLE edge. The catalogue PR review is the primary control; this is
    the runtime backstop.
    """
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        if not isinstance(name, str):
            continue
        if name not in CANONICAL_ROLES:
            logger.warning(
                "entra_group_sync.dropping_non_canonical_role role=%s", name
            )
            continue
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    out.sort()
    return out


def _resolve_role_names(
    client: PatientGraphClient,
    group_ids: list[str],
) -> tuple[list[str], list[str]]:
    """Return (role_names, unknown_group_ids) for the given group ID list."""
    if not group_ids:
        return [], []
    rows = client.run(RESOLVE_ROLES_FROM_ENTRA_GROUPS, group_object_ids=group_ids)
    matched_ids: set[str] = set()
    role_set: set[str] = set()
    for row in rows or []:
        oid = row.get("entra_object_id")
        rname = row.get("role_name")
        if isinstance(oid, str) and oid:
            matched_ids.add(oid)
        if isinstance(rname, str) and rname:
            role_set.add(rname)
    unknown = sorted({g for g in group_ids if g not in matched_ids})
    role_names = _filter_canonical(role_set)
    return role_names, unknown


def _sync_has_role(
    client: PatientGraphClient,
    email: str,
    role_names: list[str],
) -> None:
    """Synchronise outgoing [:HAS_ROLE] edges to exactly ``role_names``."""
    client.run(DROP_STALE_HAS_ROLE, email=email, role_names=role_names)
    if role_names:
        client.run(ADD_HAS_ROLE_EDGES, email=email, role_names=role_names)


def resolve_and_sync_entra_groups(
    *,
    email: str,
    id_claims: dict[str, Any],
    ip: str,
    client: Optional[PatientGraphClient] = None,
) -> GroupSyncResult:
    """Resolve the user's Entra groups to LEO roles and sync HAS_ROLE edges.

    Returns a ``GroupSyncResult``. When ``fallthrough=True`` the caller
    should keep whatever HAS_ROLE edges already exist on the practitioner;
    no edges have been mutated.
    """
    normalised = _normalise_email(email)
    if not normalised:
        return GroupSyncResult.empty_fallthrough()

    raw_groups = id_claims.get("groups")
    overage = (id_claims.get("_claim_names") or {}).get("groups")

    if raw_groups is None:
        if overage:
            emit_groups_claim_overage(email=normalised, ip=ip)
        else:
            emit_groups_claim_missing(email=normalised, ip=ip)
        return GroupSyncResult.empty_fallthrough()

    group_ids = _coerce_group_ids(raw_groups)
    if not group_ids:
        emit_groups_claim_missing(email=normalised, ip=ip)
        return GroupSyncResult.empty_fallthrough()

    own_client = client is None
    graph = client or PatientGraphClient()
    try:
        role_names, unknown = _resolve_role_names(graph, group_ids)
        for unknown_id in unknown:
            emit_unknown_entra_group(
                email=normalised,
                ip=ip,
                group_id=unknown_id,
            )
        _sync_has_role(graph, normalised, role_names)
    finally:
        if own_client:
            graph.close()

    emit_entra_groups_resolved(
        email=normalised,
        ip=ip,
        group_ids=group_ids,
        role_names=role_names,
    )
    return GroupSyncResult(
        role_names=role_names,
        unknown_group_ids=unknown,
        fallthrough=False,
    )


def read_current_role_names(
    email: str,
    client: Optional[PatientGraphClient] = None,
) -> list[str]:
    """Return the practitioner's current HAS_ROLE role-name set."""
    normalised = _normalise_email(email)
    if not normalised:
        return []
    own_client = client is None
    graph = client or PatientGraphClient()
    try:
        rows = graph.run(READ_HAS_ROLE, email=normalised)
    finally:
        if own_client:
            graph.close()
    if not rows:
        return []
    names = rows[0].get("allowed_roles") or []
    return _filter_canonical(names)
