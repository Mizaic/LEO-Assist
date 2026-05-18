"""Build the labelled regression cohort for Episode Detector v2.

Atlas trace:
  DI: DI-8A5FCF4F (Defence-in-depth episode detector with coverage fail-safe)
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-8A5FCF4F")

Picks patient 9990001004 as the seeded gold case (concurrent UGI 2WW,
confirmed breast cancer, benign-closed lung pathway -- the case that
exposed every failure mode of the v1 detectors). Then queries the graph
for additional patients with the most :AuditEvent rows of type
EpisodeManualAttach or EpisodeManualDetach (i.e. patients where ops has
already corrected the auto-detected episodes manually) and selects up
to nine more, biased toward variety: at least three single-pathway,
three concurrent multi-pathway, and three with at least one benign
closure.

Output is written to compliance/episode-v2-regression-cohort.json with
schema:

    {
      "version": 1,
      "generated_at": "2026-04-22T...",
      "seed_case": "9990001004",
      "cohort": [
        {
          "patient_id": "...",
          "selection_reason": "seed | manual_corrections | benign_closure | multi_pathway",
          "manual_event_count": int,
          "current_episode_ids": [...],
          "expected_episode_count_min": int,
          "notes": "..."
        }
      ]
    }

Run: python -m scripts.episode_v2.build_regression_cohort [--limit 10] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SEED_PATIENT = "9990001004"
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[2]
    / "compliance"
    / "episode-v2-regression-cohort.json"
)
DEFAULT_LIMIT = 10
SINGLE_PATHWAY_TARGET = 3
MULTI_PATHWAY_TARGET = 3
BENIGN_CLOSURE_TARGET = 3


def _seed_case_entry() -> dict[str, Any]:
    return {
        "patient_id": SEED_PATIENT,
        "selection_reason": "seed",
        "manual_event_count": None,
        "current_episode_ids": [],
        "expected_episode_count_min": 3,
        "notes": (
            "Concurrent upper GI 2WW (manual), confirmed breast cancer "
            "(auto-detected), and benign-closed lung pathway (manual). "
            "v1 detectors lost two of three pathways with no flag. "
            "v2 must produce all three episodes (or flag for review)."
        ),
    }


def _candidate_query() -> str:
    return """
        MATCH (a:AuditEvent)
        WHERE a.type IN ['EpisodeManualAttach', 'EpisodeManualDetach']
          AND a.patient_id IS NOT NULL
        WITH a.patient_id AS patient_id, count(*) AS event_count,
             collect(DISTINCT a.type) AS event_types
        OPTIONAL MATCH (p:Patient {patient_id: patient_id})
        OPTIONAL MATCH (p)-[:HAS_EPISODE]->(e:EpisodeOfCare)
        WITH patient_id, event_count, event_types,
             collect(DISTINCT e.episode_id) AS episode_ids,
             collect(DISTINCT e.suspected_site) AS sites,
             collect(DISTINCT e.status) AS statuses
        WHERE patient_id <> $seed_patient
        RETURN patient_id,
               event_count,
               event_types,
               episode_ids,
               sites,
               statuses
        ORDER BY event_count DESC
        LIMIT $candidate_limit
    """


def _classify_candidate(row: dict[str, Any]) -> str:
    statuses = [s for s in (row.get("statuses") or []) if s]
    sites = [s for s in (row.get("sites") or []) if s]
    if any(s == "benign_closure" or s == "closed_benign" for s in statuses):
        return "benign_closure"
    if len(sites) >= 2:
        return "multi_pathway"
    if len(row.get("episode_ids") or []) <= 1:
        return "single_pathway"
    return "manual_corrections"


def _select_balanced(candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Pick up to limit-1 candidates aiming for variety."""
    quota = {
        "single_pathway": SINGLE_PATHWAY_TARGET,
        "multi_pathway": MULTI_PATHWAY_TARGET,
        "benign_closure": BENIGN_CLOSURE_TARGET,
    }
    chosen: list[dict[str, Any]] = []
    leftover: list[dict[str, Any]] = []
    for cand in candidates:
        bucket = _classify_candidate(cand)
        if quota.get(bucket, 0) > 0:
            chosen.append({**cand, "selection_reason": bucket})
            quota[bucket] -= 1
        else:
            leftover.append({**cand, "selection_reason": "manual_corrections"})
        if len(chosen) >= limit - 1:
            break
    while len(chosen) < limit - 1 and leftover:
        chosen.append(leftover.pop(0))
    return chosen


def _candidate_to_entry(cand: dict[str, Any]) -> dict[str, Any]:
    sites = [s for s in (cand.get("sites") or []) if s]
    return {
        "patient_id": str(cand.get("patient_id") or ""),
        "selection_reason": cand.get("selection_reason") or "manual_corrections",
        "manual_event_count": int(cand.get("event_count") or 0),
        "current_episode_ids": [str(e) for e in (cand.get("episode_ids") or []) if e],
        "expected_episode_count_min": max(1, len(sites) or 1),
        "notes": (
            f"Selected because clinicians have made "
            f"{int(cand.get('event_count') or 0)} manual episode "
            f"corrections; current sites: {', '.join(sites) or 'unknown'}."
        ),
    }


def fetch_candidates(client, limit: int) -> list[dict[str, Any]]:
    """Query the graph for candidate patients. Returns raw dicts."""
    rows = client.run(
        _candidate_query(),
        seed_patient=SEED_PATIENT,
        candidate_limit=max(limit * 4, limit),
    )
    return [dict(row) for row in rows]


def build_cohort(
    candidates: list[dict[str, Any]],
    *,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Build the cohort dict. Pure function for testability."""
    seed = _seed_case_entry()
    deduped = [c for c in candidates if str(c.get("patient_id")) != SEED_PATIENT]
    selected = _select_balanced(deduped, limit=limit)
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed_case": SEED_PATIENT,
        "cohort": [seed] + [_candidate_to_entry(c) for c in selected],
    }


def write_cohort(cohort: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cohort, indent=2, sort_keys=False) + "\n")
    logger.info("Wrote regression cohort with %d cases to %s", len(cohort["cohort"]), path)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the cohort to stdout without writing.",
    )
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args()
    try:
        from libs.neo4j_client.client import PatientGraphClient
    except Exception as exc:
        logger.error("Cannot import PatientGraphClient: %s", exc)
        return 2

    client = PatientGraphClient()
    try:
        candidates = fetch_candidates(client, limit=args.limit)
    finally:
        client.close()

    cohort = build_cohort(candidates, limit=args.limit)
    if args.dry_run:
        json.dump(cohort, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        write_cohort(cohort, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
