#!/usr/bin/env python3
"""Stage 0a - Verify vector coverage prerequisite for the NCDA detector.

Walks the patient graph to confirm:
  1. encounter_vector_index exists and is online.
  2. >= 99% of Encounter nodes have Encounter.vector populated (the property
     the index is keyed on).

Exits 0 on pass, 1 on fail. The rest of the NCDA pipeline gates on this.

If coverage is below threshold, instructs the operator to run the
embedding reindex via the visual-report-builder clinical-ai service:

    POST /embeddings/reindex

Usage:
    python scripts/ncda/verify_vector_coverage.py
    python scripts/ncda/verify_vector_coverage.py --min-coverage 0.99
    python scripts/ncda/verify_vector_coverage.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from neo4j import GraphDatabase  # noqa: E402

VECTOR_INDEX_NAME = "encounter_vector_index"

_Q_INDEX = "SHOW INDEXES WHERE name = $name"
_Q_COVERAGE = """
MATCH (e:Encounter)
RETURN count(e) AS total, count(e.vector) AS with_vector
"""


def _connect() -> "GraphDatabase":
    uri = os.environ.get("NEO4J_PATIENT_URI", "").strip() or os.environ.get(
        "NEO4J_URI", ""
    ).strip()
    user = os.environ.get("NEO4J_PATIENT_USER", "").strip() or os.environ.get(
        "NEO4J_USER", ""
    ).strip()
    password = os.environ.get(
        "NEO4J_PATIENT_PASSWORD", ""
    ).strip() or os.environ.get("NEO4J_PASSWORD", "").strip()
    if not all([uri, user, password]):
        raise SystemExit(
            "ERROR: set NEO4J_PATIENT_URI / NEO4J_PATIENT_USER / "
            "NEO4J_PATIENT_PASSWORD (or NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD)."
        )
    return GraphDatabase.driver(uri, auth=(user, password))


def check_index(session) -> dict[str, object]:
    """Return index metadata or empty dict if not found."""
    rows = list(session.run(_Q_INDEX, name=VECTOR_INDEX_NAME))
    if not rows:
        return {}
    idx = dict(rows[0])
    return {
        "name": idx.get("name"),
        "type": idx.get("type"),
        "state": idx.get("state"),
        "labelsOrTypes": idx.get("labelsOrTypes"),
        "properties": idx.get("properties"),
    }


def check_coverage(session) -> dict[str, int | float]:
    """Return total and with_vector counts plus the coverage ratio."""
    row = session.run(_Q_COVERAGE).single()
    total = int(row["total"]) if row else 0
    with_vector = int(row["with_vector"]) if row else 0
    coverage = with_vector / total if total else 0.0
    return {"total": total, "with_vector": with_vector, "coverage": round(coverage, 4)}


def _print_human(index_meta: dict, coverage: dict, threshold: float, ok: bool) -> None:
    print(f"Vector index '{VECTOR_INDEX_NAME}':")
    if index_meta:
        print(f"  state: {index_meta.get('state', '?')}")
        print(f"  type: {index_meta.get('type', '?')}")
        print(f"  labels: {index_meta.get('labelsOrTypes', '?')}")
        print(f"  properties: {index_meta.get('properties', '?')}")
    else:
        print(f"  NOT FOUND - run POST /embeddings/reindex on clinical-ai service")
    pct = coverage["coverage"] * 100
    print(
        f"\nEncounter vector coverage: "
        f"{coverage['with_vector']} / {coverage['total']} ({pct:.2f}%)"
    )
    print(f"Threshold: {threshold * 100:.2f}%")
    print("Result:", "PASS" if ok else "FAIL")
    if not ok:
        print(
            "\nTo backfill, POST to the clinical-ai service /embeddings/reindex "
            "endpoint then re-run this script."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=0.99,
        help="Minimum vector coverage ratio (default 0.99).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args()

    driver = _connect()
    try:
        with driver.session() as session:
            index_meta = check_index(session)
            coverage = check_coverage(session)
    finally:
        driver.close()

    index_online = bool(index_meta) and index_meta.get("state") == "ONLINE"
    coverage_ok = float(coverage["coverage"]) >= args.min_coverage
    ok = index_online and coverage_ok

    if args.json:
        print(
            json.dumps(
                {
                    "index": index_meta,
                    "coverage": coverage,
                    "threshold": args.min_coverage,
                    "ok": ok,
                },
                indent=2,
            )
        )
    else:
        _print_human(index_meta, coverage, args.min_coverage, ok)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
