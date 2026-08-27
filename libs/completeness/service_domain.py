"""Create or reuse a completeness dataset domain for a Service.

Atlas trace:
  UN: UN-3B25A20E
  DI: DI-26546721
  DO: DO-020C7B5C
  VT: VT-940267F9
"""

from __future__ import annotations

import json
from typing import Any

from libs.completeness.schema import normalise_completeness_groups

_SUBDOMAIN = "minimum_dataset"

_ENSURE_SERVICE_DOMAIN = """
MERGE (d:AuditDomain {id: $domain_id})
ON CREATE SET
    d.name = $domain_name,
    d.description = $description,
    d.source = 'tenant',
    d.useCases = ['completeness'],
    d.createdAt = datetime()
SET d.updatedAt = datetime()
MERGE (v:ValueSet {id: $vs_id})
ON CREATE SET
    v.name = $subdomain,
    v.useCases = ['completeness'],
    v.createdAt = datetime()
SET v.completeness_schema = $schema,
    v.completeness_schema_active = true,
    v.completeness_schema_updated_at = datetime()
MERGE (d)-[:HAS_SUBDOMAIN]->(v)
WITH d, v
OPTIONAL MATCH (svc:Service {id: $service_id})
FOREACH (_ IN CASE WHEN svc IS NOT NULL THEN [1] ELSE [] END |
    SET svc.completeness_domain = $domain_id,
        svc.completeness_subdomain = $subdomain
)
WITH d, v
OPTIONAL MATCH (org:Organization {id: $organization_id})
FOREACH (_ IN CASE WHEN org IS NOT NULL THEN [1] ELSE [] END |
    MERGE (d)-[:FOR_ORGANIZATION]->(org)
)
RETURN d.id AS domain_id, v.name AS subdomain
"""


def domain_id_for_service(service_id: str) -> str:
    """Stable AuditDomain id for an existing Service node."""
    return f"svc_{service_id}"


def ensure_service_completeness_domain(
    client: Any,
    organization_id: str,
    service_id: str,
    form_name: str,
    groups: list[dict[str, Any]] | None = None,
    *,
    require_blocking_groups: bool = True,
) -> dict[str, str]:
    """MERGE the service dataset domain and point the Service at it."""
    domain_id = domain_id_for_service(service_id)
    schema_rows = (
        normalise_completeness_groups(
            groups or [],
            require_blocking=require_blocking_groups,
        )
        if groups
        else []
    )
    rows = client.run(
        _ENSURE_SERVICE_DOMAIN,
        domain_id=domain_id,
        domain_name=f"{form_name} dataset",
        description=f"Minimum dataset for {form_name}",
        vs_id=f"{domain_id}-{_SUBDOMAIN}",
        subdomain=_SUBDOMAIN,
        schema=json.dumps({"groups": schema_rows}, ensure_ascii=True),
        service_id=service_id,
        organization_id=organization_id,
    )
    row = (rows or [{}])[0]
    return {
        "domain_id": str(row.get("domain_id") or domain_id),
        "subdomain": str(row.get("subdomain") or _SUBDOMAIN),
    }
