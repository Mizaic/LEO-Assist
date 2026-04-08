"""Verify patient count vs episode count."""
from __future__ import annotations
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from libs.neo4j_client.client import PatientGraphClient


def main() -> None:
    c = PatientGraphClient()
    try:
        rows = c.run("""
            MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
            RETURN toString(p.id) AS patient_id, count(ep) AS episode_count
            ORDER BY episode_count DESC
        """)

        total_patients = len(rows)
        total_episodes = sum(r["episode_count"] for r in rows)
        dist = Counter(r["episode_count"] for r in rows)

        print(f"Unique patients with episodes : {total_patients}")
        print(f"Total referral pathways       : {total_episodes}")
        print(f"Average episodes per patient  : {total_episodes/total_patients:.1f}")
        print()
        print("Episodes per patient distribution:")
        for n in sorted(dist):
            print(f"  {n} episode(s): {dist[n]:3d} patients")
        print()
        print("Patients with most episodes (top 10):")
        for r in rows[:10]:
            print(f"  {r['patient_id']}  ->  {r['episode_count']} episodes")
    finally:
        c.close()


if __name__ == "__main__":
    main()
