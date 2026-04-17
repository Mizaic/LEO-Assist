"""One-shot helper to print episode metrics. Used to compare pre/post rebuild."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

QUERIES = {
    "total_episodes": """
        MATCH (ep:EpisodeOfCare) RETURN count(ep) AS n
    """,
    "by_status": """
        MATCH (ep:EpisodeOfCare)
        RETURN coalesce(ep.status, '<null>') AS status, count(ep) AS n
        ORDER BY n DESC
    """,
    "auto_closed_breakdown": """
        MATCH (ep:EpisodeOfCare)
        WHERE coalesce(ep.auto_closed, false) = true
        RETURN coalesce(ep.auto_close_reason, '<none>') AS reason, count(ep) AS n
        ORDER BY n DESC
    """,
    "first_seen_persistence": """
        MATCH (ep:EpisodeOfCare)
        RETURN
            sum(CASE WHEN ep.first_seen_date IS NOT NULL THEN 1 ELSE 0 END) AS with_first_seen,
            sum(CASE WHEN ep.first_seen_date IS NULL THEN 1 ELSE 0 END) AS without_first_seen
    """,
    "completed_with_diagnosis_link": """
        MATCH (ep:EpisodeOfCare {status: 'completed'})
        OPTIONAL MATCH (e:Encounter)-[r:IS_PART_OF {milestone: 'diagnosis_confirmed'}]->(ep)
        RETURN
            count(DISTINCT ep) AS completed_total,
            count(DISTINCT CASE WHEN r IS NOT NULL THEN ep END) AS completed_with_diag
    """,
}


def main() -> None:
    c = PatientGraphClient()
    try:
        for name, q in QUERIES.items():
            print(f"\n--- {name} ---")
            for row in c.run(q):
                print("  ", dict(row))
    finally:
        c.close()


if __name__ == "__main__":
    main()
