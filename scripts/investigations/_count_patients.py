"""Quick patient and episode counts from Neo4j."""
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

_Q_PATIENTS = "MATCH (p:Patient) RETURN count(p) AS patients"

_Q_EPS = """
MATCH (ep:EpisodeOfCare)
RETURN ep.status AS status, count(*) AS n
ORDER BY n DESC
"""

_Q_DATE_RANGE = """
MATCH (enc:Encounter)
WHERE enc.date IS NOT NULL
RETURN min(enc.date) AS earliest, max(enc.date) AS latest, count(enc) AS n
"""


def main() -> None:
    client = PatientGraphClient()
    try:
        with client.session() as s:
            pat = s.run(_Q_PATIENTS).single()
            print(f"Patients in graph : {pat['patients']}")

            print("\nEpisode status breakdown:")
            total = 0
            for row in s.run(_Q_EPS).data():
                print(f"  {row['n']:4d}  {row['status']}")
                total += row['n']
            print(f"  ----")
            print(f"  {total:4d}  TOTAL")

            dr = s.run(_Q_DATE_RANGE).single()
            print(f"\nEncounter date range:")
            print(f"  Earliest : {dr['earliest']}")
            print(f"  Latest   : {dr['latest']}")
            print(f"  Count    : {dr['n']}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
