"""FastAPI dependencies for auth and session."""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Query

from libs.auth.org_scope import CallerScope, resolve_caller_scope
from libs.neo4j_client.client import PatientGraphClient
from app.services.session_store import COOKIE_NAME, load_session


def get_session_data(
    leo_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> dict:
    """Dependency that returns session data or raises 401."""
    if not leo_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    data = load_session(leo_session)
    if not data:
        raise HTTPException(status_code=401, detail="Session expired")
    return data


def get_access_token(session_data: dict = Depends(get_session_data)) -> str:
    """Dependency that returns the access token from session."""
    token = session_data.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="No access token")
    return token


def get_user_email(session_data: dict = Depends(get_session_data)) -> str:
    """Dependency that returns the normalized user email from session."""
    email = (session_data.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="No user email in session")
    return email


def get_caller_scope_from_request(
    x_user_email: Annotated[str | None, Header(alias="X-User-Email")] = None,
    email: Annotated[str | None, Query()] = None,
    leo_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> CallerScope:
    """Resolve caller scope from header/query, with session-cookie fallback.

    This keeps org scoping working for direct UI rewrites (e.g. /api/training/*)
    that do not pass X-User-Email but do include the auth session cookie.
    """
    caller_email = (x_user_email or email or "").strip().lower()
    if not caller_email and leo_session:
        session_data = load_session(leo_session) or {}
        caller_email = (session_data.get("email") or "").strip().lower()

    if not caller_email:
        raise HTTPException(
            status_code=401,
            detail="Caller identity required: set X-User-Email header or ?email= param",
        )

    client = PatientGraphClient()
    try:
        return resolve_caller_scope(client, caller_email)
    finally:
        client.close()
