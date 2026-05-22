"""Patient 9990001004 concurrent-pathway regression test.

Atlas trace:
  DI: DI-CC0BD732 (Per-episode SBAR with cross-section coherence)
  UN: UN-782EE657

This is the canonical regression case from the rebuild scope. The
patient has THREE concurrent episodes:

  - ep-breast-1    (confirmed breast cancer)
  - ep-ugi-1       (suspected upper GI malignancy, manual)
  - ep-lung-1      (suspected lung cancer, manually closed as benign)

Under the OLD patient-level SBAR, all three pathways were mashed into
one summary, producing a mixed Recommendation that lost the lung
benign-closure context entirely. Under the NEW per-episode SBAR, each
episode gets its OWN summary scoped to its OWN encounters, and the
patient-level rollup reasons across them.

This test asserts the structural property that delivers that:

1. The per-episode orchestrator does NOT see encounters from other
   episodes when invoked for a specific episode_id.
2. The rollup orchestrator sees ALL three per-episode summaries when
   invoked for the patient.
3. Coherence checks fire on the lung episode (negation in
   assessment, no urgent recommendation -> no flag) and breast
   episode (clean -> no flag) appropriately.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from unittest.mock import MagicMock

from services.pipeline_worker.app.services.episode_sbar_orchestrator import (
    EpisodeSBAROrchestrator,
    EpisodeSBARRequest,
)
from services.pipeline_worker.app.services.patient_rollup_sbar_orchestrator import (
    PatientRollupRequest,
    PatientRollupSBAROrchestrator,
    RollupResult,
)
from services.pipeline_worker.app.services.sbar_orchestrator import SBARResult


PATIENT_ID = "9990001004"

EPISODE_DEFINITIONS = {
    "ep-breast-1": {
        "site": "breast",
        "encounters": ("e-br-1", "e-br-2", "e-br-3"),
        "assessment": "Right breast lesion confirmed on mammography.",
        "recommendation": "Refer to breast oncology MDT.",
        "canonical_concept_id": "254837009",
        "canonical_display_name": "Malignant tumor of breast",
    },
    "ep-ugi-1": {
        "site": "upper_gi",
        "encounters": ("e-ugi-1", "e-ugi-2"),
        "assessment": "Epigastric pain, suspected upper GI malignancy.",
        "recommendation": "Refer to gastroenterology 2WW pathway.",
        "canonical_concept_id": None,
        "canonical_display_name": "",
    },
    "ep-lung-1": {
        "site": "lung",
        "encounters": ("e-lu-1",),
        "assessment": "No current evidence of lung malignancy following CT.",
        "recommendation": "Continue routine respiratory follow-up.",
        "canonical_concept_id": None,
        "canonical_display_name": "",
    },
}


class FakeSession:
    def __init__(self, episode_rows: list[dict] | None = None):
        self._episode_rows = episode_rows or []
        self.runs: list[tuple[str, dict]] = []

    def run(self, query, **params):
        self.runs.append((query, params))
        if "MATCH (p:Patient" in query and "assessment_scope = 'episode'" in query:
            return iter([dict(r) for r in self._episode_rows])
        result = MagicMock()
        result.single.return_value = None
        return result


class FakeClient:
    def __init__(self, episode_rows: list[dict] | None = None):
        self.session_inst = FakeSession(episode_rows)

    @contextmanager
    def session(self):
        yield self.session_inst

    def run(self, query, **params):
        return self.session_inst.run(query, **params)


class CapturingSBAR:
    def __init__(self, episode_id: str):
        self.captured = None
        self._episode_id = episode_id
        self._defn = EPISODE_DEFINITIONS[episode_id]

    async def run(self, payload):
        self.captured = payload
        return SBARResult(
            assessment_id=f"asmt-{self._episode_id}",
            status="completed",
            situation=self._defn["site"],
            background=", ".join(self._defn["encounters"]),
            assessment=self._defn["assessment"],
            recommendation=self._defn["recommendation"],
            content=(
                f"# SBAR\n\n{self._defn['assessment']}\n\n"
                f"{self._defn['recommendation']}"
            ),
            actions=[],
            rules=[],
            pathway_hints={},
            errors=[],
            errors_detail=[],
            notices=[],
            duration_s=0.0,
        )


def _run_one_episode(episode_id: str):
    defn = EPISODE_DEFINITIONS[episode_id]
    inner = CapturingSBAR(episode_id)
    orch = EpisodeSBAROrchestrator(
        sbar_orchestrator=inner, patient_graph_client=FakeClient()
    )
    result = asyncio.run(
        orch.run(
            EpisodeSBARRequest(
                run_id=f"r-{episode_id}",
                patient_id=PATIENT_ID,
                episode_id=episode_id,
                encounter_ids=defn["encounters"],
                suspected_site=defn["site"],
                canonical_concept_id=defn["canonical_concept_id"],
                canonical_display_name=defn["canonical_display_name"],
            )
        )
    )
    return inner, result


def test_each_episode_sbar_only_sees_its_own_encounters():
    inner_breast, _ = _run_one_episode("ep-breast-1")
    inner_ugi, _ = _run_one_episode("ep-ugi-1")
    inner_lung, _ = _run_one_episode("ep-lung-1")

    breast_ids = {b.id for b in inner_breast.captured.background}
    ugi_ids = {b.id for b in inner_ugi.captured.background}
    lung_ids = {b.id for b in inner_lung.captured.background}

    assert breast_ids == set(EPISODE_DEFINITIONS["ep-breast-1"]["encounters"])
    assert ugi_ids == set(EPISODE_DEFINITIONS["ep-ugi-1"]["encounters"])
    assert lung_ids == set(EPISODE_DEFINITIONS["ep-lung-1"]["encounters"])

    assert breast_ids.isdisjoint(ugi_ids)
    assert breast_ids.isdisjoint(lung_ids)
    assert ugi_ids.isdisjoint(lung_ids)


def test_breast_episode_coherence_clean_lung_episode_clean():
    _, breast = _run_one_episode("ep-breast-1")
    _, lung = _run_one_episode("ep-lung-1")

    assert breast.coherence_flags == ()
    assert lung.coherence_flags == ()


def test_lung_episode_with_inappropriate_2ww_recommendation_flags_contradiction():
    inner = CapturingSBAR("ep-lung-1")
    original_run = inner.run

    async def lung_with_bad_recommendation(payload):
        result = await original_run(payload)
        return SBARResult(
            assessment_id=result.assessment_id,
            status=result.status,
            situation=result.situation,
            background=result.background,
            assessment="No evidence of lung malignancy following CT.",
            recommendation="Initiate urgent two-week wait oncology referral.",
            content=result.content,
            actions=result.actions,
            rules=result.rules,
            pathway_hints=result.pathway_hints,
            errors=result.errors,
            errors_detail=result.errors_detail,
            notices=result.notices,
            duration_s=result.duration_s,
        )

    inner.run = lung_with_bad_recommendation  # type: ignore[assignment]
    orch = EpisodeSBAROrchestrator(
        sbar_orchestrator=inner, patient_graph_client=FakeClient()
    )
    result = asyncio.run(
        orch.run(
            EpisodeSBARRequest(
                run_id="r-lung",
                patient_id=PATIENT_ID,
                episode_id="ep-lung-1",
                encounter_ids=EPISODE_DEFINITIONS["ep-lung-1"]["encounters"],
                suspected_site="lung",
            )
        )
    )
    codes = {f.code for f in result.coherence_flags}
    assert "narrative_contradiction" in codes


def test_patient_rollup_sees_all_three_episode_summaries():
    rollup_rows = [
        {
            "assessment_id": f"asmt-{ep_id}",
            "episode_id": ep_id,
            "situation": defn["site"],
            "background": ", ".join(defn["encounters"]),
            "assessment": defn["assessment"],
            "recommendation": defn["recommendation"],
            "created_at": "2024-04-01",
        }
        for ep_id, defn in EPISODE_DEFINITIONS.items()
    ]

    captured: list[dict] = []

    async def capturing_caller(episodes):
        captured.extend(episodes)
        return RollupResult(
            markdown=(
                "## Rollup\n\n"
                "Three concurrent episodes: prioritise breast 2WW, "
                "follow up UGI 2WW, lung is benign-closed."
            ),
            actions=(),
        )

    client = FakeClient(episode_rows=rollup_rows)
    orch = PatientRollupSBAROrchestrator(
        patient_graph_client=client, rollup_caller=capturing_caller
    )
    result = asyncio.run(
        orch.run(PatientRollupRequest(run_id="r-rollup", patient_id=PATIENT_ID))
    )

    assert result.episode_count == 3
    seen_episode_ids = {e["episode_id"] for e in captured}
    assert seen_episode_ids == set(EPISODE_DEFINITIONS.keys())
    assert "rollup" in result.rollup_markdown.lower()
