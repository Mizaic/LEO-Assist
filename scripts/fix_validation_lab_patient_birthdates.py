#!/usr/bin/env python3
"""Backfill Validation Lab Patient.birthDate from ValidationCase prose.

DevOps one-liner (after secrets are loaded locally):
  python -m scripts.fix_validation_lab_patient_birthdates --apply

Default mode is dry-run: prints planned updates without writing to Neo4j.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / "secrets" / ".env.config")
load_dotenv(_REPO_ROOT / "secrets" / ".env.secrets")

from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402
from libs.neo4j_client.client import PatientGraphClient  # noqa: E402
from libs.validation_lab.birthdate_backfill import (  # noqa: E402
    backfill_validation_lab_birthdates,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Write birthDate to Neo4j. Without this flag the run is dry-run."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    load_keyvault_secrets()
    client = PatientGraphClient()
    try:
        report = backfill_validation_lab_birthdates(client, dry_run=not args.apply)
    finally:
        client.close()

    mode = "dry-run" if report.dry_run else "apply"
    print(f"validation-lab birthDate backfill ({mode})")
    print(f"  missing before: {report.missing_before}")
    print(f"  planned:        {report.planned}")
    print(f"  skipped:        {report.skipped}")
    if not report.dry_run:
        print(f"  updated:        {report.updated}")
        print(f"  missing after:  {report.missing_after}")
    for item in report.updates:
        if report.dry_run:
            print(
                f"  would set {item['patient_id']} "
                f"(case {item.get('case_id', '')}) -> {item['birth_date']}"
            )
        else:
            print(
                f"  set {item.get('patient_id', '')} -> "
                f"{item.get('birth_date', '')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
