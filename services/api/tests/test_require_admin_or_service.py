"""Unit tests for require_admin_or_service -- VT-LEO-AI-166 (DI-LEO-AI-167).

Covers the generic service-to-service auth dependency that lets another
internal service call an admin endpoint with a SERVICE_AUTH_SECRET Bearer
token, while the admin UI continues to call the same endpoint with a
session cookie.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.deps import (
    SERVICE_ACCOUNT_EMAIL,
    require_admin_or_service,
)
from libs.auth.org_scope import CallerScope


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/protected")
    def protected(scope: CallerScope = Depends(require_admin_or_service)) -> dict:
        return {"email": scope.email, "is_admin": scope.is_admin}

    return app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(_app())


# -- service-auth Bearer token path ----------------------------------------


def test_service_auth_bearer_with_correct_secret_returns_service_account(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SERVICE_AUTH_SECRET", "correct-secret")
    resp = client.get(
        "/protected", headers={"Authorization": "Bearer correct-secret"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == SERVICE_ACCOUNT_EMAIL
    assert body["is_admin"] is True


def test_service_auth_bearer_with_wrong_secret_returns_401(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SERVICE_AUTH_SECRET", "correct-secret")
    resp = client.get(
        "/protected", headers={"Authorization": "Bearer wrong-secret"}
    )
    assert resp.status_code == 401
    assert "Invalid service auth token" in resp.json()["detail"]


def test_bearer_header_ignored_when_secret_unset_falls_back_to_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Local dev: SERVICE_AUTH_SECRET unset means a Bearer header is ignored
    and the request must still produce a session cookie. Without one it is
    rejected -- the dev bypass is not used by this dependency."""
    monkeypatch.delenv("SERVICE_AUTH_SECRET", raising=False)
    resp = client.get(
        "/protected", headers={"Authorization": "Bearer anything"}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not authenticated"


# -- session cookie path ---------------------------------------------------


def test_session_cookie_admin_returns_admin_scope(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SERVICE_AUTH_SECRET", "")
    fake_session = {
        "email": "admin@nhs.example",
        "is_platform_admin": True,
    }
    with patch("app.deps.load_session", return_value=fake_session):
        resp = client.get("/protected", cookies={"leo_session": "sess123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "admin@nhs.example"
    assert body["is_admin"] is True


def test_no_session_and_no_bearer_returns_401(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SERVICE_AUTH_SECRET", "")
    resp = client.get("/protected")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not authenticated"


def test_session_cookie_non_admin_returns_403(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SERVICE_AUTH_SECRET", "")
    fake_session = {
        "email": "clinician@nhs.example",
        "is_platform_admin": False,
    }
    non_admin_scope = CallerScope(
        email="clinician@nhs.example",
        is_admin=False,
        org_ids=["gp-1"],
        scope_type="gp",
        primary_org_id="gp-1",
    )
    with patch("app.deps.load_session", return_value=fake_session), patch(
        "app.deps.PatientGraphClient"
    ), patch(
        "app.deps.resolve_caller_scope", return_value=non_admin_scope
    ):
        resp = client.get("/protected", cookies={"leo_session": "sess123"})
    assert resp.status_code == 403
    assert "Platform admin access required" in resp.json()["detail"]
