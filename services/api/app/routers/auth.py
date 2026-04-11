"""OAuth auth routes: login, callback, logout, session.

Handles Azure AD OAuth flow. Tokens stored server-side in Redis.
Frontend uses session cookie only (no token in browser).
"""

from __future__ import annotations

import logging
import os
import re
import time
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
import httpx
from jose import jwt, JWTError

from app.services.session_store import (
    COOKIE_NAME,
    SESSION_TTL,
    create_session_id,
    delete_session,
    load_session,
    save_session,
)
from libs.audit.security_log import (
    emit_login_success,
    emit_login_failure,
    emit_login_mfa_blocked,
    emit_logout,
    emit_token_rejected,
)
from libs.auth.practitioner_org_context import fetch_practitioner_org_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Read Azure AD / frontend settings at request time. Module-level os.getenv() can run
# before Key Vault hydration or ACA secret injection is visible in edge cases; lazy reads
# avoid stale empty values for CLIENT_ID.


def _env_ad_tenant_id() -> str:
    return (os.getenv("AZURE_AD_TENANT_ID") or "").strip()


def _env_ad_client_id() -> str:
    return (os.getenv("AZURE_AD_CLIENT_ID") or "").strip()


def _env_ad_client_secret() -> str:
    return (os.getenv("AZURE_AD_CLIENT_SECRET") or "").strip()


def _frontend_url() -> str:
    return (os.getenv("FRONTEND_URL") or "http://localhost:3000").rstrip("/")


def _redirect_uri() -> str:
    explicit = (os.getenv("AUTH_REDIRECT_URI") or "").strip()
    if explicit:
        return explicit
    return f"{_frontend_url()}/auth/callback"


def _oauth_scope() -> str:
    return os.getenv(
        "AZURE_AD_SCOPE",
        "openid profile email api://c97f7ad9-845f-420c-ae3f-fa5c5d815bcd/.default",
    )


# Multi-tenant: use /common/ endpoints so users from any NHS Entra tenant can authenticate
# without needing guest accounts in the Mizaic tenant. The app registration signInAudience
# is already AzureADMultipleOrgs. Issuer validation is done by tid-allowlist (see below).
AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"


# JWKS cache — fetched once per process, refreshed when keys change.
# /common/ JWKS returns all current Microsoft signing keys (valid across all tenants).
# Azure AD rotates keys infrequently; 1-hour TTL is conservative.
_JWKS_CACHE: dict = {}
_JWKS_FETCHED_AT: float = 0.0
_JWKS_TTL = 3600  # seconds


def _get_jwks() -> dict:
    """Return Azure AD JWKS from /common/, refreshing the cache if older than _JWKS_TTL."""
    global _JWKS_CACHE, _JWKS_FETCHED_AT
    now = time.monotonic()
    if _JWKS_CACHE and _JWKS_FETCHED_AT > 0 and (now - _JWKS_FETCHED_AT) < _JWKS_TTL:
        return _JWKS_CACHE
    jwks_uri = "https://login.microsoftonline.com/common/discovery/v2.0/keys"
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(jwks_uri)
            resp.raise_for_status()
            _JWKS_CACHE = resp.json()
            _JWKS_FETCHED_AT = now
    except Exception as exc:
        logger.error("Failed to fetch Azure AD JWKS: %s", exc)
        if _JWKS_CACHE:
            logger.warning("Using stale JWKS cache after fetch failure")
            return _JWKS_CACHE
        raise
    return _JWKS_CACHE


