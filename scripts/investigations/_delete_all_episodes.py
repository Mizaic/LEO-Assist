"""Delete all EpisodeOfCare nodes from Neo4j.

Run:
    python scripts/investigations/_delete_all_episodes.py
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

_COUNT_Q = "MATCH (ep:EpisodeOfCare) RETURN count(ep) AS n"
_DELETE_Q = (
    "CALL { MATCH (ep:EpisodeOfCare) WITH ep LIMIT 500 DETACH DELETE ep }"
    " IN TRANSACTIONS OF 500 ROWS"
)


def main() -> None:
    client = PatientGraphClient()
    try:
        before = (client.run(_COUNT_Q) or [{}])[0].get("n", "?")
        print(f"EpisodeOfCare nodes before delete: {before}")

        client.run(_DELETE_Q)

        after = (client.run(_COUNT_Q) or [{}])[0].get("n", "?")
        print(f"EpisodeOfCare nodes after delete:  {after}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
