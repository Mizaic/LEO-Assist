"""Debug why the encounter concept query returns 0 results."""

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

from libs.neo4j_client.client import KnowledgeGraphClient

kg = KnowledgeGraphClient()
try:
    # Basic: any DOCUMENTS relationship at all?
    r1 = kg.run("MATCH (e:Encounter)-[:DOCUMENTS]->(c) RETURN count(*) AS cnt LIMIT 1")
    print("DOCUMENTS relationships:", r1)

    # Any nodes with conceptId?
    r2 = kg.run(
        "MATCH (c) WHERE c.conceptId IS NOT NULL RETURN labels(c)[0] AS lbl, count(*) AS cnt LIMIT 10"
    )
    print("Nodes with conceptId:", r2)

    # Sample of what Encounter DOCUMENTS to
    r3 = kg.run(
        "MATCH (e:Encounter)-[:DOCUMENTS]->(c) RETURN labels(c) AS lbls, c.conceptId AS cid, c.name AS name LIMIT 5"
    )
    print("Sample encounter docs:")
    for r in r3 or []:
        print(f"  {r['lbls']} conceptId={r['cid']} name={r['name']}")

    # Try the filter explicitly
    r4 = kg.run("""
    MATCH (e:Encounter)-[:DOCUMENTS]->(c)
    WHERE c.conceptId IS NOT NULL
    RETURN count(*) AS cnt
    """)
    print("With conceptId IS NOT NULL:", r4)

    # Without the NOT labels filter
    r5 = kg.run("""
    MATCH (e:Encounter)-[:DOCUMENTS]->(c)
    RETURN DISTINCT toString(c.conceptId) AS cid, count(e) AS cnt
    ORDER BY cnt DESC LIMIT 10
    """)
    print("Distinct concept IDs (no filter):")
    for r in r5 or []:
        print(f"  cid={r['cid']}  cnt={r['cnt']}")

finally:
    kg.close()
