"""Backfill IS_PART_OF encounter-episode relationships for existing episodes.

Existing EpisodeOfCare nodes were created before the episode builder wrote
IS_PART_OF edges. Without these edges, audit/KPI queries that match
(Encounter)-[:IS_PART_OF]->(EpisodeOfCare) return zero rows.

This script rebuilds all patients' episodes using the existing episode
builder (which now writes IS_PART_OF edges). Run once after deploying the
episode_builder fix.

Usage:
    python scripts/investigations/_backfill_is_part_of.py [--dry-run] [--patient-id PID]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# -- Secret loading (same pattern as all other investigation scripts) ---------
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_keyvault_secrets()
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _run_for_patient(patient_id: str, dry_run: bool, registry) -> dict:
    from libs.neo4j_client.client import PatientGraphClient  # noqa: PLC0415
    from services.analysis_worker.app.analyzers.anchor_detector import detect_anchors  # noqa: PLC0415
    from services.analysis_worker.app.analyzers.episode_builder import build_episodes  # noqa: PLC0415

    client = PatientGraphClient()
    try:
        if dry_run:
            anchors = detect_anchors(
                patient_id=patient_id,
                start_date="2000-01-01",
                end_date="2030-12-31",
                patient_client=client,
                registry=registry,
            )
            ref_count = len(anchors.referral_anchors)
            diag_count = len(anchors.diagnosis_anchors)
            logger.info(
                "DRY-RUN patient=%s refs=%d diags=%d",
                patient_id,
                ref_count,
                diag_count,
            )
            return {"patient_id": patient_id, "status": "dry_run"}

        client.run(
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE toString(p.id) = $pid "
            "DETACH DELETE ep",
            pid=patient_id,
        )
        anchors = detect_anchors(
            patient_id=patient_id,
            start_date="2000-01-01",
            end_date="2030-12-31",
            patient_client=client,
            registry=registry,
        )
        result = asyncio.run(
            build_episodes(
                patient_id=patient_id,
                anchors=anchors,
                patient_client=client,
            )
        )
        logger.info(
            "patient=%s created=%d errors=%d",
            patient_id,
            result.episodes_created,
            len(result.errors),
        )
        return {
            "patient_id": patient_id,
            "episodes_created": result.episodes_created,
            "errors": result.errors,
        }
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill IS_PART_OF edges")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to Neo4j")
    parser.add_argument("--patient-id", help="Run for one patient only")
    parser.add_argument("--domain-id", default="", help="Domain ID to scope the registry (default: all episode-detector domains)")
    args = parser.parse_args()

    from libs.neo4j_client.client import PatientGraphClient  # noqa: PLC0415
    from libs.pipeline_graph.subgraphs.anchor import _load_registry  # noqa: PLC0415

    logger.info("Loading domain registry (domain_id=%r) ...", args.domain_id)
    registry = _load_registry(args.domain_id)
    logger.info("Registry loaded.")

    client = PatientGraphClient()
    try:
        if args.patient_id:
            patient_ids = [args.patient_id]
        else:
            rows = client.run("MATCH (p:Patient) RETURN toString(p.id) AS pid ORDER BY pid")
            patient_ids = [r["pid"] for r in rows if r.get("pid")]
    finally:
        client.close()

    logger.info("Backfilling IS_PART_OF for %d patients (dry_run=%s)", len(patient_ids), args.dry_run)

    ok = err = 0
    for pid in patient_ids:
        try:
            _run_for_patient(pid, args.dry_run, registry)
            ok += 1
        except Exception as exc:
            logger.error("patient=%s error=%s", pid, exc)
            err += 1

    logger.info("Done: ok=%d errors=%d", ok, err)
    sys.exit(0 if err == 0 else 1)


if __name__ == "__main__":
    main()
