from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from neo4j.time import DateTime

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

sys.modules.setdefault(
    "app.db.neo4j_client",
    MagicMock(PatientGraphClient=MagicMock),
)
sys.modules.setdefault(
    "app.services.session_store",
    MagicMock(COOKIE_NAME="leo_session", load_session=MagicMock()),
)

from app.deps import require_admin  # noqa: E402
from app.routers import sbar as sbar_module  # noqa: E402
from app.routers.sbar import router as sbar_router  # noqa: E402
from libs.auth.org_scope import CallerScope, get_caller_scope  # noqa: E402
from libs.message_bus.base import Message  # noqa: E402

ADMIN_SCOPE = CallerScope(
    email="admin@example.test",
    is_admin=True,
)


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(sbar_router)
    app.dependency_overrides[get_caller_scope] = lambda: ADMIN_SCOPE
    app.dependency_overrides[require_admin] = lambda: None
    return app


def test_scenario_run_enqueues_referral_messages(monkeypatch) -> None:
    fake_bus = AsyncMock()
    fake_bus.send = AsyncMock()
    fake_bus.close = AsyncMock()

    monkeypatch.setattr(sbar_module, "_ensure_scenario_run_schema", lambda: None)
    monkeypatch.setattr(
        sbar_module,
        "_load_scenarios",
        lambda case_ids: [
            {
                "case_id": case_ids[0],
                "markdown_body": "Referral text",
                "site": "upper_gi",
            }
        ],
    )
    monkeypatch.setattr(sbar_module, "_create_scenario_run", lambda **_: None)
    monkeypatch.setattr(
        sbar_module,
        "_scaffold_scenario_referrals",
        lambda *_a, **_k: {"upper_gi_letter_001": ["chunk-1"]},
    )
    monkeypatch.setattr(
        sbar_module, "_update_scenario_parent_status", lambda *_, **__: None
    )

    import libs.message_bus.factory as factory_module

    monkeypatch.setattr(factory_module, "create_message_bus", lambda: fake_bus)

    response = TestClient(_app()).post(
        "/sbar/scenario-runs",
        json={
            "case_ids": ["upper_gi_letter_001"],
            "guideline_id": "NG12",
            "completeness_domain": "cancer_referrals",
            "completeness_subdomain": "upper_gi",
        },
    )

    assert response.status_code == 200, response.text
    assert fake_bus.send.await_count == 1
    _, message = fake_bus.send.await_args.args
    assert isinstance(message, Message)
    assert message.body["event_type"] == "referral-received"
    assert message.body["plan_definition_id"] == "pd-referral-assessment"
    assert message.body["guideline_id"] == "NG12"
    assert message.body["chunk_ids"] == ["chunk-1"]
    assert message.body["source_node_type"] == "ReferralRequest"
    assert message.body["context"]["case_id"] == "upper_gi_letter_001"
    assert message.body["context"]["source"] == "ai_summarisation_scenario"


def test_scenario_run_detail_includes_child_stages(monkeypatch) -> None:
    monkeypatch.setattr(
        sbar_module,
        "_get_scenario_run_row",
        lambda run_id: {
            "run_id": run_id,
            "status": "completed",
            "case_ids_json": '["case-1"]',
            "child_runs_json": '{"case-1": "run-1:case-1"}',
            "guideline_id": "NG12",
            "completeness_domain": "cancer_referrals",
            "completeness_subdomain": "lower_gi",
        },
    )
    monkeypatch.setattr(
        sbar_module,
        "_load_child_pipeline_runs",
        lambda child_runs: [
            {
                "case_id": "case-1",
                "run_id": child_runs["case-1"],
                "status": "completed",
                "assessment_id": "assessment-1",
                "stages": [
                    {
                        "step_id": "durable-ref-sbar",
                        "event_type": "sbar_requested",
                        "status": "completed",
                        "errors": [],
                    }
                ],
            }
        ],
    )
    monkeypatch.setattr(
        sbar_module, "_update_scenario_parent_status", lambda *_, **__: None
    )

    response = TestClient(_app()).get("/sbar/scenario-runs/run-1")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["children"][0]["assessment_id"] == "assessment-1"
    assert payload["children"][0]["stages"][0]["event_type"] == "sbar_requested"


def test_scenario_run_detail_serializes_neo4j_datetime(monkeypatch) -> None:
    neo_dt = DateTime(2026, 5, 22, 13, 12, 0, 0)
    monkeypatch.setattr(
        sbar_module,
        "_get_scenario_run_row",
        lambda run_id: {
            "run_id": run_id,
            "status": "running",
            "case_ids_json": '["case-1"]',
            "child_runs_json": '{"case-1": "run-1:case-1"}',
            "guideline_id": "NG12",
            "completeness_domain": "cancer_referrals",
            "completeness_subdomain": "lower_gi",
            "triggered_at": neo_dt,
            "updated_at": neo_dt,
        },
    )
    monkeypatch.setattr(
        sbar_module,
        "_load_child_pipeline_runs",
        lambda _child_runs: [
            {
                "case_id": "case-1",
                "run_id": "run-1:case-1",
                "status": "running",
                "created_at": neo_dt,
                "stages": [{"event_type": "referral-received", "completed_at": neo_dt}],
            }
        ],
    )
    monkeypatch.setattr(
        sbar_module, "_update_scenario_parent_status", lambda *_, **__: None
    )

    response = TestClient(_app()).get("/sbar/scenario-runs/run-1")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["triggered_at"].startswith("2026-05-22T13:12:00")
    assert payload["children"][0]["created_at"].startswith("2026-05-22T13:12:00")
    assert payload["children"][0]["stages"][0]["completed_at"].startswith(
        "2026-05-22T13:12:00"
    )


def test_scenario_synthetic_patient_demographics_are_written(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_scaffold(**kwargs):
        calls.append(kwargs)
        return ["chunk-1"]

    monkeypatch.setattr(
        "libs.referral_simulator.scaffold.scaffold_referral",
        fake_scaffold,
    )

    chunk_ids = sbar_module._scaffold_scenario_referrals(
        "parent-1",
        [
            {
                "case_id": "upper_gi_form_001",
                "markdown_body": "Referral text",
                "synthetic_patient": {
                    "given_name": "Synthetic Given 005",
                    "family_name": "Synthetic Family 005",
                    "date_of_birth": "1945-06-06",
                    "gender": "Male",
                    "synthetic_nhs_number": "SYN-NHS-000005",
                },
            }
        ],
        {"upper_gi_form_001": "parent-1:upper_gi_form_001"},
    )

    assert chunk_ids == {"upper_gi_form_001": ["chunk-1"]}
    assert calls[0]["patient_name"] == "Synthetic Given 005 Synthetic Family 005"
    assert calls[0]["patient_sex"] == "Male"
    assert calls[0]["birth_date"] == "1945-06-06"
    assert calls[0]["nhs_number"] == "SYN-NHS-000005"
