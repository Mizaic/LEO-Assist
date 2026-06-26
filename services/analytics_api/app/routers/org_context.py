"""Organization context endpoint.

Atlas trace:
  DO: DO-D5B9FE5F
  DI: DI-6E1B71A4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-D5B9FE5F")

Returns the organizations a user has access to, based on their
Practitioner node and WORKS_AT relationships in the Patient Graph.
Platform admins (is_platform_admin=true) see all organizations.

Enriched with scopeType (gp|icb|alliance) for tenant-scoped measure evaluation.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)

router = APIRouter()

# Map Neo4j node labels to scope types (hardcoded)
_LABEL_TO_SCOPE = {
    "GPPractice": "gp",
    "ICB": "icb",
    "CancerAlliance": "alliance",
    "ServiceProvider": "service_provider",
}


def _resolve_scope_type(labels: list) -> str:
    """Resolve scopeType from node labels. Default to gp for Organization-only nodes."""
    for label in labels:
        if label in _LABEL_TO_SCOPE:
            return _LABEL_TO_SCOPE[label]
    return "gp"


@router.get("/auth/org-context")
def get_org_context(
    scope: CallerScope = Depends(get_caller_scope),
    email: Optional[str] = Query(
        default=None, description="User email override (admin only)"
    ),
):
    """Return organizations the user can access, with scopeType for tenant scoping.

    Non-admin callers always see their own org context (the email parameter is
    ignored).  Platform admins may pass an explicit email to look up another
    user's context.
    """
    lookup_email = scope.email
    if email and scope.is_admin:
        lookup_email = email
    elif email and not scope.is_admin:
        logger.warning(
            "org-context: non-admin %s tried to look up %s -- using own email",
            scope.email,
            email,
        )

    client = PatientGraphClient()
    try:
        practitioner = client.run(
            "MATCH (pr:Practitioner {email: $email}) "
            "RETURN pr.id AS id, pr.name AS name, pr.email AS email, "
            "       pr.is_platform_admin AS is_platform_admin",
            email=lookup_email.lower().strip(),
        )

        if not practitioner:
            raise HTTPException(404, f"No practitioner found for {lookup_email}")

        user = practitioner[0]
        is_admin = user.get("is_platform_admin", False)

        org_where = (
            "o:GPPractice OR o:ICB OR o:CancerAlliance "
            "OR o:ServiceProvider OR o:Organization"
        )
        if is_admin:
            orgs = client.run(
                "MATCH (o) WHERE " + org_where + " "
                "RETURN o.id AS id, o.name AS name, o.odsCode AS odsCode, "
                "       o.short_name AS short_name, o.type AS type, labels(o) AS nodeLabels "
                "ORDER BY o.name",
            )
        else:
            orgs = client.run(
                "MATCH (pr:Practitioner {email: $email})-[:WORKS_AT]->(o) "
                "WHERE " + org_where + " "
                "RETURN o.id AS id, o.name AS name, o.odsCode AS odsCode, "
                "       o.short_name AS short_name, o.type AS type, labels(o) AS nodeLabels "
                "ORDER BY o.name",
                email=lookup_email.lower().strip(),
            )

        return {
            "user": {
                "id": user.get("id"),
                "name": user.get("name"),
                "email": user.get("email"),
                "is_platform_admin": is_admin,
            },
            "organizations": [
                {
                    "id": o.get("id"),
                    "name": o.get("name"),
                    "odsCode": o.get("odsCode"),
                    "shortName": o.get("short_name"),
                    "type": o.get("type"),
                    "scopeType": _resolve_scope_type(o.get("nodeLabels") or []),
                }
                for o in orgs
            ],
        }
    finally:
        client.close()
