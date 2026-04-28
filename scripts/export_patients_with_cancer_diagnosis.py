"""Export patient identifiers that have >= one cancer-diagnosis SNOMED on DOCUMENTS.

Uses ``CANCER_TYPE_IDS`` (NCDA milestone diagnoses) merged with
``DOCUMENTS_DISORDER_MALIGNANCY_IDS`` (disorder-labelled malignancies observed in graph).
Optional: include ambiguous bladder neoplasm (126885006).

Output CSV columns:
  patient_id          Practice identifier (coalesce patient_id, id on :Patient)
  distinct_concepts   Count of distinct matching SNOMED concept ids
  concept_ids         Semicolon-separated sorted SNOMED ids

Do not commit generated CSV files; ``artifacts/patient_exports/*`` is gitignored.

Usage:

  python3 scripts/export_patients_with_cancer_diagnosis.py \\
      --output artifacts/patient_exports/patients_with_cancer_diagnosis.csv

  python3 scripts/export_patients_with_cancer_diagnosis.py --stdout
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.domains.documents_disorder_malignancy_ids import (
    DOCUMENTS_DISORDER_MALIGNANCY_IDS,
    DOCUMENTS_DISORDER_NEOPLASM_AMBIGUOUS_IDS,
)
from libs.domains.ncda_concept_sets import CANCER_TYPE_IDS
from libs.neo4j_client.client import PatientGraphClient

_Q_EXPORT = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(:Encounter)-[:DOCUMENTS]->(c)
WHERE toString(c.conceptId) IN $concept_ids
WITH coalesce(toString(p.patient_id), toString(p.id)) AS patient_id,
     collect(DISTINCT toString(c.conceptId)) AS raw_ids
RETURN patient_id,
       raw_ids,
       size(raw_ids) AS distinct_concepts
ORDER BY patient_id
"""


def _concept_id_strings(
    *,
    include_ambiguous_bladder: bool,
) -> list[str]:
    merged: set[int] = set(CANCER_TYPE_IDS) | set(DOCUMENTS_DISORDER_MALIGNANCY_IDS)
    if include_ambiguous_bladder:
        merged |= set(DOCUMENTS_DISORDER_NEOPLASM_AMBIGUOUS_IDS)
    return sorted({str(i) for i in merged})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="CSV path (parent dirs created). Ignored if --stdout.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print CSV to stdout instead of writing a file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Write JSON array instead of CSV (--stdout prints JSON).",
    )
    parser.add_argument(
        "--include-ambiguous-bladder-neoplasm",
        action="store_true",
        help="Include SNOMED 126885006 (Neoplasm of urinary bladder; may be benign).",
    )
    args = parser.parse_args()

    concept_ids = _concept_id_strings(
        include_ambiguous_bladder=args.include_ambiguous_bladder_neoplasm,
    )

    client = PatientGraphClient()
    rows: list[dict[str, object]] = []
    with client.session() as session:
        result = session.run(
            _Q_EXPORT,
            concept_ids=concept_ids,
        )
        for record in result:
            raw_ids = sorted(record["raw_ids"])
            rows.append(
                {
                    "patient_id": record["patient_id"],
                    "distinct_concepts": int(record["distinct_concepts"]),
                    "concept_ids": ";".join(raw_ids),
                }
            )

    if args.json:
        payload = [
            {
                "patient_id": r["patient_id"],
                "distinct_concepts": r["distinct_concepts"],
                "concept_ids": r["concept_ids"].split(";") if r["concept_ids"] else [],
            }
            for r in rows
        ]
        text = json.dumps(payload, indent=2)
        if args.stdout:
            sys.stdout.write(text + "\n")
        elif args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
            print(f"Wrote {len(rows)} patients to {args.output}", file=sys.stderr)
        else:
            parser.error("--json requires --output or --stdout")
        return

    fieldnames = ["patient_id", "distinct_concepts", "concept_ids"]
    if args.stdout:
        w = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "patient_id": r["patient_id"],
                    "distinct_concepts": r["distinct_concepts"],
                    "concept_ids": r["concept_ids"],
                }
            )
        print(f"# rows: {len(rows)}", file=sys.stderr)
        return

    if not args.output:
        parser.error("Provide --output PATH or use --stdout")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "patient_id": r["patient_id"],
                    "distinct_concepts": r["distinct_concepts"],
                    "concept_ids": r["concept_ids"],
                }
            )
    print(f"Wrote {len(rows)} patients to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
