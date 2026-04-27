"""Persist Episode Detector v2 output to Neo4j for one patient.

By default merges **auto** and **suggest** tiers so curators can sign off
suggest-tier pathways in Mission Control (pipeline runs only persist auto).

Usage::

    python -m scripts.episode_v2.persist_patient_v2 --patient-id 6142203497
    python -m scripts.episode_v2.persist_patient_v2 --patient-id X --tiers auto
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import FrozenSet

from scripts.episode_v2.dry_run_patient import _install_v1_bundle

logger = logging.getLogger(__name__)


def _parse_tiers(raw: str) -> FrozenSet[str]:
    parts = {p.strip().lower() for p in raw.split(",") if p.strip()}
    allowed = {"auto", "suggest", "review"}
    bad = parts - allowed
    if bad:
        raise SystemExit(f"Unknown tier(s) {bad!r}; allowed: {sorted(allowed)}")
    return frozenset(parts)


async def _run(patient_id: str, tiers: FrozenSet[str]) -> int:
    from libs.keyvault.loader import load_keyvault_secrets
    from libs.neo4j_client.client import PatientGraphClient
    from services.analysis_worker.app.episode_detector_v2.runner import build_episodes

    load_keyvault_secrets()
    _install_v1_bundle()
    client = PatientGraphClient()
    try:
        result = await build_episodes(
            patient_id=patient_id,
            patient_client=client,
            anchors=None,
            domain_id="",
            persist_confidence_tiers=tiers,
        )
    finally:
        client.close()

    payload = {
        "patient_id": result.patient_id,
        "episodes_created": result.episodes_created,
        "episodes_completed": result.episodes_completed,
        "encounters_linked": result.encounters_linked,
        "episode_ids": result.episode_ids,
        "review_count": result.review_count,
        "errors": result.errors,
        "resolved": [
            {
                "episode_id": ep.episode_id,
                "site_key": ep.site_key,
                "tier": ep.confidence_tier,
                "status": ep.status,
                "intent": ep.intent,
                "start_date": ep.start_date.isoformat() if ep.start_date else None,
                "end_date": ep.end_date.isoformat() if ep.end_date else None,
                "encounter_count": len(ep.encounter_ids),
                "needs_human_review": ep.needs_human_review,
                "review_reasons": ep.review_reasons,
            }
            for ep in result.resolved_episodes
        ],
    }
    print(json.dumps(payload, indent=2, sort_keys=False))
    if not result.episode_ids:
        logger.warning("No episodes persisted (check tiers vs detector output).")
        return 1
    if result.errors:
        for err in result.errors:
            logger.warning("Detector note: %s", err)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient-id", required=True)
    parser.add_argument(
        "--tiers",
        default="auto,suggest",
        help="Comma-separated confidence tiers to MERGE (default: auto,suggest).",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    tiers = _parse_tiers(args.tiers)
    return asyncio.run(_run(args.patient_id, tiers))


if __name__ == "__main__":
    raise SystemExit(main())
