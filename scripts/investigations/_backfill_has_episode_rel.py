"""
Backfill HAS_EPISODE_OF_CARE relationships for all existing EpisodeOfCare nodes.

The episode_builder now creates this relationship automatically, but existing
episodes built before this fix are missing it. Run once after the fix.
"""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()
from libs.neo4j_client.client import PatientGraphClient

Q_COUNT_MISSING = """
MATCH (ep:EpisodeOfCare)
WHERE ep.patient_id IS NOT NULL
  AND NOT EXISTS { MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep) }
RETURN count(ep) AS n
"""

Q_BACKFILL = """
CALL {
    MATCH (ep:EpisodeOfCare)
    WHERE ep.patient_id IS NOT NULL
      AND NOT EXISTS { MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep) }
    WITH ep LIMIT 500
    MATCH (p:Patient) WHERE toString(p.id) = ep.patient_id
    MERGE (p)-[:HAS_EPISODE_OF_CARE]->(ep)
    RETURN count(*) AS created
} IN TRANSACTIONS OF 500 ROWS
RETURN sum(created) AS total_created
"""

Q_VERIFY = """
MATCH (ep:EpisodeOfCare)
WHERE ep.patient_id IS NOT NULL
OPTIONAL MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep)
RETURN
    count(ep) AS total_episodes,
    sum(CASE WHEN p IS NOT NULL THEN 1 ELSE 0 END) AS linked,
    sum(CASE WHEN p IS NULL THEN 1 ELSE 0 END) AS unlinked
"""


def main() -> None:
    c = PatientGraphClient()
    try:
        missing = c.run(Q_COUNT_MISSING)[0]["n"]
        print(f"Episodes missing HAS_EPISODE_OF_CARE: {missing}")

        if missing == 0:
            print("Nothing to backfill.")
        else:
            print(f"Creating {missing} relationships...")
            result = c.run(Q_BACKFILL)
            created = result[0]["total_created"] if result else "?"
            print(f"Created: {created}")

        verify = c.run(Q_VERIFY)[0]
        print(f"\nVerification:")
        print(f"  Total episodes : {verify['total_episodes']}")
        print(f"  Linked         : {verify['linked']}")
        print(f"  Unlinked       : {verify['unlinked']}")

    finally:
        c.close()


if __name__ == "__main__":
    main()
