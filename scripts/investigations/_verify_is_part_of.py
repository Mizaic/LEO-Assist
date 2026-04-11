"""Quick verification: count IS_PART_OF edges and show sample."""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient

client = PatientGraphClient()
try:
    total = client.run("MATCH ()-[r:IS_PART_OF]->() RETURN count(r) AS n")[0]["n"]
    episodes = client.run("MATCH (ep:EpisodeOfCare) RETURN count(ep) AS n")[0]["n"]
    by_type = client.run(
        "MATCH ()-[r:IS_PART_OF]->() RETURN r.milestone_type AS t, count(r) AS n ORDER BY n DESC"
    )
    with_links = client.run(
        "MATCH (ep:EpisodeOfCare) WHERE EXISTS { MATCH ()-[:IS_PART_OF]->(ep) } "
        "RETURN count(ep) AS n"
    )[0]["n"]
    print(f"Total IS_PART_OF edges : {total}")
    print(f"EpisodeOfCare nodes    : {episodes}")
    print(f"Episodes with links    : {with_links} / {episodes}")
    print()
    print("Breakdown by milestone_type:")
    for row in by_type:
        print(f"  {row['t'] or '(none)':30s}  {row['n']:>6}")
finally:
    client.close()
