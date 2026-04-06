"""Inventory and optionally clear TrainingCandidate and GoldLabel from Knowledge Graph."""
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

client = KnowledgeGraphClient()
with client.session() as s:

    print("=== TrainingCandidate ===")
    rows = [dict(x) for x in s.run("""
        MATCH (c:TrainingCandidate)
        RETURN coalesce(c.status, '?')  AS status,
               coalesce(c.source, '?')  AS source,
               count(*)                 AS n
        ORDER BY source, status
    """)]
    for row in rows:
        print(f"  source={str(row['source']):20s} status={str(row['status']):15s} n={row['n']}")
    if not rows:
        print("  (none)")

    print("\n=== GoldLabel ===")
    rows = [dict(x) for x in s.run("""
        MATCH (g:GoldLabel)
        RETURN coalesce(g.source, '?')      AS source,
               coalesce(g.verified, false)  AS verified,
               g.entities_json IS NOT NULL  AS has_entities,
               count(*)                     AS n
        ORDER BY source, verified
    """)]
    for row in rows:
        print(f"  source={str(row['source']):20s} verified={str(row['verified']):6s} "
              f"has_entities={str(row['has_entities']):6s} n={row['n']}")
    if not rows:
        print("  (none)")

    print("\n=== All KG node labels ===")
    rows = [dict(x) for x in s.run("CALL db.labels() YIELD label RETURN label ORDER BY label")]
    for row in rows:
        print(f"  {row['label']}")

client.close()
