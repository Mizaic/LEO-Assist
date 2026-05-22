"""LEO widget SDK auth verification tests.

Atlas trace:
  DI: DI-A1206416, DI-AF2C3996
  DO: DO-5C88CA8F, DO-6D21096F
  VTs:
    - VT-7EF430DD (token-mint endpoint enforces server-to-server)
    - VT-8CADA244 (proxy returns 403 on assessment-id mismatch)
    - VT-5E57AAE4 (proxy returns combined SBAR + guideline + completeness payload)
    - VT-80BC0C00 (proxy returns 404 for unknown assessment)

Drives the FastAPI router in services/api/app/routers/sdk_auth.py
plus the helper in libs/sdk_auth/widget_token.py.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_API_ROOT = Path(__file__).resolve().parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

_HOST_SECRET = "test-host-shared-secret-please-rotate"
_TOKEN_SECRET = "test-widget-token-secret-please-rotate"

_SAMPLE_RULES = json.dumps(
    [
        {
            "rule_id": "rule:NG12:v1:CH002:SEC000:R004:abc123",
            "name": "1.1.5 Offer an urgent chest X-ray within 2 weeks",
            "strength": "offer",
            "guideline_id": "NG12",
            "recommendation_verbatim": (
                "Offer an urgent chest X-ray (to be done within 2 weeks) "
                "to assess for mesothelioma in people aged 40 and over."
            ),
        }
    ]
)

_SAMPLE_RECORD: dict[str, Any] = {
    "id": "ASSESS-1",
    "type": "SBAR",
    "status": "completed",
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-01T10:05:00Z",
    "run_id": "run-001",
    "requested_by": "user-001",
    "tenant_id": "tenant-A",
    "guideline_ids": ["NG12"],
    "patient_id": "patient-001",
    "situation": "55-year-old with cough.",
    "background": "No prior investigations.",
    "background_parts": [],
    "assessment": "NG12 rule fired.",
    "assessment_codes": [],
    "assessment_rules": _SAMPLE_RULES,
    "recommendation": "Chest X-ray within 2 weeks.",
    "recommendation_actions": [],
    "content": "## situation\nCough.\n\n## recommendation\nChest X-ray.\n",
    "stt": None,
    "stt_evidence": None,
    "alternative_pathway": None,
    "alternative_pathway_evidence": None,
    "rtr": None,
    "rtr_evidence": None,
    "errors": [],
}


@pytest.fixture(autouse=True)
def _sdk_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDK_HOST_SHARED_SECRET", _HOST_SECRET)
    monkeypatch.setenv("SDK_WIDGET_TOKEN_SECRET", _TOKEN_SECRET)


@pytest.fixture(autouse=True)
def _mock_neo4j(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the Neo4j query function so tests run without a live database.

    Individual tests that want to exercise 404 or different data can
    monkeypatch again inside the test body.
    """
    import app.routers.sdk_auth as sdk_auth_module

    monkeypatch.setattr(
        sdk_auth_module,
        "_query_assessment_from_neo4j",
        lambda assessment_id: (
            _SAMPLE_RECORD.copy() if assessment_id == "ASSESS-1" else None
        ),
    )


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


# ---------------------------------------------------------------------------
# VT-5E57AAE4 - GET /sdk/sbar/{id} returns combined SBAR + guideline payload
# ---------------------------------------------------------------------------


def test_sbar_returns_real_assessment(client: TestClient) -> None:
    """Proxy returns markdown, guideline matches, and null completeness."""
    token = _mint_token_for("ASSESS-1")
    response = client.get(
        "/sdk/sbar/ASSESS-1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["assessment_id"] == "ASSESS-1"
    assert body["tenant_id"] == "tenant-A"
    assert "situation" in body["markdown"].lower() or body["markdown"] != ""
    assert body["completeness_findings"] is None


def test_sbar_returns_guideline_verbatim(client: TestClient) -> None:
    """Proxy decodes assessment_rules and includes recommendation_verbatim."""
    token = _mint_token_for("ASSESS-1")
    response = client.get(
        "/sdk/sbar/ASSESS-1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    matches = body["guideline_matches"]
    assert len(matches) == 1
    match = matches[0]
    assert match["rule_id"] == "rule:NG12:v1:CH002:SEC000:R004:abc123"
    assert match["guideline_id"] == "NG12"
    assert "mesothelioma" in match["recommendation_verbatim"]


def test_sbar_returns_completeness_findings_when_persisted(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proxy converts stored completeness_result_json to widget contract."""
    import app.routers.sdk_auth as sdk_auth_module

    completeness_json = json.dumps(
        {
            "configured": True,
            "complete": False,
            "domain": "cancer_referrals",
            "subdomain": "lower_gi",
            "matched_groups": [
                {"name": "Diagnosis", "required": True, "matched": True},
            ],
            "missing_groups": [
                {"name": "Urgency", "required": True, "matched": False},
                {"name": "GP name", "required": False, "matched": False},
            ],
            "concept_ids": [12345],
        }
    )
    record_with_completeness = {**_SAMPLE_RECORD, "completeness_result_json": completeness_json}
    monkeypatch.setattr(
        sdk_auth_module,
        "_query_assessment_from_neo4j",
        lambda _id: record_with_completeness,
    )

    token = _mint_token_for("ASSESS-1")
    response = client.get(
        "/sdk/sbar/ASSESS-1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    cf = body["completeness_findings"]
    assert cf is not None
    assert cf["requiredFields"] == ["Diagnosis", "Urgency"]
    assert cf["presentFields"] == ["Diagnosis"]
    assert cf["missingFields"] == ["Urgency"]
    assert cf["unclearFields"] == ["GP name"]


# ---------------------------------------------------------------------------
# VT-80BC0C00 - GET /sdk/sbar/{id} returns 404 for unknown assessment
# ---------------------------------------------------------------------------


def test_sbar_returns_404_for_missing_assessment(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proxy returns 404 when no Assessment node exists in Neo4j."""
    import app.routers.sdk_auth as sdk_auth_module

    monkeypatch.setattr(
        sdk_auth_module,
        "_query_assessment_from_neo4j",
        lambda _id: None,
    )
    token = _mint_token_for("ASSESS-MISSING")
    response = client.get(
        "/sdk/sbar/ASSESS-MISSING",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_exchange_rejects_host_not_onboarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exchange returns 403 host_not_onboarded for un-registered hosts."""
    from app.routers.sdk_auth import router
    from app.services import host_governance

    host_governance._reset_for_testing()
    app = FastAPI()
    app.include_router(router)
    tc = TestClient(app)

    response = tc.post(
        "/sdk/auth/exchange",
        json={
            "host_id": "HOST-UNKNOWN",
            "host_user_id": "u1",
            "tenant_id": "t1",
            "assessment_id": "A1",
            "user_role": "clinician",
        },
        headers={"X-Mizaic-Host-Secret": _HOST_SECRET},
    )
    assert response.status_code == 403
    assert "host_not_onboarded" in response.json()["detail"]
