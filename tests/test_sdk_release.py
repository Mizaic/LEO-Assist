"""LEO widget release-channel verification tests.

Atlas trace:
  DI: DI-3C06AFD0
  DO: DO-3B62F38E
  VT: VT-FFFE45AD (release endpoints served from Mizaic-controlled origin)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_API_ROOT = Path(__file__).resolve().parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))


@pytest.fixture
def client() -> TestClient:
    from app.routers.sdk_release import (
        _reset_release_state_for_testing,
        router,
    )

    _reset_release_state_for_testing()
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _max_age(header_value: str | None) -> int:
    assert header_value, "missing Cache-Control header"
    match = re.search(r"max-age=(\d+)", header_value)
    assert match, f"unexpected Cache-Control: {header_value}"
    return int(match.group(1))


def test_manifest_endpoint_returns_active_and_major(client: TestClient) -> None:
    response = client.get("/v1/manifest.json")
    assert response.status_code == 200
    body = response.json()
    assert "active" in body
    assert "major" in body
    assert isinstance(body["major"], int)
    assert isinstance(body["active"], str) and len(body["active"]) > 0


def test_manifest_cache_control_under_60s(client: TestClient) -> None:
    response = client.get("/v1/manifest.json")
    max_age = _max_age(response.headers.get("Cache-Control"))
    assert max_age <= 60


def test_advisory_endpoint_returns_active_flag(client: TestClient) -> None:
    response = client.get("/v1/advisory.json")
    assert response.status_code == 200
    body = response.json()
    assert "active" in body
    assert isinstance(body["active"], bool)


def test_advisory_active_payload_carries_headline_and_body(
    client: TestClient,
) -> None:
    from app.routers.sdk_release import _set_advisory_for_testing

    _set_advisory_for_testing(
        active=True,
        severity="safety",
        headline="Withhold autosubmit",
        body="Pending CSO review.",
        published_at="2026-04-20T10:00:00Z",
    )
    response = client.get("/v1/advisory.json")
    body = response.json()
    assert body["active"] is True
    assert body["headline"] == "Withhold autosubmit"
    assert body["body"]


def test_advisory_cache_control_under_60s(client: TestClient) -> None:
    response = client.get("/v1/advisory.json")
    max_age = _max_age(response.headers.get("Cache-Control"))
    assert max_age <= 60


def test_cso_rollback_visible_via_manifest(client: TestClient) -> None:
    from app.routers.sdk_release import _set_manifest_for_testing

    response_a = client.get("/v1/manifest.json")
    assert response_a.json()["active"] == "1.0.0"
    _set_manifest_for_testing(1, "0.9.5")
    response_b = client.get("/v1/manifest.json")
    assert response_b.json()["active"] == "0.9.5"
