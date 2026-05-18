"""Tests for the per-episode SBAR orchestrator.

Atlas trace:
  DI: DI-CC0BD732
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from services.pipeline_worker.app.services.episode_sbar_orchestrator import (
    EpisodeSBAROrchestrator,
    EpisodeSBARRequest,
)
from services.pipeline_worker.app.services.sbar_orchestrator import SBARResult


class FakeSBAROrchestrator:
    def __init__(self, *, assessment_md: str, recommendation_md: str):
        self._assessment = assessment_md
        self._recommendation = recommendation_md
        self.captured = None

    async def run(self, payload):
        self.captured = payload
        return SBARResult(
            assessment_id="asmt-1",
            status="completed",
            situation="Sit",
            background="Bg",
            assessment=self._assessment,
            recommendation=self._recommendation,
            content=f"# SBAR\n\n{self._assessment}\n\n{self._recommendation}",
            actions=[],
            rules=[],
            pathway_hints={},
            errors=[],
            errors_detail=[],
            notices=[],
            duration_s=0.1,
        )


class FakeSession:
    def __init__(self):
        self.runs: list[tuple[str, dict]] = []

    def run(self, query, **params):
        self.runs.append((query, params))
        result = MagicMock()
        result.single.return_value = None
        return result


class FakeClient:
    def __init__(self):
        self.session_inst = FakeSession()

    @contextmanager
    def session(self):
        yield self.session_inst


def test_episode_sbar_requires_at_least_one_encounter():
    orch = EpisodeSBAROrchestrator(
        sbar_orchestrator=FakeSBAROrchestrator(
            assessment_md="x", recommendation_md="y"
        ),
        patient_graph_client=FakeClient(),
    )
    with pytest.raises(ValueError):
        asyncio.run(
            orch.run(
                EpisodeSBARRequest(
                    run_id="r1",
                    patient_id="P1",
                    episode_id="ep-1",
                    encounter_ids=tuple(),
                    suspected_site="breast",
                )
            )
        )


def test_episode_sbar_payload_scoped_to_episode_encounters():
    inner = FakeSBAROrchestrator(assessment_md="x", recommendation_md="y")
    orch = EpisodeSBAROrchestrator(
        sbar_orchestrator=inner,
        patient_graph_client=FakeClient(),
    )
    asyncio.run(
        orch.run(
            EpisodeSBARRequest(
                run_id="r1",
                patient_id="P1",
                episode_id="ep-1",
                encounter_ids=("e-1", "e-2", "e-3"),
                suspected_site="breast",
            )
        )
    )
    assert inner.captured is not None
    assert len(inner.captured.background) == 3
    assert {b.id for b in inner.captured.background} == {"e-1", "e-2", "e-3"}
    assert inner.captured.extra["scope"] == "episode"
    assert inner.captured.extra["episode_id"] == "ep-1"


def test_episode_sbar_links_to_episode_and_persists_coherence():
    client = FakeClient()
    inner = FakeSBAROrchestrator(
        assessment_md="Confirmed breast cancer.",
        recommendation_md="Refer to oncology MDT.",
    )
    orch = EpisodeSBAROrchestrator(
        sbar_orchestrator=inner, patient_graph_client=client
    )
    result = asyncio.run(
        orch.run(
            EpisodeSBARRequest(
                run_id="r1",
                patient_id="P1",
                episode_id="ep-1",
                encounter_ids=("e-1",),
                suspected_site="breast",
                canonical_concept_id="254837009",
                canonical_display_name="Malignant tumor of breast",
            )
        )
    )
    queries = [q for q, _ in client.session_inst.runs]
    assert any("HAS_ASSESSMENT" in q for q in queries)
    assert any("coherence_flags" in q for q in queries)
    assert result.episode_id == "ep-1"
    assert result.coherence_flags == ()


def test_episode_sbar_records_coherence_when_assessment_contradicts_recommendation():
    client = FakeClient()
    inner = FakeSBAROrchestrator(
        assessment_md="No current evidence of malignancy.",
        recommendation_md="Initiate urgent two-week wait oncology referral.",
    )
    orch = EpisodeSBAROrchestrator(
        sbar_orchestrator=inner, patient_graph_client=client
    )
    result = asyncio.run(
        orch.run(
            EpisodeSBARRequest(
                run_id="r1",
                patient_id="P1",
                episode_id="ep-1",
                encounter_ids=("e-1",),
                suspected_site="breast",
                canonical_concept_id="254837009",
                canonical_display_name="Malignant tumor of breast",
            )
        )
    )
    codes = {f.code for f in result.coherence_flags}
    assert "narrative_contradiction" in codes
