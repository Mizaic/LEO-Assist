"""Orchestrator-level regression test for the DOB-as-citation bug found on
referral 000049823847: the model was given the patient's birth_date (to
state age) and cited it verbatim as an inline evidence date for an
unrelated clause, leaking a direct patient identifier into the Situation
narrative.

Verifies SBAROrchestrator.run() applies libs.sbar.pii_guard.strip_dob_citations
to the Situation, Background, and Recommendation markdown before persisting,
and records a guard event in ``errors`` when a DOB citation was stripped.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

from libs.sbar.events import (
    BackgroundSourceType,
    SBARBackgroundSourceRef,
    SBARRequestPayload,
    SBARSituationInput,
)
from libs.sbar.source_resolver import ResolvedCode, ResolvedSituation, ResolvedSource
from services.pipeline_worker.app.services.sbar_orchestrator import SBAROrchestrator

_PATIENT_DOB = "1955-04-09"
_LEAKED_SITUATION_MD = (
    "This 71-year-old woman needs referral assessment now for an urgent "
    "cancer pathway, but the request conflicts between 2WW and the "
    "Serious Non-Specific Symptoms pathway [1955-04-09]. The headline "
    "trigger is concern for cancer [Document date not stated]."
)


@dataclass
class _FakeSession:
    runs: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def run(self, query: str, **kwargs):
        self.runs.append((query, kwargs))
        return _FakeResult()


class _FakeResult:
    def single(self):
        return {"id": "found"}


class _FakeClient:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    @contextmanager
    def session(self):
        yield self._session

    def run(self, query: str, **kwargs):
        self._session.run(query, **kwargs)
        return []


def _payload() -> SBARRequestPayload:
    return SBARRequestPayload(
        run_id="run-dob-guard",
        situation=SBARSituationInput(patient_id="pat-1"),
        background=[
            SBARBackgroundSourceRef(type=BackgroundSourceType.encounter, id="enc-1")
        ],
    )


def _build_orchestrator(monkeypatch, *, situation_markdown: str):
    session = _FakeSession()
    client = _FakeClient(session)

    async def _situation_caller(_resolved, **_kwargs):
        return {"markdown": situation_markdown, "raw": {}, "error": None}

    async def _background_caller(*_a, **_kw):
        return {"markdown": "", "raw": {}, "error": None}

    async def _recommendation_caller(*_a, **_kw):
        return {"markdown": "", "actions": [], "raw": {}, "error": None}

    async def _evaluator(**_kw):
        return {"matched_rules": [], "active_version": "v1"}

    def _fake_resolve_situation(_s, _i):
        return ResolvedSituation(
            patient_id="pat-1",
            patient_summary={"birth_date": _PATIENT_DOB, "gender": "female"},
            artifacts=[],
        )

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

    orch = SBAROrchestrator(
        patient_graph_client=client,
        publish_progress=MagicMock(),
        situation_caller=_situation_caller,
        background_caller=_background_caller,
        recommendation_caller=_recommendation_caller,
        evaluator=_evaluator,
    )
    return orch, session


def test_orchestrator_strips_dob_citation_before_persisting_situation(monkeypatch):
    orch, session = _build_orchestrator(
        monkeypatch, situation_markdown=_LEAKED_SITUATION_MD
    )

    result = asyncio.run(orch.run(_payload()))

    # Persisted (via Cypher) and returned situation text must both be clean.
    persisted_kwargs = next(
        kwargs for _q, kwargs in session.runs if kwargs.get("situation") is not None
    )
    assert _PATIENT_DOB not in persisted_kwargs["situation"]
    assert _PATIENT_DOB not in result.situation
    assert "pii_guard_stripped_dob_citation" in " ".join(result.errors)


def test_orchestrator_leaves_genuine_dates_untouched(monkeypatch):
    clean_md = "This 71-year-old woman is referred for a 2WW pathway. [2026-03-19]"
    orch, session = _build_orchestrator(monkeypatch, situation_markdown=clean_md)

    result = asyncio.run(orch.run(_payload()))

    persisted_kwargs = next(
        kwargs for _q, kwargs in session.runs if kwargs.get("situation") is not None
    )
    assert persisted_kwargs["situation"] == clean_md
    assert result.situation == clean_md
    assert "pii_guard_stripped_dob_citation" not in " ".join(result.errors)
