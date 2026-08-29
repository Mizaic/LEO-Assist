"""Delete all :DOCUMENTS relationships written by specific pipeline runs.

This is a targeted cleanup for runs that produced incorrect facts
(guidance text extracted as patient findings, or Section C narrative
deleted before extraction). After running this, re-run the pipeline
with the fixed code to produce clean facts.

Writes to whichever graph NEO4J_URI points at. Not a dry run unless
--dry-run is passed.

Usage:
    # Dry run -- see what would be deleted, write nothing:
    .venv/bin/python scripts/investigations/clean_run_facts.py --dry-run \\
        --run 68844cf65ad34b0e915520f938061f23 \\
        --run 5fa6348091364fa793e6d6d674fe470a \\
        --run 95142b16a7d7412696e60592800c6a6e \\
        --run 9efaca5f03214f8c9b104f4813412f9e \\
        --run 455cca102c8b448f83cf5cc1dc81fbd2

    # Live delete:
    .venv/bin/python scripts/investigations/clean_run_facts.py \\
        --run 68844cf65ad34b0e915520f938061f23 \\
        --run 5fa6348091364fa793e6d6d674fe470a \\
        --run 95142b16a7d7412696e60592800c6a6e \\
        --run 9efaca5f03214f8c9b104f4813412f9e \\
        --run 455cca102c8b448f83cf5cc1dc81fbd2
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / ".env", override=False)

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

_COUNT_CHUNK_DOCS = """
MATCH (c:Chunk)-[r:DOCUMENTS]->()
WHERE r.run_id = $run_id
RETURN count(r) AS n
"""

_COUNT_ENCOUNTER_DOCS = """
MATCH (e:Encounter)-[r:DOCUMENTS]->()
WHERE r.run_id = $run_id
RETURN count(r) AS n
"""

_DELETE_CHUNK_DOCS = """
MATCH (c:Chunk)-[r:DOCUMENTS]->()
WHERE r.run_id = $run_id
DELETE r
RETURN count(r) AS deleted
"""

_DELETE_ENCOUNTER_DOCS = """
MATCH (e:Encounter)-[r:DOCUMENTS]->()
WHERE r.run_id = $run_id
DELETE r
RETURN count(r) AS deleted
"""


def _count(client: PatientGraphClient, run_id: str) -> int:
    chunk = client.run(_COUNT_CHUNK_DOCS, run_id=run_id)
    enc = client.run(_COUNT_ENCOUNTER_DOCS, run_id=run_id)
    return int((chunk[0]["n"] if chunk else 0) + (enc[0]["n"] if enc else 0))


def _delete(client: PatientGraphClient, run_id: str) -> int:
    chunk = client.run(_DELETE_CHUNK_DOCS, run_id=run_id)
    enc = client.run(_DELETE_ENCOUNTER_DOCS, run_id=run_id)
    return int(
        (chunk[0]["deleted"] if chunk else 0)
        + (enc[0]["deleted"] if enc else 0)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", action="append", required=True, metavar="RUN_ID",
        help="run_id to clean (repeat for multiple)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Count facts but do not delete them",
    )
    args = parser.parse_args()

    client = PatientGraphClient()
    total = 0
    try:
        for run_id in args.run:
            if args.dry_run:
                n = _count(client, run_id)
                print(f"DRY RUN  run={run_id}  facts_to_delete={n}")
                total += n
            else:
                n = _delete(client, run_id)
                print(f"DELETED  run={run_id}  facts_deleted={n}")
                total += n
    finally:
        client.close()

    label = "facts to delete" if args.dry_run else "facts deleted"
    print(f"\nTotal {label}: {total}")
    if args.dry_run:
        print("Re-run without --dry-run to apply.")


if __name__ == "__main__":
    main()
