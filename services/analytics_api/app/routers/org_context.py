"""Organization context endpoint.

Returns the organizations a user has access to, based on their
Practitioner node and WORKS_AT relationships in the Patient Graph.
Platform admins (is_platform_admin=true) see all organizations.

Enriched with scopeType (gp|icb|alliance) for tenant-scoped measure evaluation.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from libs.neo4j_client.client import PatientGraphClient

router = APIRouter()

# Map Neo4j node labels to scope types (hardcoded)
_LABEL_TO_SCOPE = {
    "GPPractice": "gp",
    "ICB": "icb",
    "CancerAlliance": "alliance",
}


def _resolve_scope_type(labels: list) -> str:
    """Resolve scopeType from node labels. Default to gp for Organization-only nodes."""
    for label in labels:
        if label in _LABEL_TO_SCOPE:
            return _LABEL_TO_SCOPE[label]
    return "gp"


@router.get("/auth/org-context")
def get_org_context(email: str = Query(..., description="User email address")):
    """Return organizations the user can access, with scopeType for tenant scoping."""
    client = PatientGraphClient()
    try:
        practitioner = client.run(
            "MATCH (pr:Practitioner {email: $email}) "
            "RETURN pr.id AS id, pr.name AS name, pr.email AS email, "
            "       pr.is_platform_admin AS is_platform_admin",
            email=email.lower().strip(),
        )

        if not practitioner:
            raise HTTPException(404, f"No practitioner found for {email}")

        user = practitioner[0]
        is_admin = user.get("is_platform_admin", False)

        if is_admin:
            orgs = client.run(
                "MATCH (o) WHERE o:GPPractice OR o:ICB OR o:CancerAlliance OR o:Organization "
                "RETURN o.id AS id, o.name AS name, o.odsCode AS odsCode, "
                "       o.short_name AS short_name, o.type AS type, labels(o) AS nodeLabels "
                "ORDER BY o.name",
            )
        else:
            orgs = client.run(
                "MATCH (pr:Practitioner {email: $email})-[:WORKS_AT]->(o) "
                "WHERE o:GPPractice OR o:ICB OR o:CancerAlliance OR o:Organization "
                "RETURN o.id AS id, o.name AS name, o.odsCode AS odsCode, "
                "       o.short_name AS short_name, o.type AS type, labels(o) AS nodeLabels "
                "ORDER BY o.name",
                email=email.lower().strip(),
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