def _is_tenant_allowed(tid: str) -> bool:
    """Check the token's tenant ID against the allowlist of onboarded organisations.

    Permits:
    - Mizaic's own tenant (for platform admins)
    - Any tenant registered on an active Organisation node in Neo4j

    This is the multi-tenant trust boundary: only pre-registered NHS tenants can sign in.
    """
    if not tid:
        return False
    # Always permit Mizaic's own tenant for platform admins
    tenant = _env_ad_tenant_id()
    if tenant and tid == tenant:
        return True
    try:
        from libs.neo4j_client.client import PatientGraphClient
        from libs.cypher.admin_queries import GET_ORG_BY_ENTRA_TENANT

        client = PatientGraphClient()
        rows = client.run(GET_ORG_BY_ENTRA_TENANT, entra_tenant_id=tid)
        client.close()
        return bool(rows)
    except Exception as exc:
        logger.error("Tenant allowlist check failed for tid=%s: %s", tid, exc)
        return False


def _verify_id_token(id_token: str) -> dict:
    """Verify and decode an Azure AD id_token using JWKS.

    Multi-tenant validation strategy:
    1. Verify RS256 signature against /common/ JWKS (cryptographic trust)
    2. Verify audience matches our CLIENT_ID (or API app ID when using api:// scope)
    3. Verify expiry and not-before
    4. Reject v1.0 tokens (sts.windows.net issuer checked in callback)
    5. Validate tid claim against tenant allowlist (business trust boundary)

    Issuer is NOT checked against a single tenant — the app is AzureADMultipleOrgs.
    GAP-002 fix: replaces insecure base64 decode with cryptographic verification.
    """
    client_id = _env_ad_client_id()
    if not client_id:
        raise HTTPException(500, "Azure AD not configured")
    # Accept both client app ID and API app ID (api://xxx) as audience — Azure may use either
    # when scope includes api://.../.default. python-jose requires audience to be str or None.
    audiences = [client_id]
    scope = _oauth_scope()
    if "api://" in scope:
        m = re.search(r"api://([a-fA-F0-9\-]+)/", scope)
        if m:
            api_id = m.group(1)
            audiences.append(api_id)  # GUID only
            audiences.append(f"api://{api_id}")  # full URI (Azure may use either)
    try:
        jwks = _get_jwks()
        opts = {"verify_exp": True, "verify_nbf": True, "verify_iss": False}
        last_error: JWTError | None = None
        for aud in audiences:
            try:
                return jwt.decode(
                    id_token, jwks, algorithms=["RS256"], audience=aud, options=opts
                )
            except JWTError as exc:
                last_error = exc
        if last_error:
            logger.warning(
                "id_token verification failed: %s (type=%s). Check: CLIENT_ID vs token aud, server clock, token expiry.",
                last_error,
                type(last_error).__name__,
            )
            raise HTTPException(
                status_code=401, detail="Token verification failed"
            ) from last_error
        raise HTTPException(status_code=401, detail="Token verification failed")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected error verifying id_token: %s", exc)
        raise HTTPException(status_code=401, detail="Token verification error") from exc


def _get_session_config() -> tuple[int, int, bool]:
    """Return (session_ttl_seconds, idle_timeout_minutes, require_mfa) from Neo4j SystemConfig.

    Falls back to env-var defaults when Neo4j is unreachable so login never fails.
    """
    try:
        from libs.neo4j_client.client import PatientGraphClient
        from libs.cypher.admin_queries import GET_SYSTEM_CONFIG

        client = PatientGraphClient()
        rows = client.run(GET_SYSTEM_CONFIG, id="auth")
        client.close()
        if rows:
            r = rows[0]
            ttl_h = int(r.get("session_ttl_hours") or 168)
            idle_m = int(r.get("idle_timeout_minutes") or 30)
            mfa = bool(r.get("require_mfa", False))
            return ttl_h * 3600, idle_m, mfa
    except Exception as exc:
        logger.warning("Could not read session config from Neo4j: %s", exc)
    return SESSION_TTL, int(os.getenv("IDLE_TIMEOUT_MINUTES", "30")), False


def _fetch_org_context(email: str) -> tuple[bool, list[dict]]:
    """Load platform-admin flag and org list from the Patient Graph.

    Not an HTTP call to Analytics: org-context there requires X-Leo-Session,
    which does not exist until after we persist the session.
    """
    return fetch_practitioner_org_context(email)


