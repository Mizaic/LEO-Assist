"""Happy/unhappy tests for scenario-run enqueue via referral simulator (Slice B)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

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
from libs.referral_simulator.ids import (  # noqa: E402
    document_reference_id,
    encounter_id_for_referral,
    referral_id_for_child_run,
    scenario_patient_id,
)
from libs.referral_simulator.scaffold import SOURCE_SCENARIO  # noqa: E402

ADMIN_SCOPE = CallerScope(email="admin@example.test", is_admin=True)


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(sbar_router)
    app.dependency_overrides[get_caller_scope] = lambda: ADMIN_SCOPE
    app.dependency_overrides[require_admin] = lambda: None
    return app


def _case(case_id: str = "upper_gi_jaundice_001", **extra: object) -> dict:
    base = {
        "case_id": case_id,
        "markdown_body": "Clinical letter paragraph one.\n\nParagraph two.",
        "site": "upper_gi",
        "synthetic_patient": {
            "given_name": "Ada",
            "family_name": "Lovelace",
            "gender": "female",
            "date_of_birth": "1980-01-01",
            "synthetic_nhs_number": "9990001111",
        },
    }
    base.update(extra)
    return base


def test_enqueue_happy_scaffolds_and_publishes_chunk_shaped_message(monkeypatch):
    fake_bus = AsyncMock()
    fake_bus.send = AsyncMock()
    fake_bus.close = AsyncMock()
    scaffold_calls: list[dict] = []

    def fake_scaffold(**kwargs):
        scaffold_calls.append(kwargs)
        return ["chunk-a", "chunk-b"]

    monkeypatch.setattr(sbar_module, "_ensure_scenario_run_schema", lambda: None)
    monkeypatch.setattr(sbar_module, "_load_scenarios", lambda ids: [_case(ids[0])])
    monkeypatch.setattr(sbar_module, "_create_scenario_run", lambda **_: None)
    monkeypatch.setattr(
        sbar_module, "_update_scenario_parent_status", lambda *_, **__: None
    )
    monkeypatch.setattr(
        "libs.referral_simulator.scaffold.scaffold_referral",
        fake_scaffold,
    )

    import libs.message_bus.factory as factory_module

    monkeypatch.setattr(factory_module, "create_message_bus", lambda: fake_bus)

    response = TestClient(_app()).post(
        "/sbar/scenario-runs",
        json={
            "case_ids": ["upper_gi_jaundice_001"],
            "guideline_id": "NG12",
            "completeness_domain": "cancer_referrals",
            "completeness_subdomain": "upper_gi",
        },
    )

    assert response.status_code == 200, response.text
    assert len(scaffold_calls) == 1
    sc = scaffold_calls[0]
    assert sc["text"] == "Clinical letter paragraph one.\n\nParagraph two."
    assert sc["source"] == SOURCE_SCENARIO
    assert sc["patient_id"] == scenario_patient_id("upper_gi_jaundice_001")
    assert sc["patient_sex"] == "female"
    assert "Ada" in sc["patient_name"]
    assert sc["encounter_id"] == encounter_id_for_referral(
        referral_id_for_child_run(
            response.json()["child_runs"]["upper_gi_jaundice_001"]
        )
    )

    assert fake_bus.send.await_count == 1
    _, message = fake_bus.send.await_args.args
    assert isinstance(message, Message)
    body = message.body
    child_run_id = response.json()["child_runs"]["upper_gi_jaundice_001"]
    referral = referral_id_for_child_run(child_run_id)

    assert body["event_type"] == "referral-received"
    assert body["referral_id"] == referral
    assert body["document_reference_id"] == document_reference_id(referral)
    assert body["chunk_ids"] == ["chunk-a", "chunk-b"]
    assert body["text_segmentation_mode"] == "document_chunks"
    assert body["source_node_type"] == "ReferralRequest"
    assert body["source_node_id"] == referral
    assert body["encounter_id"] == encounter_id_for_referral(referral)
    assert body["patient_id"] == scenario_patient_id("upper_gi_jaundice_001")
    assert body["guideline_id"] == "NG12"
    assert body["completeness_domain"] == "cancer_referrals"
    assert body["completeness_subdomain"] == "upper_gi"
    assert body["context"]["source"] == SOURCE_SCENARIO
    assert body["context"]["case_id"] == "upper_gi_jaundice_001"
    assert body["context"]["parent_run_id"] == response.json()["run_id"]
    assert body["source_node_type"] != "Encounter"
    assert body.get("source_text_property") in (None, "")


def test_enqueue_unhappy_unknown_case_no_scaffold_no_bus(monkeypatch):
    fake_bus = AsyncMock()
    fake_bus.send = AsyncMock()
    scaffold = MagicMock(return_value=["c1"])

    monkeypatch.setattr(sbar_module, "_ensure_scenario_run_schema", lambda: None)
    monkeypatch.setattr(sbar_module, "_load_scenarios", lambda _ids: [])
    monkeypatch.setattr(
        "libs.referral_simulator.scaffold.scaffold_referral",
        scaffold,
    )

    import libs.message_bus.factory as factory_module

    monkeypatch.setattr(factory_module, "create_message_bus", lambda: fake_bus)

    response = TestClient(_app()).post(
        "/sbar/scenario-runs",
        json={"case_ids": ["missing_case"]},
    )

    assert response.status_code == 404
    scaffold.assert_not_called()
    fake_bus.send.assert_not_awaited()


def test_enqueue_unhappy_missing_markdown_no_publish(monkeypatch):
    fake_bus = AsyncMock()
    fake_bus.send = AsyncMock()
    scaffold = MagicMock(return_value=["c1"])

    monkeypatch.setattr(sbar_module, "_ensure_scenario_run_schema", lambda: None)
    monkeypatch.setattr(
        sbar_module,
        "_load_scenarios",
        lambda ids: [_case(ids[0], markdown_body="")],
    )
    monkeypatch.setattr(sbar_module, "_create_scenario_run", lambda **_: None)
    monkeypatch.setattr(
        "libs.referral_simulator.scaffold.scaffold_referral",
        scaffold,
    )

    import libs.message_bus.factory as factory_module

    monkeypatch.setattr(factory_module, "create_message_bus", lambda: fake_bus)

    response = TestClient(_app()).post(
        "/sbar/scenario-runs",
        json={"case_ids": ["empty_md_001"]},
    )

    assert response.status_code == 422
    scaffold.assert_not_called()
    fake_bus.send.assert_not_awaited()


def test_enqueue_unhappy_scaffold_failure_surfaces_error(monkeypatch):
    created: list[str] = []
    fake_bus = AsyncMock()
    fake_bus.send = AsyncMock()

    def boom(**_kwargs):
        raise RuntimeError("neo4j down")

    monkeypatch.setattr(sbar_module, "_ensure_scenario_run_schema", lambda: None)
    monkeypatch.setattr(sbar_module, "_load_scenarios", lambda ids: [_case(ids[0])])
    monkeypatch.setattr(
        sbar_module,
        "_create_scenario_run",
        lambda **kwargs: created.append(kwargs["run_id"]),
    )
    monkeypatch.setattr(
        "libs.referral_simulator.scaffold.scaffold_referral",
        boom,
    )

    import libs.message_bus.factory as factory_module

    monkeypatch.setattr(factory_module, "create_message_bus", lambda: fake_bus)

    response = TestClient(_app()).post(
        "/sbar/scenario-runs",
        json={"case_ids": ["upper_gi_jaundice_001"]},
    )

    assert response.status_code == 500
    assert created == []  # create after successful scaffold
    fake_bus.send.assert_not_awaited()
