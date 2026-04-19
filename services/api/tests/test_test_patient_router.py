"""Router smoke tests for /guidance/test-patients -- VT-LEO-AI-165.

Verifies the FastAPI surface wires through to the service layer with the
correct request shape and status codes.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.test_patients import router


def _make_app() -> FastAPI:
    app = FastAPI()
    from app import deps
    from libs.auth.org_scope import CallerScope

    admin_scope = CallerScope(email="admin@test", is_admin=True)
    app.dependency_overrides[deps.require_admin] = lambda: admin_scope
    app.dependency_overrides[deps.require_admin_or_service] = lambda: admin_scope
    app.include_router(router)
    return app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(_make_app())


# -- dry-run ---------------------------------------------------------------


def test_dry_run_returns_evaluation(client: TestClient) -> None:
    payload = {
        "patient": {"codes": ["100"], "age": 70, "sex": "male"},
        "scope_type": "global",
        "scope_id": "default",
    }
    fake_result = {
        "matched_rules": [{"rule_id": "r1"}],
        "branch_paths": {"r1": ["c1"]},
        "ruleset_version": "v1",
    }
    with patch(
        "app.routers.test_patients.test_patient_service.dry_run",
        return_value=fake_result,
    ), patch("app.routers.test_patients._client", return_value=MagicMock()):
        resp = client.post("/guidance/test-patients/dry-run", json=payload)
    assert resp.status_code == 200
    assert resp.json() == fake_result


def test_dry_run_502_on_runtime_error(client: TestClient) -> None:
    payload = {"patient": {"codes": ["100"]}}
    with patch(
        "app.routers.test_patients.test_patient_service.dry_run",
        side_effect=RuntimeError("terminology offline"),
    ), patch("app.routers.test_patients._client", return_value=MagicMock()):
        resp = client.post("/guidance/test-patients/dry-run", json=payload)
    assert resp.status_code == 502
    assert "terminology offline" in resp.json()["detail"]


# -- save ------------------------------------------------------------------


def test_save_routes_through_to_service(client: TestClient) -> None:
    payload = {
        "patient": {"codes": ["100"], "age": 70, "sex": "male"},
        "guideline_id": "g1",
        "expectations": [
            {"rule_id": "r1", "fires": True, "matched_branch_node_ids": ["c1"]}
        ],
    }
    with patch(
        "app.routers.test_patients.test_patient_service.confirm_and_save",
        return_value={"id": "tp_new", "created": True, "expectations_written": 1},
    ), patch("app.routers.test_patients._client", return_value=MagicMock()):
        resp = client.post("/guidance/test-patients", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "tp_new"
    assert body["created"] is True


# -- update / PATCH --------------------------------------------------------


def test_update_routes_through_to_service(client: TestClient) -> None:
    payload = {
        "patient": {
            "codes": ["100", "200"],
            "age": 71,
            "sex": "female",
            "name": "Edited patient",
        },
        "expectations": [
            {"rule_id": "r1", "fires": False, "matched_branch_node_ids": []}
        ],
    }
    fake_service = MagicMock(
        return_value={
            "id": "tp_existing",
            "updated": True,
            "expectations_written": 1,
        }
    )
    with patch(
        "app.routers.test_patients.test_patient_service.update_patient",
        fake_service,
    ), patch("app.routers.test_patients._client", return_value=MagicMock()):
        resp = client.patch(
            "/guidance/test-patients/tp_existing", json=payload
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "id": "tp_existing",
        "updated": True,
        "expectations_written": 1,
    }
    # Service was called with the parsed payload + id from the URL.
    kwargs = fake_service.call_args.kwargs
    assert kwargs["patient_id"] == "tp_existing"
    assert kwargs["expectations"] == [
        {"rule_id": "r1", "fires": False, "matched_branch_node_ids": []}
    ]
    assert kwargs["payload"].codes == ["100", "200"]
    assert kwargs["payload"].name == "Edited patient"


def test_update_404_when_patient_missing(client: TestClient) -> None:
    payload = {
        "patient": {"codes": ["100"]},
        "expectations": [],
    }
    with patch(
        "app.routers.test_patients.test_patient_service.update_patient",
        return_value={
            "id": "tp_missing",
            "updated": False,
            "expectations_written": 0,
        },
    ), patch("app.routers.test_patients._client", return_value=MagicMock()):
        resp = client.patch(
            "/guidance/test-patients/tp_missing", json=payload
        )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_update_accepts_empty_expectations(client: TestClient) -> None:
    """Editing a patient down to zero assertions is permitted -- the
    UI surfaces this as 'no assertions' instead of silently passing."""
    payload = {
        "patient": {"codes": ["100"], "age": 70, "sex": "male"},
        "expectations": [],
    }
    fake_service = MagicMock(
        return_value={
            "id": "tp1",
            "updated": True,
            "expectations_written": 0,
        }
    )
    with patch(
        "app.routers.test_patients.test_patient_service.update_patient",
        fake_service,
    ), patch("app.routers.test_patients._client", return_value=MagicMock()):
        resp = client.patch("/guidance/test-patients/tp1", json=payload)
    assert resp.status_code == 200
    assert resp.json()["expectations_written"] == 0
    assert fake_service.call_args.kwargs["expectations"] == []


# -- delete + 404 ----------------------------------------------------------


def test_delete_404_when_missing(client: TestClient) -> None:
    with patch(
        "app.routers.test_patients.test_patient_service.delete_patient",
        return_value=0,
    ), patch("app.routers.test_patients._client", return_value=MagicMock()):
        resp = client.delete("/guidance/test-patients/tp_missing")
    assert resp.status_code == 404


def test_delete_returns_count(client: TestClient) -> None:
    with patch(
        "app.routers.test_patients.test_patient_service.delete_patient",
        return_value=1,
    ), patch("app.routers.test_patients._client", return_value=MagicMock()):
        resp = client.delete("/guidance/test-patients/tp1")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 1, "patient_id": "tp1"}


# -- replay ----------------------------------------------------------------


def test_replay_returns_report(client: TestClient) -> None:
    fake_report = {
        "id": "rv_1",
        "ruleset_version": "v1",
        "passes_count": 3,
        "regressions_count": 0,
        "drift_count": 0,
        "patient_count": 3,
        "results": [],
    }
    with patch(
        "app.routers.test_patients.test_patient_service.replay_scope",
        return_value=fake_report,
    ), patch("app.routers.test_patients._client", return_value=MagicMock()):
        resp = client.post(
            "/guidance/test-patients/replay", json={"guideline_id": "g1"}
        )
    assert resp.status_code == 200
    assert resp.json()["regressions_count"] == 0


# -- generate --------------------------------------------------------------


def test_generate_returns_proposals(client: TestClient) -> None:
    fake_proposals = {
        "proposals": [
            {
                "patient": {"codes": ["100"], "age": 70, "sex": "male"},
                "rule_id": "r1",
                "rule_name": "Rule 1",
                "guideline_id": "g1",
                "kind": "happy",
                "rationale": "...",
                "content_hash": "abc",
            }
        ],
        "scope_type": "rule",
        "depth": "minimal_pair",
        "rules_considered": 1,
    }
    with patch(
        "app.routers.test_patients.test_patient_generator.generate",
        return_value=fake_proposals,
    ), patch("app.routers.test_patients._client", return_value=MagicMock()):
        resp = client.post(
            "/guidance/test-patients/generate",
            json={
                "scope_type": "rule",
                "rule_id": "r1",
                "depth": "minimal_pair",
            },
        )
    assert resp.status_code == 200
    assert len(resp.json()["proposals"]) == 1


# -- replay reports --------------------------------------------------------


def test_replay_report_404(client: TestClient) -> None:
    with patch(
        "app.routers.test_patients.test_patient_service.get_replay_report",
        return_value=None,
    ), patch("app.routers.test_patients._client", return_value=MagicMock()):
        resp = client.get("/guidance/test-patients/replay-reports/rv_missing")
    assert resp.status_code == 404
