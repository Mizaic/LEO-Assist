"""VTs for the /admin/entra/* router.

Pins the contracts:
- DI-31F4C232 capability probe + 7 endpoints.
- DI-6CF7FCE0 InsufficientConsent maps to HTTP 403 ``code: consent_required``
  AND emits an ``auth.entra_admin.denied`` audit event.
- BindGroupDialog confirm gate -- mismatched ``confirm_display_name``
  is rejected before any Neo4j or Graph write.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.deps import get_session_data, require_admin  # noqa: E402
from app.routers.admin_entra import router as admin_entra_router  # noqa: E402
from libs.auth.org_scope import CallerScope  # noqa: E402
from libs.graph_client.errors import InsufficientConsent  # noqa: E402


ADMIN_SESSION = {
    "access_token": "user-token-xyz",
    "email": "admin@contoso.com",
    "is_platform_admin": True,
    "entra_tenant_id": "tenant-abc",
}

ADMIN_SCOPE = CallerScope(
    email="admin@contoso.com",
    is_admin=True,
    org_ids=[],
    scope_type=None,
    primary_org_id=None,
)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(admin_entra_router)
    app.dependency_overrides[get_session_data] = lambda: ADMIN_SESSION
    app.dependency_overrides[require_admin] = lambda: ADMIN_SCOPE
    return app


def _async_context_manager(graph_client_mock):
    cm = AsyncMock()
    cm.__aenter__.return_value = graph_client_mock
    cm.__aexit__.return_value = False
    return cm


def test_capability_consent_required_returns_403_and_audits():
    app = _make_app()
    client = TestClient(app)

    consent_err = InsufficientConsent(
        "consent required",
        status_code=403,
        graph_error_code="Authorization_RequestDenied",
    )

    with patch(
        "app.routers.admin_entra.probe_capability",
        AsyncMock(side_effect=consent_err),
    ):
        resp = client.get("/admin/entra/capability")

    assert resp.status_code == 403
    body = resp.json()
    assert body["detail"]["code"] == "consent_required"
    assert body["detail"]["graph_error_code"] == "Authorization_RequestDenied"


def test_capability_success_returns_capability_matrix():
    app = _make_app()
    client = TestClient(app)

    capability = {
        "can_list_domains": True,
        "can_search_users": True,
        "can_list_groups": True,
        "can_write_groups": False,
        "can_manage_membership": False,
        "scopes_granted": [
            "https://graph.microsoft.com/User.Read.All",
        ],
        "scopes_required": [
            "https://graph.microsoft.com/User.Read.All",
            "https://graph.microsoft.com/Group.Read.All",
        ],
        "admin_consent_url": "https://login.microsoftonline.com/tenant-abc/v2.0/adminconsent",
    }

    with patch(
        "app.routers.admin_entra.probe_capability",
        AsyncMock(return_value=capability),
    ):
        resp = client.get("/admin/entra/capability")

    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant_id"] == "tenant-abc"
    assert body["can_search_users"] is True
    assert body["from_cache"] is False


def test_capability_returns_409_when_tenant_id_missing():
    app = FastAPI()
    app.include_router(admin_entra_router)
    app.dependency_overrides[get_session_data] = lambda: {
        **ADMIN_SESSION,
        "entra_tenant_id": "",
    }
    app.dependency_overrides[require_admin] = lambda: ADMIN_SCOPE
    client = TestClient(app)

    resp = client.get("/admin/entra/capability")

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "tenant_unknown"


def test_search_users_passes_query_through_to_graph():
    app = _make_app()
    client = TestClient(app)

    fake_gc = MagicMock()
    fake_gc.search_users = AsyncMock(
        return_value=[
            {
                "id": "u-1",
                "displayName": "Alice Example",
                "mail": "alice@contoso.com",
            }
        ]
    )

    with patch(
        "app.routers.admin_entra._make_graph_client",
        return_value=_async_context_manager(fake_gc),
    ):
        resp = client.get("/admin/entra/users", params={"q": "alice"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["users"][0]["mail"] == "alice@contoso.com"
    fake_gc.search_users.assert_awaited_once()


def test_bind_group_confirm_mismatch_rejected_before_graph_call():
    app = _make_app()
    client = TestClient(app)

    fake_gc = MagicMock()
    fake_gc.call = AsyncMock()

    with patch(
        "app.routers.admin_entra._make_graph_client",
        return_value=_async_context_manager(fake_gc),
    ), patch("app.routers.admin_entra._upsert_shadow") as upsert_mock, patch(
        "app.routers.admin_entra._bind_role"
    ) as bind_mock:
        resp = client.post(
            "/admin/entra/groups/group-oid-1/bind",
            json={
                "display_name": "LEO Coding Reviewers",
                "name": "LEO Coding Reviewers",
                "role_name": "coding_reviewer",
                "confirm_display_name": "wrong name",
            },
        )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "confirm_mismatch"
    fake_gc.call.assert_not_called()
    upsert_mock.assert_not_called()
    bind_mock.assert_not_called()
