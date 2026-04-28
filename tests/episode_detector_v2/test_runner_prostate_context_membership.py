"""Regression: context_milestone-only encounters stay in episode window (prostate).

Atlas trace:
  DI: DI-8A5FCF4F

Rulebook context patterns (e.g. pathology U&E request) emit
role=context_milestone only. The runner used to drop those encounter
ids from final membership because signal_encounter_ids excluded every
context_milestone; infer_contextual_encounter_ids only expands
breast/skin. Prostate admin/lab rows inside the referral window must
still link when they match the site's context catalogue.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from services.analysis_worker.app.episode_detector_v2 import runner as runner_mod
from services.analysis_worker.app.episode_detector_v2.runner import build_episodes


def _doc(
    *,
    concept_id: str,
    display_name: str,
    semantic_tag: str = "Procedure",
):
    return {
        "concept_id": concept_id,
        "display_name": display_name,
        "semantic_tag": semantic_tag,
        "assertion_json": json.dumps({"assertion": "present"}),
        "modifiers_json": "{}",
        "evidence_sentence": display_name,
        "value": None,
        "unit": None,
        "decision_tier": "high",
        "model_version": "v1",
    }


def _live_row(
    encounter_id: str,
    *,
    occurred_on: str,
    encounter_text: str = "",
    docs: list[dict[str, Any]] | None = None,
):
    return {
        "encounter_id": encounter_id,
        "occurred_on": occurred_on,
        "encounter_text": encounter_text,
        "raw_codes": docs or [],
    }


class _FakePatientClient:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def run(self, query: str, **kwargs):  # noqa: ARG002
        if "MATCH (p:Patient" in query and "HAS_ENCOUNTER" in query:
            return list(self._rows)
        return []

    def close(self):
        return None


@pytest.fixture
def v1_bundle():
    from scripts.episode_v2.dry_run_patient import _install_v1_bundle

    return _install_v1_bundle()


def test_prostate_episode_includes_context_only_lab_in_referral_window(v1_bundle):
    _ = v1_bundle
    rows = [
        _live_row(
            "pr-anchor",
            occurred_on="2025-08-01",
            docs=[
                _doc(
                    concept_id="276431000000102",
                    display_name="Fast track referral urological",
                )
            ],
        ),
        _live_row(
            "pr-lab-only",
            occurred_on="2025-08-04",
            encounter_text=(
                "Pathology Request (Request Sent): Urea & electrolytes (Requested) "
                "Reason for request: 2ww urology bloods"
            ),
            docs=[],
        ),
    ]
    original_replay = runner_mod.load_reviewed_episode_replay
    runner_mod.load_reviewed_episode_replay = lambda *a, **k: []
    try:
        result = asyncio.run(
            build_episodes(
                patient_id="9990001999",
                patient_client=_FakePatientClient(rows),
            )
        )
    finally:
        runner_mod.load_reviewed_episode_replay = original_replay

    prostate_eps = [
        ep
        for ep in result.resolved_episodes
        if ep.site_key == "prostate_urological"
    ]
    assert prostate_eps, result.resolved_episodes
    enc_ids = set(prostate_eps[0].encounter_ids)
    assert "pr-anchor" in enc_ids
    assert "pr-lab-only" in enc_ids
