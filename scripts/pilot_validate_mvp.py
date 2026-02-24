"""Pilot validation runner for HITL training creator MVP."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_PATH = ROOT / "services" / "api"
if str(API_PATH) not in sys.path:
    sys.path.append(str(API_PATH))

from app.db.neo4j_client import Neo4jClient  # noqa: E402
from app.services.training_creator import TrainingCreatorService  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--patient-id",
        action="append",
        required=True,
        help="Repeat this argument for pilot cohort.",
    )
    parser.add_argument(
        "--max-encounters-per-patient",
        type=int,
        default=50,
        help="Cap for rapid pilot runs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = Neo4jClient()
    client.initialize_schema()
    service = TrainingCreatorService(client)

    run_id, stats = service.run(
        patient_ids=args.patient_id,
        max_encounters_per_patient=args.max_encounters_per_patient,
        dry_run=False,
    )
    print("Pilot run summary")
    print(f"run_id={run_id}")
    print(f"patients={len(args.patient_id)}")
    print(f"processed_encounters={stats.processed_encounters}")
    print(f"queued_for_review={stats.queued_for_review}")
    print(f"rejected_hard_fail={stats.rejected_hard_fail}")
    print(f"warnings_only={stats.warnings_only}")
    client.close()


if __name__ == "__main__":
    main()
