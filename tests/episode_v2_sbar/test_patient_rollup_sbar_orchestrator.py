"""Tests for the patient-level rollup SBAR orchestrator.

Atlas trace:
  DI: DI-CC0BD732
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from unittest.mock import MagicMock

from services.pipeline_worker.app.services.patient_rollup_sbar_orchestrator import (
    PatientRollupRequest,
    PatientRollupSBAROrchestrator,
    RollupResult,
)


class FakeSession:
    def __init__(self, episode_rows: list[dict]):
        self._episode_rows = episode_rows
        self.runs: list[tuple[str, dict]] = []

    def run(self, query, **params):
        self.runs.append((query, params))
        if "LIST" in query or "assessment_scope" in query and "MATCH (p:Patient" in query:
            return iter([dict(r) for r in self._episode_rows])
        result = MagicMock()
        result.single.return_value = None
        return result


class FakeClient:
    def __init__(self, episode_rows: list[dict]):
        self.session_inst = FakeSession(episode_rows)

    @contextmanager
    def session(self):
        yield self.session_inst


async def _capturing_caller(episodes):
    _capturing_caller.captured = list(episodes)
    return RollupResult(
        markdown="## Rollup\n\nReview oncology MDT timing across episodes.",
        actions=(
            {
                "action": "Confirm 2WW booked",
                "priority": "2ww",
                "due_days": 14,
                "rationale": "Outstanding from breast episode",
                "episode_ids": ["ep-breast-1"],
            },
        ),
    )


def test_rollup_with_no_episodes_returns_default_message():
    client = FakeClient(episode_rows=[])
    orch = PatientRollupSBAROrchestrator(patient_graph_client=client)
    result = asyncio.run(
        orch.run(PatientRollupRequest(run_id="r1", patient_id="P1"))
    )
    assert result.episode_count == 0
    assert "no active episodes" in result.rollup_markdown.lower()


def test_rollup_calls_caller_with_loaded_episodes():
    rows = [
        {
            "assessment_id": "asmt-breast",
            "episode_id": "ep-breast-1",
            "situation": "Right breast lesion.",
            "background": "Mammography 2024-03.",
            "assessment": "Confirmed breast cancer.",
            "recommendation": "Oncology MDT referral.",
            "created_at": "2024-04-01",
        },
        {
            "assessment_id": "asmt-ugi",
            "episode_id": "ep-ugi-1",
            "situation": "Epigastric pain.",
            "background": "OGD pending.",
            "assessment": "UGI investigation in progress.",
            "recommendation": "Gastroenterology follow-up.",
            "created_at": "2024-04-02",
        },
    ]
    client = FakeClient(episode_rows=rows)
    orch = PatientRollupSBAROrchestrator(
        patient_graph_client=client, rollup_caller=_capturing_caller
    )
    result = asyncio.run(
        orch.run(PatientRollupRequest(run_id="r1", patient_id="P1"))
    )
    assert result.episode_count == 2
    assert "rollup" in result.rollup_markdown.lower()
    assert len(result.actions) == 1
    captured = _capturing_caller.captured
    assert {e["episode_id"] for e in captured} == {"ep-breast-1", "ep-ugi-1"}


def test_rollup_persists_assessment_with_scope_rollup():
    rows = [
        {
            "assessment_id": "asmt-breast",
            "episode_id": "ep-breast-1",
            "situation": "S",
            "background": "B",
            "assessment": "A",
            "recommendation": "R",
            "created_at": "2024-04-01",
        }
    ]
    client = FakeClient(episode_rows=rows)
    orch = PatientRollupSBAROrchestrator(
        patient_graph_client=client, rollup_caller=_capturing_caller
    )
    asyncio.run(orch.run(PatientRollupRequest(run_id="r1", patient_id="P1")))
    queries = [q for q, _ in client.session_inst.runs]
    assert any("assessment_scope = 'rollup'" in q for q in queries)
    assert any("FINALISE_ASSESSMENT" in q or "a.content" in q for q in queries)
