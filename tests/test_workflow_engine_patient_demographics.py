"""Regression test for patient_age/patient_sex enrichment in WorkflowEngine.

Atlas trace:
  DI: DI-F22160C3 (guideline compliance evaluation)

Prior to this fix, WorkflowEngine.handle_event never populated
patient_age/patient_sex on pipeline_state, so every age/sex-gated NG12
guideline logic node in the compliance and terminology subgraphs silently
failed CLOSED for every real pipeline run -- regardless of the patient's
actual age or sex on the Patient node.
"""

from __future__ import annotations

import pytest

from libs.workflow.engine import (
    ActionDefinition,
    StepResult,
    WorkflowEngine,
    WorkflowEvent,
)


def _edge(source: str) -> list[dict[str, str]]:
    return [{"actionId": source, "relationship": "after-end"}]


def _trigger_plus_probe_actions() -> list[ActionDefinition]:
    return [
        ActionDefinition(
            action_id="start",
            subgraph_id="trigger",
            trigger_type="data-changed",
            trigger_name="encounter-created",
            node_type="trigger",
            sequence=0,
        ),
        ActionDefinition(
            action_id="probe",
            subgraph_id="compliance",
            trigger_type="",
            trigger_name="",
            related_edges=_edge("start"),
            sequence=1,
        ),
    ]


class _FakePatientGraphClient:
    def __init__(self, rows: list[dict[str, str]]):
        self._rows = rows
        self.closed = False

    def run(self, query: str, **params):
        return self._rows

    def close(self) -> None:
        self.closed = True


def _wire_common_mocks(
    engine: WorkflowEngine,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: _FakePatientGraphClient,
    captured_state: dict,
) -> None:
    async def _resolve_action_chain(_event: WorkflowEvent):
        return _trigger_plus_probe_actions()

    async def _noop_audit(*_args, **_kwargs):
        return None

    async def _execute_step(action: ActionDefinition, state: dict):
        captured_state.update(state)
        return StepResult(
            action_id=action.action_id,
            subgraph_id=action.subgraph_id,
            status="completed",
            output={},
        )

    monkeypatch.setattr(
        "libs.neo4j_client.client.PatientGraphClient", lambda: fake_client
    )
    monkeypatch.setattr(engine, "_resolve_action_chain", _resolve_action_chain)
    monkeypatch.setattr(engine, "_write_audit_event", _noop_audit)
    monkeypatch.setattr(engine, "_execute_step", _execute_step)


@pytest.mark.asyncio
async def test_handle_event_populates_patient_age_and_sex_from_patient_node(
    monkeypatch: pytest.MonkeyPatch,
):
    engine = WorkflowEngine()
    captured_state: dict = {}
    fake_client = _FakePatientGraphClient(
        [{"birth_date": "1945-06-06", "gender": "Male"}]
    )
    _wire_common_mocks(engine, monkeypatch, fake_client, captured_state)

    result = await engine.handle_event(
        WorkflowEvent(
            event_type="encounter-created",
            patient_id="scenario-sbar-upper_gi_form_001",
            encounter_id="e-1",
        )
    )

    assert result["status"] == "completed"
    assert captured_state.get("patient_age") is not None
    assert captured_state["patient_age"] > 60
    assert captured_state.get("patient_sex") == "male"
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_handle_event_leaves_demographics_unset_without_patient_node(
    monkeypatch: pytest.MonkeyPatch,
):
    engine = WorkflowEngine()
    captured_state: dict = {}
    fake_client = _FakePatientGraphClient([])
    _wire_common_mocks(engine, monkeypatch, fake_client, captured_state)

    result = await engine.handle_event(
        WorkflowEvent(
            event_type="encounter-created",
            patient_id="unknown-patient",
            encounter_id="e-1",
        )
    )

    assert result["status"] == "completed"
    assert "patient_age" not in captured_state
    assert "patient_sex" not in captured_state


@pytest.mark.asyncio
async def test_handle_event_respects_context_supplied_patient_age(
    monkeypatch: pytest.MonkeyPatch,
):
    """Quick-run / synthetic callers that pass patient_age explicitly win."""
    engine = WorkflowEngine()
    captured_state: dict = {}
    fake_client = _FakePatientGraphClient(
        [{"birth_date": "1945-06-06", "gender": "Male"}]
    )
    _wire_common_mocks(engine, monkeypatch, fake_client, captured_state)

    result = await engine.handle_event(
        WorkflowEvent(
            event_type="encounter-created",
            patient_id="scenario-sbar-upper_gi_form_001",
            encounter_id="e-1",
            context={"patient_age": 30.0},
        )
    )

    assert result["status"] == "completed"
    assert captured_state.get("patient_age") == 30.0
