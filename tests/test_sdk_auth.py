"""LEO widget SDK auth verification tests.

Atlas trace:
  DI: DI-A1206416
  DO: DO-5C88CA8F
  VTs:
    - VT-7EF430DD (token-mint endpoint enforces server-to-server)
    - VT-8CADA244 (proxy returns 403 on assessment-id mismatch)

Drives the FastAPI router in services/api/app/routers/sdk_auth.py
plus the helper in libs/sdk_auth/widget_token.py.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_API_ROOT = Path(__file__).resolve().parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

_HOST_SECRET = "test-host-shared-secret-please-rotate"
_TOKEN_SECRET = "test-widget-token-secret-please-rotate"


@pytest.fixture(autouse=True)
def _sdk_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDK_HOST_SHARED_SECRET", _HOST_SECRET)
    monkeypatch.setenv("SDK_WIDGET_TOKEN_SECRET", _TOKEN_SECRET)


@pytest.fixture
def client() -> TestClient:
    from app.routers.sdk_auth import router
    from app.services import host_governance

    host_governance._reset_for_testing()
    host_governance.register_host(
        host_id="HOST-TEST", name="Test Host", contact="ops@test.example"
    )
    for artefact in (
        "saas_embedding_agreement",
        "dpa",
        "dcb0129_reference",
    ):
        host_governance.mark_artefact_received(
            host_id="HOST-TEST",
            artefact=artefact,  # type: ignore[arg-type]
            evidence_uri=f"file://evidence/{artefact}.pdf",
        )
    host_governance.acknowledge_ifu(host_id="HOST-TEST", version="v1.0.0")
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _exchange_payload() -> dict:
    return {
        "host_id": "HOST-TEST",
        "host_user_id": "host-user-001",
        "tenant_id": "tenant-A",
        "assessment_id": "ASSESS-1",
        "user_role": "clinician",
    }


# ---------------------------------------------------------------------------
# VT-7EF430DD - POST /sdk/auth/exchange enforces server-to-server auth (AC3)
# ---------------------------------------------------------------------------


def test_exchange_rejects_missing_host_secret(client: TestClient) -> None:
    response = client.post("/sdk/auth/exchange", json=_exchange_payload())
    assert response.status_code == 401


def test_exchange_rejects_wrong_host_secret(client: TestClient) -> None:
    response = client.post(
        "/sdk/auth/exchange",
        json=_exchange_payload(),
        headers={"X-Mizaic-Host-Secret": "wrong-secret"},
    )
    assert response.status_code == 401


def test_exchange_rejects_browser_origin(client: TestClient) -> None:
    response = client.post(
        "/sdk/auth/exchange",
        json=_exchange_payload(),
        headers={
            "X-Mizaic-Host-Secret": _HOST_SECRET,
            "Origin": "https://host.example.com",
        },
    )
    assert response.status_code == 403


def test_exchange_returns_widget_jwt(client: TestClient) -> None:
    response = client.post(
        "/sdk/auth/exchange",
        json=_exchange_payload(),
        headers={"X-Mizaic-Host-Secret": _HOST_SECRET},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ttl_seconds"] == 900
    assert body["expires_at"] > int(time.time())

    from libs.sdk_auth import verify_widget_token

    claims = verify_widget_token(body["widget_token"])
    assert claims.assessment_id == "ASSESS-1"
    assert claims.tenant_id == "tenant-A"
    assert claims.user_role == "clinician"
    assert claims.exp - claims.iat == 900


# ---------------------------------------------------------------------------
# VT-8CADA244 - GET /sdk/sbar/{id} returns 403 on assessment-id mismatch (AC4)
# ---------------------------------------------------------------------------


def _mint_token_for(assessment_id: str) -> str:
    from libs.sdk_auth import mint_widget_token

    result = mint_widget_token(
        host_user_id="host-user-001",
        tenant_id="tenant-A",
        assessment_id=assessment_id,
        user_role="clinician",
    )
    return result.token


def test_sbar_returns_payload_on_matching_assessment(
    client: TestClient,
) -> None:
    token = _mint_token_for("ASSESS-1")
    response = client.get(
        "/sdk/sbar/ASSESS-1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["assessment_id"] == "ASSESS-1"
    assert body["tenant_id"] == "tenant-A"


def test_sbar_returns_403_on_assessment_mismatch(
    client: TestClient,
) -> None:
    token = _mint_token_for("ASSESS-1")
    response = client.get(
        "/sdk/sbar/ASSESS-2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_sbar_returns_401_when_no_authorization(client: TestClient) -> None:
    response = client.get("/sdk/sbar/ASSESS-1")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Token helper - belt-and-braces unit checks for the server-side primitives
# ---------------------------------------------------------------------------


def test_mint_widget_token_caps_ttl_at_900s() -> None:
    from libs.sdk_auth import mint_widget_token

    result = mint_widget_token(
        host_user_id="user",
        tenant_id="t",
        assessment_id="A1",
        user_role="clinician",
        ttl_seconds=4000,
    )
    assert result.ttl_seconds == 900


def test_verify_widget_token_rejects_missing_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from libs.sdk_auth import WidgetTokenError, verify_widget_token

    monkeypatch.delenv("SDK_WIDGET_TOKEN_SECRET", raising=False)
    with pytest.raises(WidgetTokenError):
        verify_widget_token("anything")
