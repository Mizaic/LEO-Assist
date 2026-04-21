"""LEO widget short-lived token mint + verify.

Atlas trace:
  DO: DO-5C88CA8F
  DI: DI-A1206416
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-5C88CA8F")

These tokens are issued to the embeddable SBAR widget. They are
*never* long-lived API keys: TTL is capped at 15 minutes, audience
is locked to "leo-widget", and scope is restricted to a single
assessment-id. Long-lived LEO credentials stay on the host product
server.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass

from jose import JWTError, jwt

WIDGET_AUDIENCE = "leo-widget"
WIDGET_ISSUER = "leo-core-api"
WIDGET_TOKEN_MAX_TTL_SECONDS = 900
_ALGORITHM = "HS256"


class WidgetTokenError(Exception):
    """Raised when a widget token fails to mint or verify."""


@dataclass(frozen=True)
class WidgetClaims:
    """Decoded claims from a verified widget token."""

    sub: str
    tenant_id: str
    assessment_id: str
    user_role: str
    scope: str
    iat: int
    exp: int
    jti: str


@dataclass(frozen=True)
class WidgetTokenResult:
    """Result of minting a widget token."""

    token: str
    expires_at: int
    ttl_seconds: int


def _signing_secret() -> str:
    secret = os.environ.get("SDK_WIDGET_TOKEN_SECRET", "")
    if not secret:
        raise WidgetTokenError(
            "SDK_WIDGET_TOKEN_SECRET is not configured; refusing to mint or "
            "verify widget tokens"
        )
    return secret


def mint_widget_token(
    *,
    host_user_id: str,
    tenant_id: str,
    assessment_id: str,
    user_role: str,
    ttl_seconds: int = WIDGET_TOKEN_MAX_TTL_SECONDS,
) -> WidgetTokenResult:
    """Mint a short-lived widget token for a single assessment.

    The TTL is hard-capped at 900 seconds. Callers asking for more
    silently get the cap; callers asking for less get what they ask
    for. Audience and issuer are not caller-controllable.
    """

    if ttl_seconds <= 0:
        raise WidgetTokenError("ttl_seconds must be positive")
    capped_ttl = min(ttl_seconds, WIDGET_TOKEN_MAX_TTL_SECONDS)
    now = int(time.time())
    exp = now + capped_ttl
    claims = {
        "iss": WIDGET_ISSUER,
        "aud": WIDGET_AUDIENCE,
        "sub": host_user_id,
        "tenant_id": tenant_id,
        "assessment_id": assessment_id,
        "user_role": user_role,
        "scope": f"sbar.read:assessment:{assessment_id}",
        "iat": now,
        "exp": exp,
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(claims, _signing_secret(), algorithm=_ALGORITHM)
    return WidgetTokenResult(token=token, expires_at=exp, ttl_seconds=capped_ttl)


def verify_widget_token(token: str) -> WidgetClaims:
    """Verify a widget token and return the decoded claims.

    Raises WidgetTokenError on any failure: bad signature, wrong
    audience, expired, missing required claim, or TTL beyond the
    server-side ceiling.
    """

    try:
        decoded = jwt.decode(
            token,
            _signing_secret(),
            algorithms=[_ALGORITHM],
            audience=WIDGET_AUDIENCE,
            issuer=WIDGET_ISSUER,
        )
    except JWTError as exc:
        raise WidgetTokenError(f"invalid widget token: {exc}") from exc

    required = (
        "sub",
        "tenant_id",
        "assessment_id",
        "user_role",
        "scope",
        "iat",
        "exp",
        "jti",
    )
    missing = [key for key in required if key not in decoded]
    if missing:
        raise WidgetTokenError(
            f"widget token missing required claims: {', '.join(missing)}"
        )

    iat = int(decoded["iat"])
    exp = int(decoded["exp"])
    if exp - iat > WIDGET_TOKEN_MAX_TTL_SECONDS:
        raise WidgetTokenError(
            "widget token TTL exceeds 15-minute ceiling"
        )

    return WidgetClaims(
        sub=str(decoded["sub"]),
        tenant_id=str(decoded["tenant_id"]),
        assessment_id=str(decoded["assessment_id"]),
        user_role=str(decoded["user_role"]),
        scope=str(decoded["scope"]),
        iat=iat,
        exp=exp,
        jti=str(decoded["jti"]),
    )
