"""
Shared-secret inter-service authentication (GAP-007, defence-in-depth).

Used on internal-ingress services (terminology-api, fhir-api, analytics-api)
as a second layer behind ACA internal network segmentation.

The secret is read from SERVICE_AUTH_SECRET env var (populated from Key Vault).
When SERVICE_AUTH_SECRET is not set the check is bypassed to allow local dev.
"""
from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request


def verify_service_token(request: Request) -> None:
    """FastAPI dependency -- raises 401 if the shared secret is wrong."""
    expected = os.environ.get("SERVICE_AUTH_SECRET", "")
    if not expected:
        return

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing service auth token")

    provided = auth_header.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid service auth token")


def get_service_auth_header() -> dict[str, str]:
    """Return Authorization header dict for outbound inter-service calls."""
    secret = os.environ.get("SERVICE_AUTH_SECRET", "")
    if not secret:
        return {}
    return {"Authorization": f"Bearer {secret}"}
