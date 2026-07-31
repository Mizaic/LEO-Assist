"""GET /auth/session needs_role_choice and PATCH session role confirmation.

Covers session-scoped ui_role_confirmed (Redis) for multi-role practitioners.
See DI-FAF97A8C / UN-852649B0.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

sys.modules.setdefault(
    "app.services.session_store",
    MagicMock(
        COOKIE_NAME="leo_session",
        SESSION_TTL=86400,
        create_session_id=MagicMock(return_value="sess-1"),
        delete_session=MagicMock(),
        load_session=MagicMock(return_value=None),
        save_session=MagicMock(),
        touch_session=MagicMock(
            return_value={"email": "user@example.com", "idle_timeout_minutes": 30}
        ),
    ),
)


@pytest.fixture()
def client_session_template(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app.routers import auth as auth_router

    monkeypatch.setattr(
        auth_router,
        "fetch_density",
        MagicMock(return_value=None),
    )
    app = FastAPI()
    app.include_router(auth_router.router)
    test_client = TestClient(app)
    test_client.cookies.set(auth_router.COOKIE_NAME, "sess-1")
    return test_client


def test_needs_role_choice_true_multi_role_new_session(
    monkeypatch: pytest.MonkeyPatch, client_session_template: TestClient
) -> None:
    from app.routers import auth as auth_router
    from libs.auth.role_state import RoleState

    monkeypatch.setattr(
        auth_router,
        "load_session",
        MagicMock(return_value={"email": "user@example.com"}),
    )
    monkeypatch.setattr(
        auth_router,
        "fetch_role_state",
        MagicMock(
            return_value=RoleState(
                selected_role="triage_clinician",
                allowed_roles=["triage_clinician", "clinical_coder"],
            )
        ),
    )
    res = client_session_template.get("/auth/session")
    assert res.status_code == 200
    assert res.json()["needs_role_choice"] is True


def test_needs_role_choice_false_after_session_confirmed(
    monkeypatch: pytest.MonkeyPatch, client_session_template: TestClient
) -> None:
    from app.routers import auth as auth_router
    from libs.auth.role_state import RoleState

    monkeypatch.setattr(
        auth_router,
        "load_session",
        MagicMock(
            return_value={
                "email": "user@example.com",
                "ui_role_confirmed": True,
            }
        ),
    )
    monkeypatch.setattr(
        auth_router,
        "fetch_role_state",
        MagicMock(
            return_value=RoleState(
                selected_role="triage_clinician",
                allowed_roles=["triage_clinician", "clinical_coder"],
            )
        ),
    )
    res = client_session_template.get("/auth/session")
    assert res.status_code == 200
    assert res.json()["needs_role_choice"] is False


def test_needs_role_choice_false_single_role(
    monkeypatch: pytest.MonkeyPatch, client_session_template: TestClient
) -> None:
    from app.routers import auth as auth_router
    from libs.auth.role_state import RoleState

    monkeypatch.setattr(
        auth_router,
        "load_session",
        MagicMock(return_value={"email": "user@example.com"}),
    )
    monkeypatch.setattr(
        auth_router,
        "fetch_role_state",
        MagicMock(
            return_value=RoleState(
                selected_role="triage_clinician",
                allowed_roles=["triage_clinician"],
            )
        ),
    )
    res = client_session_template.get("/auth/session")
    assert res.status_code == 200
    assert res.json()["needs_role_choice"] is False


def test_patch_session_role_marks_session_confirmed(
    monkeypatch: pytest.MonkeyPatch, client_session_template: TestClient
) -> None:
    from app.routers import auth as auth_router
    from libs.auth.role_state import RoleState

    session_data: dict = {"email": "user@example.com"}
    monkeypatch.setattr(
        auth_router,
        "load_session",
        MagicMock(return_value=session_data),
    )
    save_mock = MagicMock()
    monkeypatch.setattr(auth_router, "save_session", save_mock)
    monkeypatch.setattr(
        auth_router,
        "fetch_role_state",
        MagicMock(
            return_value=RoleState(
                selected_role="triage_clinician",
                allowed_roles=["triage_clinician", "clinical_coder"],
            )
        ),
    )
    monkeypatch.setattr(
        auth_router,
        "set_selected_role",
        MagicMock(
            return_value=RoleState(
                selected_role="clinical_coder",
                allowed_roles=["triage_clinician", "clinical_coder"],
            )
        ),
    )
    monkeypatch.setattr(
        auth_router,
        "_get_session_config",
        MagicMock(return_value=(3600, 30, False)),
    )

    res = client_session_template.patch(
        "/auth/session/role",
        json={"role": "clinical_coder"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["selected_role"] == "clinical_coder"
    assert body["needs_role_choice"] is False
    save_mock.assert_called()
    pos = save_mock.call_args[0]
    assert len(pos) >= 2
    saved = pos[1]
    assert saved.get("ui_role_confirmed") is True
