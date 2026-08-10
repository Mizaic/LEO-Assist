"""Tests for SBAR task context integrity preflight (R-0E8A90ED)."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

from libs.sbar.context_integrity import validate_sbar_context
from libs.sbar.events import (
    BackgroundSourceType,
    SBARArtifactRef,
    SBARBackgroundSourceRef,
    SBARRequestPayload,
    SBARSituationInput,
    SituationArtifactType,
)
from services.pipeline_worker.app.services.sbar_orchestrator import SBAROrchestrator


@dataclass
class _FakeResult:
    record: Any | None = None

    def single(self):
        return self.record


@dataclass
class _FakeSession:
    responses: list[Any | None] = field(default_factory=list)
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    _index: int = 0

    def run(self, query: str, **kwargs):
        self.calls.append((query, kwargs))
        record = None
        if self._index < len(self.responses):
            record = self.responses[self._index]
        self._index += 1
        return _FakeResult(record)


class _FakeClient:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session
        self.run_calls: list[tuple[str, dict[str, Any]]] = []

    @contextmanager
    def session(self):
        yield self._session

    def run(self, query: str, **kwargs):
        self.run_calls.append((query, kwargs))
        return []


def _payload(**overrides: Any) -> SBARRequestPayload:
    base = SBARRequestPayload(
        run_id="run-1",
        situation=SBARSituationInput(
            patient_id="pat-1",
            artifacts=[
                SBARArtifactRef(type=SituationArtifactType.referral_request, id="rr-1")
            ],
        ),
        background=[
            SBARBackgroundSourceRef(type=BackgroundSourceType.encounter, id="enc-1")
        ],
        encounter_id="enc-1",
    )
    return base.model_copy(update=overrides)


def test_validate_rejects_missing_patient() -> None:
    session = _FakeSession(responses=[None])
    result = validate_sbar_context(session, _payload())
    assert result.ok is False
    assert result.errors[0].code == "patient_not_found"


def test_validate_rejects_encounter_not_connected_to_patient() -> None:
    session = _FakeSession(
        responses=[
            {"id": "pat-1"},
            None,
            None,
            None,
            None,
        ]
    )
    result = validate_sbar_context(session, _payload())
    assert result.ok is False
    codes = {err.code for err in result.errors}
    assert "encounter_patient_mismatch" in codes


def test_validate_passes_when_all_records_connected() -> None:
    session = _FakeSession(
        responses=[
            {"id": "pat-1"},
            {"id": "enc-1"},
            {"id": "rr-1"},
            {"id": "enc-1"},
        ]
    )
    result = validate_sbar_context(session, _payload())
    assert result.ok is True
    assert result.errors == []


def test_validate_accepts_referral_assessment_correlation_encounter() -> None:
    session = _FakeSession(
        responses=[
            {"id": "pat-1"},
            {"id": "000049823847"},
            {"id": "000049823847"},
            {"id": "rr-1"},
            {"id": "000049823847"},
        ]
    )
    payload = _payload(
        encounter_id="000049823847:referral-assessment",
        situation=SBARSituationInput(
            patient_id="pat-1",
            artifacts=[
                SBARArtifactRef(
                    type=SituationArtifactType.encounter,
                    id="000049823847:referral-assessment",
                ),
                SBARArtifactRef(
                    type=SituationArtifactType.referral_request,
                    id="000049823847",
                ),
            ],
        ),
        background=[
            SBARBackgroundSourceRef(
                type=BackgroundSourceType.encounter,
                id="000049823847:referral-assessment",
            )
        ],
    )
    result = validate_sbar_context(session, payload)
    assert result.ok is True


def test_orchestrator_stops_before_llm_on_integrity_failure() -> None:
    session = _FakeSession(responses=[None])
    client = _FakeClient(session)
    situation = MagicMock()
    background = MagicMock()
    published: list[tuple[str, dict[str, Any]]] = []

    def _capture(run_id: str, body: dict[str, Any]) -> None:
        published.append((run_id, body))

    orch = SBAROrchestrator(
        patient_graph_client=client,
        publish_progress=_capture,
        situation_caller=situation,
        background_caller=background,
    )

    result = asyncio.run(orch.run(_payload()))

    assert result.status == "error"
    situation.assert_not_called()
    background.assert_not_called()
    assert any(body.get("type") == "sbar_failed" for _, body in published)
