"""Find the most common unresolved SNOMED concept IDs in completed episodes."""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient

client = PatientGraphClient()
try:
    # Find concept IDs where name is just a number (unresolved)
    # in completed episodes tagged 'unknown'
    print("=== Unresolved concept IDs in 'unknown' completed episodes ===")
    rows = client.run("""
        MATCH (ep:EpisodeOfCare)
        WHERE ep.status = 'completed'
          AND ep.cancer_type = 'unknown'
        MATCH (enc:Encounter)-[:IS_PART_OF]->(ep)
        MATCH (enc)-[:DOCUMENTS]->(c)
        WHERE c.name =~ '^[0-9]+$'
        RETURN c.conceptId AS concept_id, c.name AS raw_name,
               count(DISTINCT ep) AS episode_count
        ORDER BY episode_count DESC
        LIMIT 30
    """)
    for r in rows:
        print(
            f"  {r['concept_id']}  raw_name={r['raw_name']}  episodes={r['episode_count']}"
        )

    # Also show resolved concept names for completed 'unknown' episodes
    print("\n=== Resolved names in 'unknown' completed episodes ===")
    rows2 = client.run("""
        MATCH (ep:EpisodeOfCare)
        WHERE ep.status = 'completed'
          AND ep.cancer_type = 'unknown'
        MATCH (enc:Encounter)-[:IS_PART_OF]->(ep)
        MATCH (enc)-[:DOCUMENTS]->(c)
        WHERE NOT c.name =~ '^[0-9]+$'
          AND c.name IS NOT NULL
        RETURN c.conceptId AS concept_id, c.name AS concept_name,
               count(DISTINCT ep) AS episode_count
        ORDER BY episode_count DESC
        LIMIT 30
    """)
    for r in rows2:
        print(
            f"  {r['concept_id']}  {r['concept_name']}  episodes={r['episode_count']}"
        )
finally:
    client.close()
