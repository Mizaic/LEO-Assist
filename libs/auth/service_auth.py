"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-175B815C
  DI: DI-5F978E36
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-175B815C")

Shared-secret inter-service authentication (GAP-007, defence-in-depth).

Used on internal-ingress services (terminology-api, fhir-api, analytics-api)
as a second layer behind ACA internal network segmentation.

The secret is read from SERVICE_AUTH_SECRET env var (populated from Key Vault).
- In local development (ENVIRONMENT=local) an empty secret bypasses the check
  so engineers can run the stack with `docker compose up` without the secret
  configured.
- In every other environment (dev, staging, prod) an empty secret is treated
  as a fail-closed condition: the dependency raises 503 so the service does
  NOT silently accept anonymous traffic against mutating internal endpoints.
"""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


def _is_local_env() -> bool:
    return os.environ.get("ENVIRONMENT", "local").strip().lower() == "local"


def verify_service_token(request: Request) -> None:
    """FastAPI dependency -- raises 401/503 if the shared secret is wrong."""
    expected = os.environ.get("SERVICE_AUTH_SECRET", "").strip()

    if not expected:
        if _is_local_env():
            return
        logger.error(
            "SERVICE_AUTH_SECRET is not configured in environment '%s'; "
            "rejecting request to fail closed.",
            os.environ.get("ENVIRONMENT", "<unset>"),
        )
        raise HTTPException(
            status_code=503,
            detail="Service auth not configured",
        )

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
