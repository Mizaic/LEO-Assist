"""Frozen-cohort regression VT for the Haiku episode engine (VT-LEO-AI-507).

Re-runs the engine in dry_run on the 20 canonical patients from
``scripts/regression/episode_engine_frozen/cohort_ids.FROZEN_COHORT`` and
asserts that each patient's structural output still matches the committed
baseline JSON.

This test makes REAL Bedrock calls (~$2 cost per run, ~15-20 min wall
clock). It is gated by the env var ``RUN_EPISODE_ENGINE_FROZEN_VT=1`` so
it never runs in normal CI / pre-commit.

Comparison rules (intentionally tolerant - LLM outputs vary slightly
between runs and we don't want to chase noise):

  - episode_count must be within +/- 1 of baseline
  - for every baseline episode we must find an engine episode that
    matches on ``suspected_site`` (case-insensitive) AND covers all the
    baseline episode's milestone_types as a subset
  - treatment_types in the matched episode must cover the baseline
    treatment_types as a subset
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

_BASELINE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "regression"
    / "episode_engine_frozen"
    / "baseline.json"
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_EPISODE_ENGINE_FROZEN_VT") != "1",
    reason=(
        "Live LLM regression (~$2 / ~15-20 min). "
        "Set RUN_EPISODE_ENGINE_FROZEN_VT=1 to run."
    ),
)


def _load_baseline() -> dict:
    if not _BASELINE_PATH.exists():
        pytest.fail(
            f"Baseline file missing: {_BASELINE_PATH}. "
            "Run scripts/regression/episode_engine_frozen/regenerate_baseline.py."
        )
    return json.loads(_BASELINE_PATH.read_text())


def _engine_episode_summary(ep) -> dict:
    return {
        "episode_type": ep.episode_type,
        "suspected_site": (ep.suspected_site or "").lower(),
        "milestone_types": sorted({m.type for m in ep.milestones}),
        "treatment_types": sorted(
            {m.treatment_type for m in ep.milestones if m.treatment_type}
        ),
        "needs_human_review": bool(ep.needs_human_review),
    }


def _matches_baseline_episode(engine_eps: list[dict], expected: dict) -> dict | None:
    """Find an engine episode that matches the baseline episode's invariants."""
    for ep in engine_eps:
        if ep["suspected_site"] != expected["suspected_site"]:
            continue
        # episode_type must agree on cancer/non-cancer family
        if ep["episode_type"] != expected["episode_type"]:
            continue
        if not set(expected["milestone_types"]).issubset(set(ep["milestone_types"])):
            continue
        if not set(expected["treatment_types"]).issubset(set(ep["treatment_types"])):
            continue
        return ep
    return None


def test_frozen_cohort_engine_matches_baseline():
    """VT-507-TC-001: structural engine output matches baseline for all 20 patients."""

    from services.analysis_worker.app.episode_engine import run_episode_engine
    from scripts.regression.episode_engine_frozen.cohort_ids import FROZEN_COHORT

    baseline = _load_baseline()
    expected_patients = baseline["patients"]
    assert set(expected_patients.keys()) == set(FROZEN_COHORT), (
        "Baseline patient ids drifted from FROZEN_COHORT - regenerate baseline."
    )

    failures: list[str] = []
    for pid in FROZEN_COHORT:
        try:
            result = run_episode_engine(pid, dry_run=True)
        except Exception as exc:
            failures.append(f"{pid}: ENGINE CRASHED -- {type(exc).__name__}: {exc}")
            continue

        expected = expected_patients[pid]
        engine_summaries = [_engine_episode_summary(e) for e in result.episodes]

        if abs(result.episode_count - expected["episode_count"]) > 1:
            failures.append(
                f"{pid}: episode_count {result.episode_count} drifted from "
                f"baseline {expected['episode_count']} (>+/-1)"
            )

        for exp_ep in expected["episodes"]:
            match = _matches_baseline_episode(engine_summaries, exp_ep)
            if match is None:
                failures.append(
                    f"{pid}: no engine episode matches baseline "
                    f"site={exp_ep['suspected_site']} "
                    f"type={exp_ep['episode_type']} "
                    f"milestones={exp_ep['milestone_types']} "
                    f"treatments={exp_ep['treatment_types']}"
                )

    if failures:
        msg = "Frozen cohort regression failures ({n}):\n  - {body}".format(
            n=len(failures), body="\n  - ".join(failures)
        )
        pytest.fail(msg)
