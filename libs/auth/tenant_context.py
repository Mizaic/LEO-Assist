"""Azure AD JWT validation and tenant context extraction.

Ported from visual-report-builder fhir-api/app/core/auth.py.
Adapted to be a standalone shared library with no service-specific dependencies.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional

import requests
from fastapi import Header, HTTPException
from jose import JWTError, jwt

logger = logging.getLogger("libs.auth")


@dataclass
class TenantContext:
    tenant_id: str
    user_oid: Optional[str] = None
    user_email: Optional[str] = None
    roles: Optional[str] = None
    app_id: Optional[str] = None


def get_tenant_context(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> TenantContext:
    """FastAPI dependency that extracts and validates tenant context from JWT."""
    if authorization and authorization.startswith("Bearer "):
        return _tenant_from_jwt(authorization.replace("Bearer ", "", 1).strip())
    raise HTTPException(status_code=401, detail="Missing Authorization bearer token.")


def _tenant_from_jwt(token: str) -> TenantContext:
    tenant_id = os.getenv("AZURE_AD_TENANT_ID")
    client_id = os.getenv("AZURE_AD_CLIENT_ID")

    if not tenant_id or not client_id:
        raise HTTPException(
            status_code=500, detail="Azure AD settings are not configured."
        )

    jwks = _get_jwks(tenant_id)
    try:
        claims = _decode_with_audiences_and_issuers(
            token, jwks, _get_expected_audiences(client_id), _get_expected_issuers(tenant_id)
        )
    except JWTError:
        try:
            unverified = jwt.get_unverified_claims(token)
            logger.warning(
                "JWT validation failed. aud=%s iss=%s",
                unverified.get("aud"),
                unverified.get("iss"),
            )
        except Exception:
            logger.warning("JWT validation failed and claims could not be decoded.")
        raise HTTPException(status_code=401, detail="Invalid or expired JWT.")

    tid = claims.get("tid")
    if not tid:
        raise HTTPException(status_code=401, detail="JWT missing tenant id (tid).")

    email = claims.get("preferred_username") or claims.get("upn") or claims.get("email")
    if isinstance(email, str):
        email = email.strip().lower() or None

    return TenantContext(
        tenant_id=tid,
        user_oid=claims.get("oid"),
        user_email=email,
        roles=",".join(claims.get("roles", []) or []),
        app_id=claims.get("azp") or claims.get("appid"),
    )


def _get_expected_audiences(client_id: str) -> List[str]:
    audiences: list[str] = [client_id]
    scope = os.getenv("FHIR_API_SCOPE")
    if scope and scope.endswith("/.default") and scope.startswith("api://"):
        audiences.append(scope.removesuffix("/.default"))
    env_audience = os.getenv("FHIR_API_AUDIENCE")
    if env_audience:
        audiences.append(env_audience)
    return list(dict.fromkeys(audiences))


def _get_expected_issuers(tenant_id: str) -> List[str]:
    """Accept v2.0 (preferred) and v1.0 issuers. Prefer accessTokenAcceptedVersion: 2 in app manifest."""
    return [
        f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        f"https://sts.windows.net/{tenant_id}/",
    ]


def _decode_with_audiences_and_issuers(
    token: str, jwks: Dict, audiences: List[str], issuers: List[str]
) -> Dict:
    last_error: JWTError | None = None
    for aud in audiences:
        for iss in issuers:
            try:
                return jwt.decode(
                    token, jwks, algorithms=["RS256"], audience=aud, issuer=iss
                )
            except JWTError as exc:
                last_error = exc
    if last_error:
        raise last_error
    raise JWTError("No valid audience or issuer configured.")


@lru_cache(maxsize=1)
def _get_jwks(tenant_id: str) -> Dict:
    url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    response = requests.get(url, timeout=10)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch Azure AD JWKS.")
    return response.json()
