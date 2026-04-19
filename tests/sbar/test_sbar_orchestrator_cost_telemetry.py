"""VT-LEO-AI-508 TC-005/TC-006/TC-007: SBAR orchestrator persists LLM
usage onto the :Assessment node and writes a PipelineRun :AuditEvent
with non-zero token counts. Telemetry write failures must NOT fail
the run.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest

from libs.cypher.sbar_assessment_queries import (
    SET_ASSESSMENT_USAGE,
    WRITE_SBAR_AUDIT_EVENT,
)
from libs.llm_client import token_tracker
from libs.llm_client.usage_recorder import (
    LLMCallRecord,
    _default_tracking_callback,
    get_active_recorder,
)
from libs.sbar.events import (
    BackgroundSourceType,
    SBARArtifactRef,
    SBARBackgroundSourceRef,
    SBARRequestPayload,
    SBARSituationInput,
    SituationArtifactType,
)
from libs.sbar.source_resolver import (
    ResolvedCode,
    ResolvedSituation,
    ResolvedSource,
)
from services.pipeline_worker.app.services.sbar_orchestrator import (
    SBAROrchestrator,
)


@pytest.fixture(autouse=True)
def _restore_default_callback():
    previous = token_tracker._tracking_callback
    token_tracker.set_tracking_callback(_default_tracking_callback)
    yield
    token_tracker.set_tracking_callback(previous)


@dataclass
class _FakeSession:
    runs: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    fail_on: set[str] = field(default_factory=set)

    def run(self, query: str, **kwargs):
        if query in self.fail_on:
            raise RuntimeError("simulated-neo4j-failure")
        self.runs.append((query, kwargs))
        return _FakeResult()


class _FakeResult:
    def single(self):
        return None


class _FakeClient:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    @contextmanager
    def session(self):
        yield self._session


def _make_payload() -> SBARRequestPayload:
    return SBARRequestPayload(
        run_id="run-vt-508",
        situation=SBARSituationInput(
            patient_id="pat-vt508",
            artifacts=[
                SBARArtifactRef(type=SituationArtifactType.referral_request, id="rr-1")
            ],
        ),
        background=[
            SBARBackgroundSourceRef(type=BackgroundSourceType.encounter, id="enc-1")
        ],
        guideline_ids=[],
        encounter_id="enc-1",
    )


def _record_into_active(agent_task: str, in_tok: int, out_tok: int) -> None:
    """Helper: simulate what invoke_llm_json does on the recorder."""
    rec = get_active_recorder()
    assert rec is not None, "expected an active LLMUsageRecorder"
    rec.record(
        LLMCallRecord(
            agent_task=agent_task,
            model_name="claude-sonnet-4-5",
            model_provider="bedrock",
            input_tokens=in_tok,
            output_tokens=out_tok,
            cached_input_tokens=0,
            latency_ms=42,
            success=True,
            patient_id="pat-vt508",
        )
    )


def _build_orchestrator(monkeypatch, session, *, telemetry_failure=False):
    async def _situation_caller(*_a, **_kw):
        _record_into_active("sbar_situation", 200, 50)
        return {"markdown": "Patient context.", "raw": {}, "error": None}

    async def _background_caller(*_a, **_kw):
        _record_into_active("sbar_background", 400, 80)
        return {"markdown": "- Recent finding.", "raw": {}, "error": None}

    async def _recommendation_caller(*_a, **_kw):
        _record_into_active("sbar_recommendation", 150, 30)
        return {
            "markdown": "Refer urgently.",
            "actions": [],
            "raw": {},
            "error": None,
        }

    def _evaluate(**_kw):
        return {"matched_rules": [], "active_version": "v1"}

    monkeypatch.setattr(
        "services.pipeline_worker.app.services.sbar_orchestrator.resolve_situation",
        lambda _s, _i: ResolvedSituation(
            patient_id="pat-vt508", patient_summary={}, artifacts=[]
        ),
    )
    monkeypatch.setattr(
        "services.pipeline_worker.app.services.sbar_orchestrator.resolve_background_sources",
        lambda _s, _r: [
            ResolvedSource(
                source_label="Encounter",
                source_id="enc-1",
                text="text",
                codes=[
                    ResolvedCode(
                        concept_id="123",
                        term="Cough",
                        assertion="present",
                        source_label="Encounter",
                        source_id="enc-1",
                    )
                ],
            )
        ],
    )

    if telemetry_failure:
        session.fail_on.add(SET_ASSESSMENT_USAGE)
        session.fail_on.add(WRITE_SBAR_AUDIT_EVENT)

    return SBAROrchestrator(
        patient_graph_client=_FakeClient(session),
        publish_progress=lambda _r, _e: None,
        situation_caller=_situation_caller,
        background_caller=_background_caller,
        recommendation_caller=_recommendation_caller,
        evaluator=_evaluate,
    )


def test_orchestrator_sets_assessment_llm_usage_json(monkeypatch):
    session = _FakeSession()
    orch = _build_orchestrator(monkeypatch, session)

    result = asyncio.run(orch.run(_make_payload()))

    assert result.status == "completed"
    matches = [kw for q, kw in session.runs if q == SET_ASSESSMENT_USAGE]
    assert len(matches) == 1, f"expected one usage write, got {len(matches)}"
    payload = matches[0]
    assert payload["llm_input_tokens"] == 200 + 400 + 150
    assert payload["llm_output_tokens"] == 50 + 80 + 30
    assert payload["llm_calls"] == 3
    assert payload["llm_cost_usd"] > 0
    parsed = json.loads(payload["llm_usage_json"])
    assert parsed["input_tokens"] == payload["llm_input_tokens"]
    assert parsed["output_tokens"] == payload["llm_output_tokens"]
    assert abs(parsed["cost_usd"] - payload["llm_cost_usd"]) < 1e-6


def test_orchestrator_writes_pipeline_run_audit_event(monkeypatch):
    session = _FakeSession()
    orch = _build_orchestrator(monkeypatch, session)

    result = asyncio.run(orch.run(_make_payload()))

    assert result.status == "completed"
    audits = [kw for q, kw in session.runs if q == WRITE_SBAR_AUDIT_EVENT]
    assert len(audits) == 1
    audit = audits[0]
    assert audit["id"] == "audit-run-vt-508"
    assert audit["patient_id"] == "pat-vt508"
    assert audit["encounter_id"] == "enc-1"
    assert audit["llm_input_tokens"] == 200 + 400 + 150
    assert audit["llm_output_tokens"] == 50 + 80 + 30
    assert audit["llm_cost_usd"] > 0
    assert audit["status"] == "completed"
    assert audit["extraction_provider"] == "bedrock"
    assert audit["extraction_prompt_name"] == "sbar"


def test_orchestrator_swallows_telemetry_write_failure(monkeypatch, caplog):
    session = _FakeSession()
    orch = _build_orchestrator(monkeypatch, session, telemetry_failure=True)

    result = asyncio.run(orch.run(_make_payload()))

    assert result.status == "completed"
    assert any(
        "SBAR usage telemetry" in record.message for record in caplog.records
    ), "expected a WARNING log when telemetry write fails"
    assert not any(q == WRITE_SBAR_AUDIT_EVENT for q, _ in session.runs)
    assert not any(q == SET_ASSESSMENT_USAGE for q, _ in session.runs)
