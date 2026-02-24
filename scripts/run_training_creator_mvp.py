"""CLI entrypoint for HITL training candidate generation."""

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
        help="Patient ID to process. Repeat for multiple.",
    )
    parser.add_argument(
        "--max-encounters-per-patient",
        type=int,
        default=None,
        help="Optional max encounter cap per patient.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = Neo4jClient()
    client.initialize_schema()
    service = TrainingCreatorService(client)
    run_id, stats = service.run(
        patient_ids=args.patient_id,
        max_encounters_per_patient=args.max_encounters_per_patient,
        dry_run=args.dry_run,
    )
    print(
        {
            "run_id": run_id,
            "processed_encounters": stats.processed_encounters,
            "queued_for_review": stats.queued_for_review,
            "rejected_hard_fail": stats.rejected_hard_fail,
            "warnings_only": stats.warnings_only,
        }
    )
    client.close()


if __name__ == "__main__":
    main()