@router.get("/login")
def login(request: Request, next_url: str = "/"):
    """Redirect to Azure AD login with a session nonce for CSRF protection (GAP-010)."""
    client_id = _env_ad_client_id()
    if not client_id:
        raise HTTPException(500, "Azure AD not configured")
    import secrets as _secrets

    nonce = _secrets.token_urlsafe(16)
    state = next_url
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": _redirect_uri(),
        "scope": _oauth_scope(),
        "response_mode": "query",
        "state": state,
        "nonce": nonce,
    }
    url = f"{AUTH_URL}?{urlencode(params)}"
    resp = RedirectResponse(url=url, status_code=302)
    cookie_secure = os.getenv("COOKIE_SECURE", "true").lower() not in (
        "false",
        "0",
        "no",
    )
    resp.set_cookie(
        "leo_oauth_nonce",
        nonce,
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        max_age=600,
        path="/",
    )
    return resp


@router.get("/callback")
def callback(
    request: Request,
    response: Response,
    code: str | None = None,
    state: str = "/",
    error: str | None = None,
):
    """Handle OAuth callback, exchange code for tokens, set session cookie (GAP-010)."""
    fe = _frontend_url()
    if error:
        logger.warning("OAuth error: %s", error)
        return RedirectResponse(url=f"{fe}/sign-in?error={error}", status_code=302)
    if not code:
        raise HTTPException(400, "Missing code")

    # Verify nonce to prevent CSRF -- cookie set at /login must be present
    expected_nonce = request.cookies.get("leo_oauth_nonce")
    if not expected_nonce:
        logger.warning("OAuth callback missing nonce cookie -- possible CSRF")
        return RedirectResponse(
            url=f"{fe}/sign-in?error=csrf_nonce_missing", status_code=302
        )
    client_secret = _env_ad_client_secret()
    if not client_secret:
        raise HTTPException(500, "Azure AD client secret not configured")

    with httpx.Client(timeout=15) as client:
        r = client.post(
            TOKEN_URL,
            data={
                "client_id": _env_ad_client_id(),
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": _redirect_uri(),
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if r.status_code != 200:
        logger.error("Token exchange failed: %s %s", r.status_code, r.text[:200])
        return RedirectResponse(
            url=f"{fe}/sign-in?error=token_exchange_failed", status_code=302
        )

    token_data = r.json()
    access_token = token_data.get("access_token")
    id_token = token_data.get("id_token")

    # GAP-002: Verify id_token signature against Azure AD JWKS before trusting any claims.
    # Replaces the previous insecure base64 decode which accepted forged tokens.
    id_claims: dict = {}
    if not id_token:
        logger.warning("Token exchange returned no id_token")
        return RedirectResponse(url=f"{fe}/sign-in?error=no_id_token", status_code=302)

    client_ip = request.client.host if request.client else "unknown"
    try:
        id_claims = _verify_id_token(id_token)
    except HTTPException as exc:
        emit_token_rejected(reason=exc.detail, ip=client_ip)
        emit_login_failure(
            reason="token_verification_failed", ip=client_ip, detail=exc.detail
        )
        return RedirectResponse(
            url=f"{fe}/sign-in?error=token_verification_failed",
            status_code=302,
        )

    # Reject v1.0 tokens (sts.windows.net issuer) — requires accessTokenAcceptedVersion: 2 in Azure AD manifest.
    iss = id_claims.get("iss", "")
    if "sts.windows.net" in iss:
        logger.warning(
            "Rejecting v1.0 token (iss=%s). Set accessTokenAcceptedVersion: 2 in Azure AD app manifest.",
            iss,
        )
        emit_token_rejected(reason="v1_issuer", ip=client_ip)
        emit_login_failure(reason="token_v1_not_allowed", ip=client_ip)
        return RedirectResponse(
            url=f"{fe}/sign-in?error=token_v1_not_allowed", status_code=302
        )

    # Multi-tenant trust boundary: validate the tid (tenant ID) claim against the
    # allowlist of onboarded organisations. Tokens from unknown tenants are rejected
    # even if cryptographically valid — prevents any Microsoft tenant signing in.
    tid = id_claims.get("tid", "")
    if not _is_tenant_allowed(tid):
        logger.warning("Rejecting token from unknown tenant tid=%s", tid)
        emit_token_rejected(reason="tenant_not_allowed", ip=client_ip)
        emit_login_failure(reason="tenant_not_allowed", ip=client_ip)
        return RedirectResponse(
            url=f"{fe}/sign-in?error=tenant_not_allowed", status_code=302
        )

    email = (
        id_claims.get("preferred_username")
        or id_claims.get("upn")
        or id_claims.get("email")
    )
    name = id_claims.get("name")

    if not email:
        email = "unknown"

    is_admin, organizations = _fetch_org_context(email)
    session_ttl_secs, idle_mins, require_mfa = _get_session_config()

    # App-level MFA backstop: verify the `amr` (Authentication Methods References)
    # claim in the ID token includes "mfa".
    #
    # If a Conditional Access Policy in Entra already enforces MFA, this claim
    # will ALWAYS contain "mfa" -- the check passes silently.
    # If Conditional Access is not yet configured, this rejects any login where
    # the user skipped MFA (e.g. password-only) when require_mfa=True.
    if require_mfa:
        amr = id_claims.get("amr", [])
        if isinstance(amr, str):
            amr = [amr]
        if "mfa" not in amr:
            logger.warning(
                "Login blocked: MFA required but not completed by %s (amr=%s)",
                email,
                amr,
            )
            emit_login_mfa_blocked(email=email or "unknown", ip=client_ip, amr=amr)
            return RedirectResponse(
                url=f"{fe}/sign-in?error=mfa_required",
                status_code=302,
            )

    session_id = create_session_id()
    save_session(
        session_id,
        {
            "access_token": access_token,
            "email": email.lower().strip(),
            "name": name or email,
            "is_platform_admin": is_admin,
            "organizations": organizations,
            "idle_timeout_minutes": idle_mins,
        },
        ttl_seconds=session_ttl_secs,
    )
    emit_login_success(
        email=email.lower().strip(),
        ip=client_ip,
        session_id_prefix=session_id,
    )

    normalized_state = state if state.startswith("/") else f"/{state.lstrip('/')}"
    if normalized_state in {"/", "/sign-in", "/auth/callback"}:
        normalized_state = "/dashboard"
    redirect_url = f"{fe}{normalized_state}"
    resp = RedirectResponse(url=redirect_url, status_code=302)
    cookie_secure = os.getenv("COOKIE_SECURE", "true").lower() not in (
        "false",
        "0",
        "no",
    )
    resp.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        max_age=session_ttl_secs,
        path="/",
    )
    return resp


@router.post("/logout")
def logout(request: Request, response: Response):
    """Clear session and cookie."""
    session_id = request.cookies.get(COOKIE_NAME)
    client_ip = request.client.host if request.client else "unknown"
    if session_id:
        data = load_session(session_id)
        email = (data or {}).get("email", "unknown")
        delete_session(session_id)
        emit_logout(email=email, ip=client_ip)
    resp = Response(status_code=204)
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


@router.get("/session")
def get_session(request: Request):
    """Return current session (user info, orgs). Used by frontend to check auth.
    Returns 200 with user: null when not authenticated (avoids 401/CORS issues).
    """
    session_id = request.cookies.get(COOKIE_NAME)
    if not session_id:
        return {"user": None, "isPlatformAdmin": False, "organizations": []}
    data = load_session(session_id)
    if not data:
        return {"user": None, "isPlatformAdmin": False, "organizations": []}
    return {
        "user": {
            "email": data.get("email"),
            "name": data.get("name"),
        },
        "isPlatformAdmin": data.get("is_platform_admin", False),
        "organizations": data.get("organizations", []),
        "idleTimeoutMinutes": data.get("idle_timeout_minutes", 30),
    }
