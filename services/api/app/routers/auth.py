"""OAuth auth routes: login, callback, logout, session.

Handles Azure AD OAuth flow. Tokens stored server-side in Redis.
Frontend uses session cookie only (no token in browser).
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
import httpx

from app.services.session_store import (
    COOKIE_NAME,
    SESSION_TTL,
    create_session_id,
    delete_session,
    load_session,
    save_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

TENANT_ID = os.getenv("AZURE_AD_TENANT_ID")
CLIENT_ID = os.getenv("AZURE_AD_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_AD_CLIENT_SECRET")
# OAuth callback - frontend URL; frontend redirects to backend to complete. Add to Azure AD app redirect URIs.
REDIRECT_URI = os.getenv("AUTH_REDIRECT_URI") or f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/auth/callback"
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
SCOPE = os.getenv("AZURE_AD_SCOPE", "openid profile email api://c97f7ad9-845f-420c-ae3f-fa5c5d815bcd/.default")

# v2.0 endpoints only (not v1.0 / sts.windows.net). Requires accessTokenAcceptedVersion: 2 in app manifest.
AUTH_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/authorize"
TOKEN_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
ANALYTICS_BASE = os.getenv("ANALYTICS_API_BASE", "http://localhost:8003")


def _fetch_org_context(email: str) -> tuple[bool, list[dict]]:
    """Fetch org context from Analytics API. Returns (is_platform_admin, organizations)."""
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(
                f"{ANALYTICS_BASE.rstrip('/')}/analytics/auth/org-context",
                params={"email": email},
            )
            if r.status_code != 200:
                return False, []
            data = r.json()
            orgs = data.get("organizations") or []
            is_admin = data.get("user", {}).get("is_platform_admin", False)
            return is_admin, orgs
    except Exception as e:
        logger.warning("Failed to fetch org context: %s", e)
        return False, []


@router.get("/login")
def login(request: Request, next_url: str = "/"):
    """Redirect to Azure AD login."""
    if not TENANT_ID or not CLIENT_ID:
        raise HTTPException(500, "Azure AD not configured")
    state = next_url
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "response_mode": "query",
        "state": state,
    }
    url = f"{AUTH_URL}?{urlencode(params)}"
    return RedirectResponse(url=url, status_code=302)


@router.get("/callback")
def callback(
    request: Request,
    response: Response,
    code: str | None = None,
    state: str = "/",
    error: str | None = None,
):
    """Handle OAuth callback, exchange code for tokens, set session cookie."""
    if error:
        logger.warning("OAuth error: %s", error)
        return RedirectResponse(url=f"{FRONTEND_URL}/sign-in?error={error}", status_code=302)
    if not code:
        raise HTTPException(400, "Missing code")
    if not CLIENT_SECRET:
        raise HTTPException(500, "Azure AD client secret not configured")

    with httpx.Client(timeout=15) as client:
        r = client.post(
            TOKEN_URL,
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if r.status_code != 200:
        logger.error("Token exchange failed: %s %s", r.status_code, r.text[:200])
        return RedirectResponse(url=f"{FRONTEND_URL}/sign-in?error=token_exchange_failed", status_code=302)

    token_data = r.json()
    access_token = token_data.get("access_token")
    id_token = token_data.get("id_token")

    # Enforce v2.0 tokens only — reject v1.0 (sts.windows.net) at login
    import base64
    import json

    for token in (access_token, id_token):
        if token:
            try:
                payload_b64 = token.split(".")[1]
                payload_b64 += "=" * (4 - len(payload_b64) % 4)
                claims = json.loads(base64.urlsafe_b64decode(payload_b64))
                iss = claims.get("iss", "")
                if "sts.windows.net" in iss:
                    logger.warning("Rejecting v1.0 token (iss=%s). Set accessTokenAcceptedVersion: 2 in Azure AD app manifest.", iss)
                    return RedirectResponse(
                        url=f"{FRONTEND_URL}/sign-in?error=token_v1_not_allowed",
                        status_code=302,
                    )
            except Exception:
                pass

    email = None
    name = None
    if id_token:
        try:
            payload_b64 = id_token.split(".")[1]
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            claims = base64.urlsafe_b64decode(payload_b64)
            data = json.loads(claims)
            email = data.get("preferred_username") or data.get("upn") or data.get("email")
            name = data.get("name")
        except Exception:
            pass

    if not email:
        email = "unknown"

    is_admin, organizations = _fetch_org_context(email)

    session_id = create_session_id()
    save_session(
        session_id,
        {
            "access_token": access_token,
            "email": email.lower().strip(),
            "name": name or email,
            "is_platform_admin": is_admin,
            "organizations": organizations,
        },
    )

    redirect_url = f"{FRONTEND_URL}{state}" if state.startswith("/") else f"{FRONTEND_URL}/{state.lstrip('/')}"
    resp = RedirectResponse(url=redirect_url, status_code=302)
    resp.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=False,  # True in production with HTTPS
        samesite="lax",
        max_age=SESSION_TTL,
        path="/",
    )
    return resp


@router.post("/logout")
def logout(request: Request, response: Response):
    """Clear session and cookie."""
    session_id = request.cookies.get(COOKIE_NAME)
    if session_id:
        delete_session(session_id)
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
    }
