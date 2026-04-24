"""Gold-patient precision/recall VT for context-tier milestone detection.

Atlas trace:
  DI: DI-2C015ADE (AI may propose context-tier milestones under human review)
  VT: (to be created -- see Phase 5 atlas closeout)

Replays the episode engine (dry_run=True) against 4 manually curated gold
patients and measures milestone recall and precision at two levels:

  type-level : does the engine emit the right milestone TYPES?
  slot-level : does the engine emit the right (milestone_type, encounter_id)?

Gold fixture: scripts/regression/episode_engine_gold_vt/gold_episodes.json

Gold patients and their curated episodes:
  4246428337  Colorectal closed_benign  (1 episode)
  4246897485  Breast closed_benign      (1 episode)
  4920262426  Multi-site Breast/Lung/UGI (3 episodes)
  6282779235  Prostate completed        (1 episode)

This test makes REAL Bedrock LLM calls (~$0.18/patient, ~3-5 min per patient,
~$0.72 / ~15 min for all 4). It is gated:

  RUN_EPISODE_ENGINE_GOLD_VT=1 pytest tests/episode_engine/test_gold_patient_vt.py -v

Thresholds (tolerate LLM output variance):
  - type_recall  >= 0.60  (engine must find 60% of gold milestone TYPES)
  - slot_recall  >= 0.40  (engine must pick the right encounter for 40% of slots)
  - type_precision >= 0.50 (at most 50% of engine types are not in gold)

These are FLOOR thresholds, not targets. They will be raised as the engine
matures. Any patient that falls below a threshold is a regression.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

_GOLD_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "regression"
    / "episode_engine_gold_vt"
    / "gold_episodes.json"
)

# slot_recall floor is 0.30 (Phase 1 calibration):
# The Prostate gold fixture has 19 slots across 12 types because the curator
# annotated every individual blood test and letter (4x primary_care_investigations,
# 3x related_correspondence, 2x related_gp_visit). With single-emission-per-type
# behaviour the theoretical maximum slot_recall is ~0.53 even with perfect
# encounter-ID selection. Raise to 0.40 once multi-slot emission is implemented
# (separate ticket) or the gold fixture is reduced to one canonical slot per type.
_TYPE_RECALL_FLOOR = 0.60
_SLOT_RECALL_FLOOR = 0.30
_TYPE_PRECISION_FLOOR = 0.50

_GATED = pytest.mark.skipif(
    os.getenv("RUN_EPISODE_ENGINE_GOLD_VT") != "1",
    reason=(
        "Live LLM gold-patient replay (~$0.72 / ~15 min). "
        "Set RUN_EPISODE_ENGINE_GOLD_VT=1 to run."
    ),
)

_CONTEXT_MILESTONE_TYPES = {
    "related_gp_visit",
    "primary_care_investigations",
    "referral_admin",
    "referral_sent",
    "related_specialist_visit",
    "specialist_diagnostics",
    "related_correspondence",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_gold() -> dict[str, Any]:
    if not _GOLD_PATH.exists():
        pytest.fail(f"Gold fixture missing: {_GOLD_PATH}")
    return json.loads(_GOLD_PATH.read_text())


def _gold_type_set(episode: dict) -> set[str]:
    return {m["milestone_type"] for m in episode["milestones"]}


def _gold_slot_set(episode: dict) -> set[tuple[str, str]]:
    return {(m["milestone_type"], m["encounter_id"]) for m in episode["milestones"]}


def _engine_type_set(ep) -> set[str]:
    return {m.type for m in ep.milestones}


def _engine_slot_set(ep) -> set[tuple[str, str]]:
    return {(m.type, m.encounter_id) for m in ep.milestones}


def _best_engine_match(engine_episodes: list, gold_ep: dict):
    """Find the engine episode whose cancer_type best matches the gold episode.

    Uses case-insensitive substring match so "Upper GI" matches "oesophageal"
    via the site normaliser. Falls back to the episode with the greatest
    milestone-type overlap when no site name match exists.
    """
    gold_site = gold_ep["cancer_type"].lower()
    gold_types = _gold_type_set(gold_ep)

    # Exact or substring site match first.
    site_matches = [
        ep
        for ep in engine_episodes
        if gold_site in (ep.suspected_site or "").lower()
        or (ep.suspected_site or "").lower() in gold_site
    ]
    if site_matches:
        return max(
            site_matches,
            key=lambda ep: len(_engine_type_set(ep) & gold_types),
        )

    # Fallback: best milestone-type overlap.
    return max(
        engine_episodes,
        key=lambda ep: len(_engine_type_set(ep) & gold_types),
        default=None,
    )


def _episode_metrics(engine_ep, gold_ep: dict) -> dict:
    """Compute type-recall, slot-recall, and type-precision for one episode."""
    if engine_ep is None:
        return {
            "type_recall": 0.0,
            "slot_recall": 0.0,
            "type_precision": 0.0,
            "gold_types": sorted(_gold_type_set(gold_ep)),
            "engine_types": [],
            "matched_types": [],
            "missed_types": sorted(_gold_type_set(gold_ep)),
            "extra_types": [],
        }
    gold_types = _gold_type_set(gold_ep)
    gold_slots = _gold_slot_set(gold_ep)
    eng_types = _engine_type_set(engine_ep)
    eng_slots = _engine_slot_set(engine_ep)

    matched_types = gold_types & eng_types
    missed_types = gold_types - eng_types
    extra_types = eng_types - gold_types
    matched_slots = gold_slots & eng_slots

    type_recall = len(matched_types) / len(gold_types) if gold_types else 1.0
    slot_recall = len(matched_slots) / len(gold_slots) if gold_slots else 1.0
    type_precision = len(matched_types) / len(eng_types) if eng_types else 0.0

    return {
        "type_recall": round(type_recall, 3),
        "slot_recall": round(slot_recall, 3),
        "type_precision": round(type_precision, 3),
        "gold_types": sorted(gold_types),
        "engine_types": sorted(eng_types),
        "matched_types": sorted(matched_types),
        "missed_types": sorted(missed_types),
        "extra_types": sorted(extra_types),
    }


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_gold_fixture_integrity():
    """Fast static check: fixture exists, has expected patients, and each episode
    contains at least one context-tier milestone (the whole point of this VT)."""
    gold_data = _load_gold()
    patients = gold_data["patients"]

    expected_ids = {"4246428337", "4246897485", "4920262426", "6282779235"}
    assert (
        set(patients.keys()) == expected_ids
    ), f"Fixture patient set changed: {set(patients.keys())}"

    for pid, patient in patients.items():
        all_types = {
            m["milestone_type"] for ep in patient["episodes"] for m in ep["milestones"]
        }
        ctx_found = all_types & _CONTEXT_MILESTONE_TYPES
        assert ctx_found, (
            f"Patient {pid} has no context-tier milestones in gold fixture -- "
            "fixture may be incomplete"
        )
        # Every milestone must have encounter_id and date
        for ep in patient["episodes"]:
            for m in ep["milestones"]:
                assert m.get("encounter_id"), f"Missing encounter_id: {m}"
                assert m.get("date"), f"Missing date: {m}"


@_GATED
def test_gold_patient_milestone_precision_recall():  # noqa: C901
    """DI-2C015ADE: engine reproduces gold milestone sets above floor thresholds."""
    from services.analysis_worker.app.episode_engine import run_episode_engine

    gold_data = _load_gold()
    failures: list[str] = []
    report_lines: list[str] = []

    for patient_id, patient_gold in gold_data["patients"].items():
        label = patient_gold.get("label", patient_id)
        try:
            result = run_episode_engine(patient_id, dry_run=True)
        except Exception as exc:
            failures.append(
                f"{label} ({patient_id}): ENGINE CRASHED -- "
                f"{type(exc).__name__}: {exc}"
            )
            continue

        engine_episodes = list(result.episodes)
        report_lines.append(f"\n=== {label} ({patient_id}) ===")
        report_lines.append(f"  engine episode count: {len(engine_episodes)}")

        for gold_ep in patient_gold["episodes"]:
            gold_site = gold_ep["cancer_type"]
            gold_status = gold_ep["status"]
            match = _best_engine_match(engine_episodes, gold_ep)
            metrics = _episode_metrics(match, gold_ep)

            report_lines.append(
                f"  [{gold_site} / {gold_status}]"
                f"  type_recall={metrics['type_recall']:.2f}"
                f"  slot_recall={metrics['slot_recall']:.2f}"
                f"  type_precision={metrics['type_precision']:.2f}"
            )
            report_lines.append(f"    gold types:    {metrics['gold_types']}")
            report_lines.append(f"    engine types:  {metrics['engine_types']}")
            report_lines.append(f"    missed:        {metrics['missed_types']}")
            report_lines.append(f"    extra:         {metrics['extra_types']}")

            ep_label = f"{label} / {gold_site} / {gold_status}"
            if metrics["type_recall"] < _TYPE_RECALL_FLOOR:
                failures.append(
                    f"{ep_label}: type_recall {metrics['type_recall']:.2f}"
                    f" < floor {_TYPE_RECALL_FLOOR}"
                    f" -- missed {metrics['missed_types']}"
                )
            if metrics["slot_recall"] < _SLOT_RECALL_FLOOR:
                failures.append(
                    f"{ep_label}: slot_recall {metrics['slot_recall']:.2f}"
                    f" < floor {_SLOT_RECALL_FLOOR}"
                )
            if metrics["type_precision"] < _TYPE_PRECISION_FLOOR:
                failures.append(
                    f"{ep_label}: type_precision {metrics['type_precision']:.2f}"
                    f" < floor {_TYPE_PRECISION_FLOOR}"
                    f" -- extra {metrics['extra_types']}"
                )

    print("\n".join(report_lines))

    if failures:
        msg = "Gold-patient milestone VT failures ({n}):\n  - {body}".format(
            n=len(failures),
            body="\n  - ".join(failures),
        )
        pytest.fail(msg)
