"""DI-55CCC312: missing-FIT list endpoint is tenant-scoped."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from libs.auth.service_auth import verify_service_token
from services.terminology_api.app.routers.guidelines import router


def _client() -> TestClient:
    app = FastAPI()
    app.dependency_overrides[verify_service_token] = lambda: None
    app.include_router(router, prefix="/terminology")
    return TestClient(app)


def test_missing_fit_list_keeps_only_required_missing_for_tenant() -> None:
    client = _client()
    resp = client.post(
        "/terminology/guidelines/missing-fit-list",
        json={
            "organization_id": "org-1",
            "referrals": [
                {
                    "referral_id": "a",
                    "organization_id": "org-1",
                    "matched_rules": [
                        {
                            "investigation_policy": "required",
                            "investigation_status": "missing",
                        }
                    ],
                },
                {
                    "referral_id": "b",
                    "organization_id": "org-1",
                    "matched_rules": [
                        {
                            "investigation_policy": "required",
                            "investigation_status": "offered_or_resulted",
                        }
                    ],
                },
                {
                    "referral_id": "c",
                    "organization_id": "org-1",
                    "matched_rules": [
                        {
                            "investigation_policy": "not_required",
                            "investigation_status": "exempt",
                        }
                    ],
                },
                {
                    "referral_id": "other-org",
                    "organization_id": "org-2",
                    "matched_rules": [
                        {
                            "investigation_policy": "required",
                            "investigation_status": "missing",
                        }
                    ],
                },
            ],
        },
    )
    assert resp.status_code == 200
    ids = [r["referral_id"] for r in resp.json()["referrals"]]
    assert ids == ["a"]
