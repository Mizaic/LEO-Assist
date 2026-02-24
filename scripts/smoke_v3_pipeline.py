"""V3 pipeline smoke test: run on one patient and verify counts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_PATH = ROOT / "services" / "api"
if str(API_PATH) not in sys.path:
    sys.path.insert(0, str(API_PATH))

from app.db.neo4j_client import CodingGraphClient, PatientGraphClient
from app.services.v3.pipeline_service import V3PipelineService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--patient-id",
        default="4202301609",
        help="Patient ID for cutover verification (default: 4202301609).",
    )
    parser.add_argument(
        "--max-encounters",
        type=int,
        default=5,
        help="Max encounters per patient (default: 5).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip persistence (no graph writes).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    coding_client = CodingGraphClient()
    patient_client = PatientGraphClient()
    coding_client.initialize_schema()

    service = V3PipelineService(
        patient_client=patient_client,
        coding_client=coding_client,
    )

    run_id, stats = service.run(
        patient_ids=[args.patient_id],
        max_encounters_per_patient=args.max_encounters,
        dry_run=args.dry_run,
        workers=1,
    )

    print("V3 pipeline smoke run")
    print(f"  run_id: {run_id}")
    print(f"  patient_id: {args.patient_id}")
    print(f"  dry_run: {args.dry_run}")
    print(f"  processed_encounters: {stats.processed_encounters}")
    print(f"  queued_for_review: {stats.queued_for_review}")
    print(f"  rejected_hard_fail: {stats.rejected_hard_fail}")
    print(f"  warnings_only: {stats.warnings_only}")

    if not args.dry_run and stats.processed_encounters > 0:
        with coding_client.session() as session:
            result = session.run(
                "MATCH (c:EncounterCandidate)-[:HAS_TASK]->(t:ReviewTask) "
                "WHERE c.patient_id = $pid "
                "RETURN c.encounter_id AS encounter_id, t.status AS status "
                "ORDER BY c.encounter_id LIMIT $limit",
                pid=args.patient_id,
                limit=args.max_encounters,
            )
            rows = list(result)
            print(f"  coding_graph: {len(rows)} candidates queued for review")
            print("  (Patient graph DOCUMENTS written via sync-gold only)")

    patient_client.close()
    coding_client.close()

    if stats.processed_encounters == 0:
        print("WARNING: No encounters processed — check patient exists in patient graph.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
