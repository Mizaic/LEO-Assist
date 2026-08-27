"""Admin endpoints for ServiceDomain completeness schemas.

GET  /completeness-domains          -- list all tenant AuditDomain nodes
GET  /completeness-domains/{domain_id}  -- get schema for one domain
PUT  /completeness-domains/{domain_id}  -- update completeness groups

Atlas trace:
  UN: UN-3B25A20E
  DI: DI-26546721
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps import require_admin
from libs.completeness.service_domain import ensure_service_completeness_domain
from libs.neo4j_client.client import PatientGraphClient

router = APIRouter(prefix="/completeness-domains", tags=["completeness-domains"])

_LIST_DOMAINS = """
MATCH (d:AuditDomain {source: 'tenant'})-[:HAS_SUBDOMAIN]->(v:ValueSet)
WHERE v.completeness_schema_active = true
OPTIONAL MATCH (d)-[:FOR_ORGANIZATION]->(org:Organization)
RETURN d.id AS domain_id,
       d.name AS domain_name,
       org.id AS organization_id,
       org.name AS organization_name,
       v.completeness_schema AS completeness_schema,
       v.completeness_schema_updated_at AS updated_at
ORDER BY d.name
"""

_GET_DOMAIN = """
MATCH (d:AuditDomain {id: $domain_id})-[:HAS_SUBDOMAIN]->(v:ValueSet)
OPTIONAL MATCH (d)-[:FOR_ORGANIZATION]->(org:Organization)
OPTIONAL MATCH (svc:Service {completeness_domain: $domain_id})
RETURN d.id AS domain_id,
       d.name AS domain_name,
       org.id AS organization_id,
       org.name AS organization_name,
       svc.id AS service_id,
       svc.name AS service_name,
       v.completeness_schema AS completeness_schema,
       v.completeness_schema_updated_at AS updated_at,
       v.completeness_schema_updated_by AS updated_by
"""


def _parse_groups(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    if isinstance(parsed, dict):
        return parsed.get("groups") or []
    if isinstance(parsed, list):
        return parsed
    return []


def _domain_detail(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "domain_id": row.get("domain_id") or "",
        "domain_name": row.get("domain_name") or "",
        "organization_id": row.get("organization_id") or "",
        "organization_name": row.get("organization_name") or "",
        "service_id": row.get("service_id") or "",
        "service_name": row.get("service_name") or "",
        "completeness_groups": _parse_groups(row.get("completeness_schema")),
        "updated_at": str(row.get("updated_at") or ""),
        "updated_by": row.get("updated_by") or "",
    }


@router.get("")
def list_domains(
    _session: dict = Depends(require_admin),
) -> dict[str, Any]:
    """List all tenant ServiceDomain completeness schemas."""
    client = PatientGraphClient()
    try:
        rows = client.run(_LIST_DOMAINS) or []
        domains = [_domain_detail(dict(r)) for r in rows]
    finally:
        client.close()
    return {"domains": domains}


@router.get("/{domain_id}")
def get_domain(
    domain_id: str,
    _session: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Get completeness groups for a single domain."""
    client = PatientGraphClient()
    try:
        rows = client.run(_GET_DOMAIN, domain_id=domain_id) or []
    finally:
        client.close()
    if not rows:
        raise HTTPException(status_code=404, detail="Domain not found")
    return {"domain": _domain_detail(dict(rows[0]))}


class UpdateDomainRequest(BaseModel):
    form_name: str = Field(..., min_length=1)
    organization_id: str = ""
    service_id: str = ""
    completeness_groups: list[dict[str, Any]] = Field(default_factory=list)


@router.put("/{domain_id}")
def update_domain(
    domain_id: str,
    body: UpdateDomainRequest,
    session: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Replace completeness groups for a domain."""
    if not body.service_id:
        raise HTTPException(
            status_code=422,
            detail="service_id is required to update a completeness domain",
        )
    client = PatientGraphClient()
    try:
        result = ensure_service_completeness_domain(
            client,
            organization_id=body.organization_id,
            service_id=body.service_id,
            form_name=body.form_name,
            groups=body.completeness_groups or None,
        )
        _mark_updated_by(client, result["domain_id"], session.get("email") or "unknown")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        client.close()
    return {
        "domain_id": result["domain_id"],
        "subdomain": result["subdomain"],
        "saved": True,
    }


_SET_UPDATED_BY = """
MATCH (d:AuditDomain {id: $domain_id})-[:HAS_SUBDOMAIN]->(v:ValueSet)
SET v.completeness_schema_updated_by = $updated_by
"""


def _mark_updated_by(client: Any, domain_id: str, updated_by: str) -> None:
    try:
        client.run(_SET_UPDATED_BY, domain_id=domain_id, updated_by=updated_by)
    except Exception:
        pass
