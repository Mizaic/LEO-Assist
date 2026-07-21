"""Cypher and helpers for LocalTerminologyPackage nodes.

Atlas trace:
  DO: DO-77A48DBC
  DI: DI-4746A178, DI-B7FEA996, DI-F8634363
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-77A48DBC")
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

CREATE_PACKAGE = """
CREATE (p:LocalTerminologyPackage {
  id: $id,
  name: $name,
  scope: $scope,
  org_id: $org_id,
  status: 'draft',
  version: 1,
  created_at: datetime($created_at),
  created_by: $created_by
})
RETURN p.id AS id, p.name AS name, p.scope AS scope, p.org_id AS org_id,
       p.status AS status, p.version AS version,
       0 AS concept_count
"""

GET_PACKAGE = """
MATCH (p:LocalTerminologyPackage {id: $id})
OPTIONAL MATCH (p)-[:CONTAINS]->(c:Concept)
RETURN p.id AS id, p.name AS name, p.scope AS scope, p.org_id AS org_id,
       p.status AS status, p.version AS version,
       count(DISTINCT c) AS concept_count
"""

LIST_PACKAGES = """
MATCH (p:LocalTerminologyPackage)
WHERE ($status IS NULL OR p.status = $status)
  AND ($scope IS NULL OR p.scope = $scope)
  AND ($org_id IS NULL OR p.org_id = $org_id OR p.scope = 'global')
OPTIONAL MATCH (p)-[:CONTAINS]->(c:Concept)
WITH p, count(DISTINCT c) AS concept_count
RETURN p.id AS id, p.name AS name, p.scope AS scope, p.org_id AS org_id,
       p.status AS status, p.version AS version, concept_count
ORDER BY p.scope, p.name
SKIP $offset LIMIT $limit
"""

COUNT_PACKAGES = """
MATCH (p:LocalTerminologyPackage)
WHERE ($status IS NULL OR p.status = $status)
  AND ($scope IS NULL OR p.scope = $scope)
  AND ($org_id IS NULL OR p.org_id = $org_id OR p.scope = 'global')
RETURN count(p) AS total
"""

SET_STATUS = """
MATCH (p:LocalTerminologyPackage {id: $id})
SET p.status = $status,
    p.updated_at = datetime($updated_at),
    p.activated_at = CASE WHEN $status = 'active'
      THEN datetime($updated_at) ELSE p.activated_at END
WITH p
OPTIONAL MATCH (p)-[:CONTAINS]->(c:Concept)
RETURN p.id AS id, p.name AS name, p.scope AS scope, p.org_id AS org_id,
       p.status AS status, p.version AS version,
       count(DISTINCT c) AS concept_count
"""

CONTAINS_CONCEPT = """
MATCH (p:LocalTerminologyPackage {id: $package_id})
MATCH (c:Concept {id: $concept_id})
MERGE (p)-[:CONTAINS]->(c)
RETURN p.id AS package_id, c.id AS concept_id
"""

ENSURE_GLOBAL_PACKAGE = """
MERGE (p:LocalTerminologyPackage {id: $id})
ON CREATE SET
  p.name = $name,
  p.scope = 'global',
  p.org_id = null,
  p.status = 'active',
  p.version = 1,
  p.created_at = datetime($created_at),
  p.created_by = 'system',
  p.activated_at = datetime($created_at)
ON MATCH SET
  p.scope = 'global',
  p.org_id = null
RETURN p.id AS id, p.name AS name, p.scope AS scope, p.status AS status
"""

GLOBAL_DEFAULT_PACKAGE_ID = "pkg-leo-global-defaults"


def validate_package_scope(scope: str, org_id: str | None) -> tuple[str, str | None]:
    """Return normalised (scope, org_id) or raise ValueError."""
    s = (scope or "").strip().lower()
    oid = (org_id or "").strip() or None
    if s == "global":
        if oid is not None:
            raise ValueError("Global packages must not set org_id.")
        return "global", None
    if s == "tenant":
        if not oid:
            raise ValueError("Tenant packages require org_id.")
        return "tenant", oid
    raise ValueError("scope must be 'global' or 'tenant'.")


def new_package_params(
    *, name: str, scope: str, org_id: str | None, created_by: str
) -> dict[str, Any]:
    scope_n, org_n = validate_package_scope(scope, org_id)
    label = (name or "").strip()
    if not label:
        raise ValueError("name is required.")
    return {
        "id": f"pkg-{uuid4().hex[:12]}",
        "name": label,
        "scope": scope_n,
        "org_id": org_n,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": created_by or "system",
    }
