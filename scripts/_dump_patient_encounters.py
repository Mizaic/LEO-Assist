"""One-off: dump encounter text for specific patient/date combos.

Used to investigate phantom milestones surfaced by the episode detector.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)


_Q = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $pid AND toString(date(e.date)) IN $dates
RETURN toString(date(e.date)) AS date,
       e.id AS eid,
       coalesce(e.text, '') AS text,
       coalesce(e.encounter_type, '') AS encounter_type
ORDER BY e.date, e.id
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--patient", required=True)
    parser.add_argument("--dates", nargs="+", required=True)
    parser.add_argument("--max-chars", type=int, default=4000)
    args = parser.parse_args()

    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()
    try:
        rows = client.run(_Q, pid=args.patient, dates=args.dates) or []
    finally:
        client.close()

    if not rows:
        print(f"No encounters found for {args.patient} on {args.dates}")
        return

    for r in rows:
        print("=" * 80)
        print(f"DATE  : {r['date']}")
        print(f"EID   : {r['eid']}")
        print(f"TYPE  : {r['encounter_type']}")
        print("-" * 80)
        text = r["text"] or ""
        if len(text) > args.max_chars:
            print(text[: args.max_chars])
            print(f"\n[... truncated, {len(text) - args.max_chars} chars omitted]")
        else:
            print(text)
    print("=" * 80)
    print(f"Total encounters: {len(rows)}")


if __name__ == "__main__":
    main()
