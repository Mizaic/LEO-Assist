"""Regenerate the frozen-cohort baseline for the episode engine VT.

Runs the engine in dry-run on the 20 canonical patients
(``cohort_ids.FROZEN_COHORT``) and writes a structural baseline JSON file
to ``baseline.json`` in this directory.

The baseline records, per patient:
  - episode_count
  - per-episode: episode_type, suspected_site, milestone_types (sorted),
    treatment_types (sorted), needs_human_review

We deliberately do NOT pin reasoning text, exact dates, evidence quotes or
confidence scores -- those are LLM outputs and would make the VT brittle.
The VT compares engine output against this baseline using TOLERANT rules
(see ``tests/episode_engine/test_frozen_cohort_vt.py``).

USAGE
=====

    python scripts/regression/episode_engine_frozen/regenerate_baseline.py

Cost: ~$2 in Bedrock tokens, ~15-20 minutes wall clock for 20 patients.
You should only re-run this when:
  - the engine prompts change AND you have manually reviewed the new
    output as still correct
  - a new patient is added to ``cohort_ids.FROZEN_COHORT``
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("frozen_cohort")

BASELINE_PATH = Path(__file__).with_name("baseline.json")


def _episode_summary(ep) -> dict:
    """Reduce an Episode model to the structural fields we pin."""
    milestone_types = sorted({m.type for m in ep.milestones})
    treatment_types = sorted({m.treatment_type for m in ep.milestones if m.treatment_type})
    return {
        "episode_type": ep.episode_type,
        "suspected_site": ep.suspected_site.lower(),
        "milestone_types": milestone_types,
        "treatment_types": treatment_types,
        "needs_human_review": bool(ep.needs_human_review),
    }


def _build_baseline_for_patient(patient_id: str) -> dict:
    from services.analysis_worker.app.episode_engine import run_episode_engine

    log.info("Generating baseline for %s", patient_id)
    result = run_episode_engine(patient_id, dry_run=True)
    return {
        "episode_count": result.episode_count,
        "errors": list(result.errors),
        "episodes": [_episode_summary(ep) for ep in result.episodes],
    }


def main() -> None:
    from scripts.regression.episode_engine_frozen.cohort_ids import FROZEN_COHORT

    baseline: dict[str, dict] = {}
    for pid in FROZEN_COHORT:
        try:
            baseline[pid] = _build_baseline_for_patient(pid)
        except Exception as exc:
            log.exception("Engine failed for patient %s", pid)
            baseline[pid] = {
                "episode_count": -1,
                "errors": [f"{type(exc).__name__}: {exc}"],
                "episodes": [],
            }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine_version": "haiku-engine-v1",
        "cohort_size": len(FROZEN_COHORT),
        "patients": baseline,
    }

    BASELINE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")
    log.info("Wrote baseline -> %s", BASELINE_PATH)
    log.info(
        "Total episodes: %d across %d patients",
        sum(p.get("episode_count", 0) for p in baseline.values()),
        len(baseline),
    )


if __name__ == "__main__":
    main()
