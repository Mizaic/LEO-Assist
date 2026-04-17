"""VT-LEO-AI-168 -- PATCH /auth/session/density router contract.

Mounts the auth router on a bare FastAPI app and exercises the density
endpoint with a mocked session store and density_state module so the
test runs without Redis or Neo4j.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# The auth router lives in services/api/app/routers/auth.py; expose the
# `app` package on sys.path before the import fires.
_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

# Stub out collaborators that hit Redis or Neo4j at import time so the
# router module imports cleanly.
sys.modules.setdefault(
    "app.services.session_store",
    MagicMock(
        COOKIE_NAME="leo_session",
        SESSION_TTL=86400,
        create_session_id=MagicMock(return_value="sess-1"),
        delete_session=MagicMock(),
        load_session=MagicMock(return_value=None),
        save_session=MagicMock(),
    ),
)


@pytest.fixture()
def client_with_session(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app.routers import auth as auth_router

    monkeypatch.setattr(
        auth_router,
        "load_session",
        MagicMock(return_value={"email": "user@example.com"}),
    )
    monkeypatch.setattr(
        auth_router,
        "fetch_role_state",
        MagicMock(
            return_value=type(
                "RS", (), {"selected_role": None, "allowed_roles": []}
            )
        ),
    )
    monkeypatch.setattr(
        auth_router, "fetch_density", MagicMock(return_value="comfortable")
    )
    monkeypatch.setattr(
        auth_router, "set_density", MagicMock(return_value="compact")
    )
    app = FastAPI()
    app.include_router(auth_router.router)
    test_client = TestClient(app)
    test_client.cookies.set(auth_router.COOKIE_NAME, "sess-1")
    return test_client


# -----------------------------------------------------------------------------
# VT-168-TC-004  -- 401 without session cookie
# -----------------------------------------------------------------------------
def test_patch_density_requires_session(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import auth as auth_router

    app = FastAPI()
    app.include_router(auth_router.router)
    client = TestClient(app)
    res = client.patch("/auth/session/density", json={"density": "compact"})
    assert res.status_code == 401
    assert res.json()["detail"] == "not_authenticated"


# -----------------------------------------------------------------------------
# VT-168-TC-005  -- 400 invalid_density
# -----------------------------------------------------------------------------
def test_patch_density_rejects_unknown_tier(
    client_with_session: TestClient,
) -> None:
    from app.routers import auth as auth_router
    from libs.auth.density_state import DensityNotAllowedError

    auth_router.set_density = MagicMock(  # type: ignore[assignment]
        side_effect=DensityNotAllowedError("huge")
    )
    res = client_with_session.patch(
        "/auth/session/density", json={"density": "huge"}
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "invalid_density"


def test_patch_density_rejects_missing_body(
    client_with_session: TestClient,
) -> None:
    res = client_with_session.patch("/auth/session/density", json={})
    assert res.status_code == 400
    assert res.json()["detail"] == "missing_density"


# -----------------------------------------------------------------------------
# VT-168-TC-006  -- 200 happy path
# -----------------------------------------------------------------------------
def test_patch_density_returns_stored_value(
    client_with_session: TestClient,
) -> None:
    res = client_with_session.patch(
        "/auth/session/density", json={"density": "compact"}
    )
    assert res.status_code == 200
    assert res.json() == {"density_preference": "compact"}


# -----------------------------------------------------------------------------
# Session payload exposes density_preference
# -----------------------------------------------------------------------------
def test_session_payload_includes_density_preference(
    client_with_session: TestClient,
) -> None:
    res = client_with_session.get("/auth/session")
    assert res.status_code == 200
    body = res.json()
    assert body["density_preference"] == "comfortable"


def test_unauthenticated_session_payload_includes_density_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.routers import auth as auth_router

    app = FastAPI()
    app.include_router(auth_router.router)
    client = TestClient(app)
    res = client.get("/auth/session")
    assert res.status_code == 200
    assert res.json()["density_preference"] is None
