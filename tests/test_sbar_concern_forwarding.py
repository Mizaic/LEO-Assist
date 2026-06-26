"""VT-LEO-AI-233 -- SBARRequestPayload.concern + orchestrator forwarding.

Verifies DI-LEO-AI-233 acceptance criteria:
  - SBARRequestPayload.concern enforces a 500-character cap.
  - The orchestrator forwards (payload.concern or '').strip() into
    extra_context['concern'] on the Situation stage caller.
  - Empty / whitespace-only concerns reach the caller as None
    (no meaningless prompt fragment).
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from libs.sbar.events import (
    BackgroundSourceType,
    SBARBackgroundSourceRef,
    SBARRequestPayload,
    SBARSituationInput,
)
from libs.sbar.source_resolver import ResolvedCode, ResolvedSource
from services.pipeline_worker.app.services.sbar_orchestrator import (
    SBAROrchestrator,
)


@dataclass
class _FakeSession:
    runs: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def run(self, query: str, **kwargs):
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

    def run(self, query: str, **kwargs):
        self._session.run(query, **kwargs)
        return []


def _payload(concern: str | None) -> SBARRequestPayload:
    return SBARRequestPayload(
        run_id="run-concern",
        situation=SBARSituationInput(patient_id="pat-1"),
        background=[
            SBARBackgroundSourceRef(
                type=BackgroundSourceType.encounter, id="enc-1"
            )
        ],
        concern=concern,
    )


def test_concern_field_rejects_strings_longer_than_500_chars() -> None:
    with pytest.raises(ValidationError):
        SBARRequestPayload(
            run_id="r",
            situation=SBARSituationInput(patient_id="p"),
            concern="x" * 501,
        )


def test_concern_field_accepts_500_chars() -> None:
    p = SBARRequestPayload(
        run_id="r",
        situation=SBARSituationInput(patient_id="p"),
        concern="x" * 500,
    )
    assert p.concern is not None
    assert len(p.concern) == 500


def _build_orchestrator(monkeypatch, situation_spy):
    session = _FakeSession()
    client = _FakeClient(session)

    async def _fake_background(*_a, **_kw):
        return {"markdown": "", "raw": {}, "error": None}

    async def _fake_recommendation(*_a, **_kw):
        return {
            "markdown": "",
            "actions": [],
            "raw": {},
            "error": None,
        }

    def _fake_evaluate(**_kw):
        return {"matched_rules": [], "active_version": "v1"}

    def _fake_resolve_situation(_s, _i):
        from libs.sbar.source_resolver import ResolvedSituation
        return ResolvedSituation(patient_id="pat-1", patient_summary={}, artifacts=[])

    def _fake_resolve_background(_s, _r):
        return [
            ResolvedSource(
                source_label="Encounter",
                source_id="enc-1",
                text="x",
                codes=[
                    ResolvedCode(
                        concept_id="1",
                        term="t",
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
    return SBAROrchestrator(
        patient_graph_client=client,
        publish_progress=publish,
        situation_caller=situation_spy,
        background_caller=_fake_background,
        recommendation_caller=_fake_recommendation,
        evaluator=_fake_evaluate,
    )


def test_orchestrator_forwards_concern_into_extra_context(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def _spy(_resolved, *, extra_context, patient_id):
        captured["extra_context"] = dict(extra_context)
        captured["patient_id"] = patient_id
        return {"markdown": "ok", "raw": {}, "error": None}

    orch = _build_orchestrator(monkeypatch, _spy)
    asyncio.run(orch.run(_payload("breathless and oxygen has dropped")))

    assert captured["extra_context"]["concern"] == (
        "breathless and oxygen has dropped"
    )


@pytest.mark.parametrize("concern", ["", "   "])
def test_orchestrator_passes_none_for_empty_or_whitespace_concern(
    monkeypatch, concern: str
) -> None:
    captured: dict[str, Any] = {}

    async def _spy(_resolved, *, extra_context, patient_id):
        captured["extra_context"] = dict(extra_context)
        return {"markdown": "ok", "raw": {}, "error": None}

    orch = _build_orchestrator(monkeypatch, _spy)
    asyncio.run(orch.run(_payload(concern or None)))

    assert captured["extra_context"]["concern"] is None
