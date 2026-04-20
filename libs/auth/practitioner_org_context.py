"""Load practitioner admin flag and org list from the Patient Graph.

Atlas trace:
  DO: DO-308DD1A6
  DI: DI-D49BCE55
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-308DD1A6")

Used during OAuth callback to build the session. This logic must stay aligned
with ``services/analytics_api/app/routers/org_context.py`` (same Cypher).

We cannot call Analytics ``GET /analytics/auth/org-context`` from Core API at
login: that route depends on ``X-Leo-Session``, which does not exist until
after the session is created.
"""

from __future__ import annotations

import logging
from typing import Any

from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)

_LABEL_TO_SCOPE: dict[str, str] = {
    "GPPractice": "gp",
    "ICB": "icb",
    "CancerAlliance": "alliance",
}


def _scope_type(labels: list[Any] | None) -> str:
    for label in labels or []:
        if label in _LABEL_TO_SCOPE:
            return _LABEL_TO_SCOPE[label]
    return "gp"


def fetch_practitioner_org_context(
    email: str,
) -> tuple[bool, list[dict[str, Any]]]:
    """Return (is_platform_admin, organizations) for session storage.

    On any graph error or missing Practitioner, returns (False, []).
    """
    normalized = (email or "").strip().lower()
    if not normalized:
        return False, []

    client = PatientGraphClient()
    try:
        practitioner = client.run(
            "MATCH (pr:Practitioner {email: $email}) "
            "RETURN pr.id AS id, pr.name AS name, pr.email AS email, "
            "       pr.is_platform_admin AS is_platform_admin",
            email=normalized,
        )
        if not practitioner:
            logger.warning(
                "Login: no Practitioner node for email=%s",
                normalized,
            )
            return False, []

        user = practitioner[0]
        is_admin = bool(user.get("is_platform_admin", False))

        org_where = "o:GPPractice OR o:ICB OR o:CancerAlliance OR o:Organization"
        if is_admin:
            orgs = client.run(
                "MATCH (o) WHERE "
                + org_where
                + " RETURN o.id AS id, o.name AS name, o.odsCode AS odsCode, "
                "o.short_name AS short_name, o.type AS type, "
                "labels(o) AS nodeLabels ORDER BY o.name",
            )
        else:
            orgs = client.run(
                "MATCH (pr:Practitioner {email: $email})-[:WORKS_AT]->(o) "
                "WHERE "
                + org_where
                + " RETURN o.id AS id, o.name AS name, o.odsCode AS odsCode, "
                "o.short_name AS short_name, o.type AS type, "
                "labels(o) AS nodeLabels ORDER BY o.name",
                email=normalized,
            )

        organizations = [
            {
                "id": o.get("id"),
                "name": o.get("name"),
                "odsCode": o.get("odsCode"),
                "shortName": o.get("short_name"),
                "type": o.get("type"),
                "scopeType": _scope_type(o.get("nodeLabels")),
            }
            for o in orgs
        ]
        return is_admin, organizations
    except Exception as exc:
        logger.warning(
            "Login: failed to load practitioner org context: %s",
            exc,
        )
        return False, []
    finally:
        client.close()
