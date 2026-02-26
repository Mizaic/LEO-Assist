"""FastAPI dependencies for auth and session."""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException

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
