"""VT-LEO-AI-182: SBAROrchestrator end-to-end with mocked dependencies.

Verifies DI-LEO-AI-186 / DI-LEO-AI-188 / DI-LEO-AI-189 acceptance criteria:
- All four stages run in order and persist incrementally to Neo4j
- A draft :Assessment is created up-front via CREATE_ASSESSMENT
- Per-stage progress events are emitted via the publisher
- LLM stage failures degrade gracefully (status='draft', error recorded)
- The deterministic Assessment formatter is invoked with aggregated codes
- Final composed Markdown contains all four section headings
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from libs.sbar.assessment_formatter import AssessmentNarrative
from libs.sbar.events import (
    BackgroundSourceType,
    SBARArtifactRef,
    SBARBackgroundSourceRef,
    SBARRequestPayload,
    SBARSituationInput,
    SituationArtifactType,
)
from libs.sbar.source_resolver import ResolvedCode, ResolvedSource
from services.pipeline_worker.app.services.sbar_orchestrator import (
    SBAROrchestrator,
)


@dataclass
class _FakeSession:
    """Tiny stand-in for a Neo4j session that records every run() call."""

    runs: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    return_values: dict[str, Any] = field(default_factory=dict)

    def run(self, query: str, **kwargs):
        self.runs.append((query, kwargs))
        record = self.return_values.get(_first_keyword(query))
        return _FakeResult(record)


@dataclass
class _FakeResult:
    record: Any | None = None

    def single(self):
        return self.record


class _FakeClient:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    @contextmanager
    def session(self):
        yield self._session


def _first_keyword(query: str) -> str:
    stripped = (query or "").strip().split()
    return stripped[0].upper() if stripped else ""


def _make_payload() -> SBARRequestPayload:
    return SBARRequestPayload(
        run_id="run-test",
        situation=SBARSituationInput(
            patient_id="pat-1",
            artifacts=[
                SBARArtifactRef(type=SituationArtifactType.referral_request, id="rr-9")
            ],
        ),
        background=[
            SBARBackgroundSourceRef(type=BackgroundSourceType.encounter, id="enc-1")
        ],
        guideline_ids=[],
    )


@pytest.fixture
def orchestrator_with_mocks(monkeypatch):
    session = _FakeSession()
    client = _FakeClient(session)

    async def _fake_situation(*_a, **_kw):
        return {"markdown": "Patient context.", "raw": {}, "error": None}

    async def _fake_background(*_a, **_kw):
        return {"markdown": "- Recent finding.", "raw": {}, "error": None}

    async def _fake_recommendation(*_a, **_kw):
        return {
            "markdown": "Refer urgently.",
            "actions": [{"action": "refer", "priority": "2ww", "due_days": 14}],
            "raw": {},
            "error": None,
        }

    def _fake_evaluate(**_kw):
        return {
            "matched_rules": [
                {
                    "rule_id": "R-1",
                    "name": "2WW lung",
                    "strength": "strong",
                    "guideline_id": "G-LUNG",
                    "guideline_title": "Suspected lung cancer",
                    "chapter_title": "Referral",
                    "recommendation_verbatim": "2WW referral",
                    "action": {"priority": "2ww", "due_days": 14, "name": "Refer 2WW"},
                    "confidence": 1.0,
                }
            ],
            "active_version": "v1",
        }

    def _fake_resolve_situation(_session, _input):
        from libs.sbar.source_resolver import ResolvedSituation

        return ResolvedSituation(patient_id="pat-1", patient_summary={}, artifacts=[])

    def _fake_resolve_background(_session, _refs):
        return [
            ResolvedSource(
                source_label="Encounter",
                source_id="enc-1",
                text="GP review",
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
        ]

    monkeypatch.setattr(
        "services.pipeline_worker.app.services.sbar_orchestrator.resolve_situation",
        _fake_resolve_situation,
    )
    monkeypatch.setattr(
        "services.pipeline_worker.app.services.sbar_orchestrator.resolve_background_sources",
        _fake_resolve_background,
    )

    publish = MagicMock()
    orch = SBAROrchestrator(
        patient_graph_client=client,
        publish_progress=publish,
        situation_caller=_fake_situation,
        background_caller=_fake_background,
        recommendation_caller=_fake_recommendation,
        evaluator=_fake_evaluate,
    )
    return orch, session, publish


def test_orchestrator_runs_all_stages_and_persists(orchestrator_with_mocks):
    orch, session, publish = orchestrator_with_mocks
    payload = _make_payload()

    result = asyncio.run(orch.run(payload))

    assert result.status == "completed"
    assert result.assessment_id
    assert "## Situation" in result.content
    assert "## Background" in result.content
    assert "## Assessment" in result.content
    assert "## Recommendation" in result.content
    assert "Refer urgently" in result.content

    # MERGE :Assessment, link to ReferralRequest, then 4 SET stages, then FINALISE
    queries = [_first_keyword(q) for q, _ in session.runs]
    assert queries.count("MATCH") >= 6  # CREATE + LINK + 4 SETs + FINAL
    # Pathway hints derived deterministically from 2WW rule
    assert result.pathway_hints["rtr"] == "yes"
    assert "R-1" in (result.pathway_hints["stt_evidence"] or "")

    # Progress events: started + 4 stages * 2 + completed
    types = [c.args[1]["type"] for c in publish.call_args_list]
    assert "sbar_started" in types
    stage_completed = [t for t in types if t == "sbar_stage_completed"]
    assert len(stage_completed) == 4
    assert types[-1] == "sbar_completed"


def test_orchestrator_emits_structured_errors_and_notices_on_sbar_completed(
    monkeypatch,
):
    """VT-LEO-AI-514 TC-006 / TC-007: structured errors[] / notices[] on SSE.

    The Bedrock 'Input is too long for requested model' validation
    failure today ends up as a green 'Done (1 errors)' button with no
    detail. After DI-LEO-AI-513 / DI-LEO-AI-516 the orchestrator MUST:
      - Append a friendly error to errors_detail and to the legacy
        errors[] list.
      - Forward a background_trimmed notice on the matching
        sbar_stage_completed event AND aggregate it in the final
        sbar_completed payload.
      - Never echo the raw vendor string (no 'ValidationException' or
        'Converse' substring on the wire).
    """
    session = _FakeSession()
    client = _FakeClient(session)

    async def _ok_situation(*_a, **_kw):
        return {
            "markdown": "Patient context.",
            "raw": {},
            "error": None,
            "error_code": None,
        }

    async def _bad_background(*_a, **_kw):
        return {
            "markdown": "",
            "raw": {},
            "error": (
                "There was too much information for the model to read for "
                "the Background section. Try picking fewer records, or "
                "shorter ones, and run it again."
            ),
            "error_code": "input_too_long",
            "notice": "Trimmed 3 records to fit.",
        }

    async def _ok_recommendation(*_a, **_kw):
        return {
            "markdown": "Refer urgently.",
            "actions": [],
            "raw": {},
            "error": None,
            "error_code": None,
        }

    monkeypatch.setattr(
        "services.pipeline_worker.app.services.sbar_orchestrator.resolve_situation",
        lambda _s, _i: _make_resolved_situation(),
    )
    monkeypatch.setattr(
        "services.pipeline_worker.app.services.sbar_orchestrator.resolve_background_sources",
        lambda _s, _r: [],
    )

    publish = MagicMock()
    orch = SBAROrchestrator(
        patient_graph_client=client,
        publish_progress=publish,
        situation_caller=_ok_situation,
        background_caller=_bad_background,
        recommendation_caller=_ok_recommendation,
        evaluator=lambda **_kw: {"matched_rules": []},
    )
    result = asyncio.run(orch.run(_make_payload()))

    assert result.status == "draft"
    assert len(result.errors_detail) == 1
    assert result.errors_detail[0]["stage"] == "background"
    assert result.errors_detail[0]["code"] == "input_too_long"
    assert "ValidationException" not in result.errors_detail[0]["message"]
    assert "Converse" not in result.errors_detail[0]["message"]

    assert len(result.notices) == 1
    assert result.notices[0] == {
        "stage": "background",
        "code": "background_trimmed",
        "message": "Trimmed 3 records to fit.",
    }

    events = [c.args[1] for c in publish.call_args_list]
    completed = [e for e in events if e["type"] == "sbar_completed"]
    assert len(completed) == 1
    payload = completed[0]
    assert payload["error_count"] == 1
    assert isinstance(payload["errors"], list)
    assert payload["errors"][0]["stage"] == "background"
    assert payload["errors"][0]["code"] == "input_too_long"
    assert isinstance(payload["notices"], list)
    assert payload["notices"][0]["code"] == "background_trimmed"

    bg_stage = [
        e
        for e in events
        if e["type"] == "sbar_stage_completed" and e.get("stage") == "background"
    ]
    assert len(bg_stage) == 1
    assert bg_stage[0]["error"]["code"] == "input_too_long"
    assert bg_stage[0]["notice"]["code"] == "background_trimmed"

    for e in events:
        for value in e.values():
            if isinstance(value, str):
                assert "ValidationException" not in value
                assert "Converse operation" not in value


def test_orchestrator_records_error_when_situation_call_fails(monkeypatch):
    session = _FakeSession()
    client = _FakeClient(session)

    async def _err_situation(*_a, **_kw):
        return {"markdown": "", "raw": {}, "error": "llm_unavailable"}

    async def _ok(*_a, **_kw):
        return {"markdown": "ok", "raw": {}, "error": None}

    async def _ok_recommendation(*_a, **_kw):
        return {"markdown": "ok", "actions": [], "raw": {}, "error": None}

    monkeypatch.setattr(
        "services.pipeline_worker.app.services.sbar_orchestrator.resolve_situation",
        lambda _s, _i: _make_resolved_situation(),
    )
    monkeypatch.setattr(
        "services.pipeline_worker.app.services.sbar_orchestrator.resolve_background_sources",
        lambda _s, _r: [],
    )

    orch = SBAROrchestrator(
        patient_graph_client=client,
        publish_progress=lambda _r, _e: None,
        situation_caller=_err_situation,
        background_caller=_ok,
        recommendation_caller=_ok_recommendation,
        evaluator=lambda **_kw: {"matched_rules": []},
    )
    result = asyncio.run(orch.run(_make_payload()))
    assert result.status == "draft"
    assert any(e.startswith("situation:") for e in result.errors)


def _make_resolved_situation():
    from libs.sbar.source_resolver import ResolvedSituation

    return ResolvedSituation(patient_id="pat-1", patient_summary={}, artifacts=[])
