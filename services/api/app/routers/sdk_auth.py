"""LEO widget SDK auth + SBAR proxy endpoints.

Atlas trace:
  DO: DO-5C88CA8F
  DI: DI-A1206416
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-5C88CA8F")

Two endpoints:

POST /sdk/auth/exchange
    Server-to-server only. The host product server presents a shared
    secret in the X-Mizaic-Host-Secret header and asks LEO to mint a
    short-lived widget token for one specific assessment-id, scoped
    to one host user. Browsers always send an Origin header on POST,
    so any request that includes Origin is refused (this catches a
    host product accidentally proxying the call from the browser).

GET /sdk/sbar/{assessment_id}
    Browser-facing. The widget calls this with the widget token in
    the Authorization header. The token's assessment_id claim MUST
    match the path. Mismatch returns 403.
"""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.services import host_governance
from libs.sdk_auth import (
    WIDGET_TOKEN_MAX_TTL_SECONDS,
    WidgetTokenError,
    mint_widget_token,
    verify_widget_token,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sdk", tags=["sdk-auth"])

_HOST_SECRET_HEADER = "X-Mizaic-Host-Secret"


class ExchangeRequest(BaseModel):
    host_id: str = Field(..., min_length=1, max_length=128)
    host_user_id: str = Field(..., min_length=1, max_length=256)
    tenant_id: str = Field(..., min_length=1, max_length=128)
    assessment_id: str = Field(..., min_length=1, max_length=128)
    user_role: str = Field(..., min_length=1, max_length=64)


class ExchangeResponse(BaseModel):
    widget_token: str
    expires_at: int
    ttl_seconds: int


class SbarPayload(BaseModel):
    assessment_id: str
    tenant_id: str
    generated_at: str
    markdown: str
    background_parts: list[dict] = []


def _expected_host_secret() -> str:
    secret = os.environ.get("SDK_HOST_SHARED_SECRET", "")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SDK widget-token exchange is not configured",
        )
    return secret


def _enforce_server_to_server(request: Request) -> None:
    """Refuse if a browser-style Origin header is present.

    Browsers send Origin on every cross-origin POST. Server-to-server
    HTTP clients (httpx, requests, curl) do not. This is a cheap
    additional belt-and-braces on top of the shared secret.
    """

    if request.headers.get("origin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "POST /sdk/auth/exchange is server-to-server only; "
                "requests from a browser origin are not permitted"
            ),
        )


def _verify_host_secret(provided: str | None) -> None:
    expected = _expected_host_secret()
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing host shared secret",
        )


@router.post("/auth/exchange", response_model=ExchangeResponse)
def exchange_for_widget_token(
    payload: ExchangeRequest,
    request: Request,
    x_mizaic_host_secret: str | None = Header(default=None),
) -> ExchangeResponse:
    """Mint a widget token for a single assessment (server-to-server)."""
    _enforce_server_to_server(request)
    _verify_host_secret(x_mizaic_host_secret)

    if not host_governance.is_production_ready(payload.host_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="host_not_onboarded",
        )

    try:
        result = mint_widget_token(
            host_user_id=payload.host_user_id,
            tenant_id=payload.tenant_id,
            assessment_id=payload.assessment_id,
            user_role=payload.user_role,
            ttl_seconds=WIDGET_TOKEN_MAX_TTL_SECONDS,
        )
    except WidgetTokenError as exc:
        logger.warning("widget token mint failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to mint widget token",
        ) from exc

    return ExchangeResponse(
        widget_token=result.token,
        expires_at=result.expires_at,
        ttl_seconds=result.ttl_seconds,
    )


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing widget Bearer token",
        )
    return authorization.split(" ", 1)[1].strip()


@router.get("/sbar/{assessment_id}", response_model=SbarPayload)
def proxy_sbar(
    assessment_id: str,
    authorization: str | None = Header(default=None),
) -> SbarPayload:
    """Browser-facing SBAR fetch. Validates token + assessment scope."""
    token = _extract_bearer(authorization)
    try:
        claims = verify_widget_token(token)
    except WidgetTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid widget token: {exc}",
        ) from exc

    if claims.assessment_id != assessment_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Widget token assessment-id does not match the requested "
                "assessment-id"
            ),
        )

    return _load_sbar_payload(assessment_id, claims.tenant_id)


def _load_sbar_payload(assessment_id: str, tenant_id: str) -> SbarPayload:
    """Load an SBAR payload for the proxy response.

    Slice 2 returns a deterministic placeholder so the auth contract
    can be verified end-to-end. Slice 3+ wires this into the existing
    Neo4j-backed assessment store via libs/cypher/sbar_assessment_queries.
    """

    return SbarPayload(
        assessment_id=assessment_id,
        tenant_id=tenant_id,
        generated_at="2026-04-20T00:00:00Z",
        markdown=(
            "# Situation\nWidget proxy slice-2 placeholder.\n\n"
            "# Background\n## Presenting complaint\nN/A\n\n"
            "# Assessment\nN/A\n\n# Recommendation\nN/A\n"
        ),
        background_parts=[],
    )
