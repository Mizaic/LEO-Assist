"""LEO widget host governance verification tests.

Atlas trace:
  DI: DI-2FBDAC7D
  DO: DO-5A298ABC
  VTs:
    - VT-E2AED8E8 - host onboarding requires four artefacts
    - VT-3D434ACC - IFU document is versioned and acknowledgement records version
    - VT-71530F5D - token issuance refuses non-onboarded host
    - VT-1A2A16AD - GET /sdk/governance/register returns all hosts
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
_API_ROOT = REPO_ROOT / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

_HOST_SECRET = "test-host-shared-secret-please-rotate"
_TOKEN_SECRET = "test-widget-token-secret-please-rotate"
IFU_PATH = REPO_ROOT / "compliance" / "policy" / "leo-widget-ifu.md"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDK_HOST_SHARED_SECRET", _HOST_SECRET)
    monkeypatch.setenv("SDK_WIDGET_TOKEN_SECRET", _TOKEN_SECRET)
    from app.services import host_governance

    host_governance._reset_for_testing()


@pytest.fixture
def client() -> TestClient:
    from app.routers.sdk_auth import router as sdk_auth_router
    from app.routers.sdk_governance import router as sdk_governance_router

    app = FastAPI()
    app.include_router(sdk_auth_router)
    app.include_router(sdk_governance_router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# VT-E2AED8E8 - host onboarding requires four artefacts
# ---------------------------------------------------------------------------


def test_newly_registered_host_is_not_production_ready() -> None:
    from app.services import host_governance

    host_governance.register_host(
        "HOST-A", "Acme Health", "ops@acme.example"
    )
    assert host_governance.is_production_ready("HOST-A") is False


def test_partial_artefacts_do_not_satisfy_production_gate() -> None:
    from app.services import host_governance

    host_governance.register_host("HOST-A", "Acme", "ops@acme")
    host_governance.mark_artefact_received(
        "HOST-A", "saas_embedding_agreement", "file://saas.pdf"
    )
    assert host_governance.is_production_ready("HOST-A") is False
    host_governance.mark_artefact_received("HOST-A", "dpa", "file://dpa.pdf")
    assert host_governance.is_production_ready("HOST-A") is False
    host_governance.mark_artefact_received(
        "HOST-A", "dcb0129_reference", "uri://dcb0129/leo-2026"
    )
    assert host_governance.is_production_ready("HOST-A") is False


def test_all_four_artefacts_satisfy_production_gate() -> None:
    from app.services import host_governance

    host_governance.register_host("HOST-A", "Acme", "ops@acme")
    for artefact, evidence in (
        ("saas_embedding_agreement", "file://saas.pdf"),
        ("dpa", "file://dpa.pdf"),
        ("dcb0129_reference", "uri://dcb0129/leo-2026"),
    ):
        host_governance.mark_artefact_received("HOST-A", artefact, evidence)
    host_governance.acknowledge_ifu("HOST-A", "v1.0.0")
    assert host_governance.is_production_ready("HOST-A") is True


def test_unknown_host_raises_for_artefact_marking() -> None:
    from app.services import host_governance

    with pytest.raises(host_governance.HostNotRegisteredError):
        host_governance.mark_artefact_received(
            "HOST-UNKNOWN", "dpa", "file://x.pdf"
        )


# ---------------------------------------------------------------------------
# VT-3D434ACC - IFU is versioned and acknowledgement records version
# ---------------------------------------------------------------------------


def test_ifu_document_exists_and_is_versioned() -> None:
    assert IFU_PATH.exists(), "IFU document is missing"
    text = IFU_PATH.read_text()
    assert re.search(r"Version:\s*v\d+\.\d+\.\d+", text), text[:200]


def test_ifu_lists_required_host_obligations() -> None:
    text = IFU_PATH.read_text()
    for token in (
        "DCB0160",
        "Content Security Policy",
        "telemetry",
        "advisory",
        "error",
    ):
        assert token in text, f"missing: {token}"


def test_acknowledge_ifu_stores_version() -> None:
    from app.services import host_governance

    host_governance.register_host("HOST-A", "Acme", "ops@acme")
    host_governance.acknowledge_ifu("HOST-A", "v1.0.0")
    record = host_governance.get_host("HOST-A")
    assert record is not None
    assert record.acknowledged_ifu_version == "v1.0.0"


# ---------------------------------------------------------------------------
# VT-71530F5D - token issuance refuses non-onboarded host
# ---------------------------------------------------------------------------


def _exchange_payload(host_id: str = "HOST-A") -> dict:
    return {
        "host_id": host_id,
        "host_user_id": "host-user-001",
        "tenant_id": "tenant-A",
        "assessment_id": "ASSESS-1",
        "user_role": "clinician",
    }


def test_exchange_blocked_for_unknown_host(client: TestClient) -> None:
    response = client.post(
        "/sdk/auth/exchange",
        json=_exchange_payload("HOST-UNKNOWN"),
        headers={"X-Mizaic-Host-Secret": _HOST_SECRET},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "host_not_onboarded"


def test_exchange_blocked_for_partially_onboarded_host(
    client: TestClient,
) -> None:
    from app.services import host_governance

    host_governance.register_host("HOST-A", "Acme", "ops@acme")
    host_governance.mark_artefact_received(
        "HOST-A", "saas_embedding_agreement", "file://saas.pdf"
    )
    response = client.post(
        "/sdk/auth/exchange",
        json=_exchange_payload(),
        headers={"X-Mizaic-Host-Secret": _HOST_SECRET},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "host_not_onboarded"


def test_exchange_blocked_until_host_onboarded(client: TestClient) -> None:
    response_a = client.post(
        "/sdk/governance/hosts",
        json={"host_id": "HOST-A", "name": "Acme", "contact": "ops@acme"},
    )
    assert response_a.status_code == 200

    for artefact in (
        "saas_embedding_agreement",
        "dpa",
        "dcb0129_reference",
    ):
        client.post(
            f"/sdk/governance/hosts/HOST-A/artefacts",
            json={"artefact": artefact, "evidence_uri": f"file://{artefact}.pdf"},
        )
    client.post(
        "/sdk/governance/hosts/HOST-A/ifu",
        json={"version": "v1.0.0"},
    )

    response = client.post(
        "/sdk/auth/exchange",
        json=_exchange_payload(),
        headers={"X-Mizaic-Host-Secret": _HOST_SECRET},
    )
    assert response.status_code == 200, response.text
    assert response.json()["ttl_seconds"] == 900


# ---------------------------------------------------------------------------
# VT-1A2A16AD - GET /sdk/governance/register returns all hosts
# ---------------------------------------------------------------------------


def test_register_endpoint_returns_all_hosts(client: TestClient) -> None:
    client.post(
        "/sdk/governance/hosts",
        json={"host_id": "HOST-A", "name": "Acme", "contact": "a@a"},
    )
    client.post(
        "/sdk/governance/hosts",
        json={"host_id": "HOST-B", "name": "Beta", "contact": "b@b"},
    )
    client.post(
        "/sdk/governance/hosts/HOST-A/ifu", json={"version": "v1.0.0"}
    )

    response = client.get("/sdk/governance/register")
    assert response.status_code == 200
    body = response.json()
    by_id = {entry["host_id"]: entry for entry in body}
    assert set(by_id.keys()) == {"HOST-A", "HOST-B"}
    for record in body:
        assert "artefacts" in record
        assert set(record["artefacts"].keys()) == {
            "saas_embedding_agreement",
            "dpa",
            "dcb0129_reference",
            "ifu_acknowledged",
        }
        assert "is_production_ready" in record
        assert "acknowledged_ifu_version" in record
    assert by_id["HOST-A"]["acknowledged_ifu_version"] == "v1.0.0"
    assert by_id["HOST-A"]["is_production_ready"] is False
