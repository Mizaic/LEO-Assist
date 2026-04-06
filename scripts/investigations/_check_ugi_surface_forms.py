"""Check existing surface forms for the upper GI fast-track referral concept."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402
load_keyvault_secrets()
from neo4j import GraphDatabase  # noqa: E402

uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
pwd = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

_QUERY = """
MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept)
WHERE c.id IN ['276551000000108', '276491000000101']
RETURN sf.normalized AS norm, c.id AS cid
ORDER BY c.id, sf.normalized
"""


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    with driver.session() as s:
        rows = list(s.run(_QUERY))
        prev_cid = None
        for r in rows:
            cid = r["cid"]
            if cid != prev_cid:
                print(f"\n-- Concept {cid} --")
                prev_cid = cid
            print(f"  {r['norm']}")
    driver.close()
    print(f"\nTotal forms: {len(rows)}")


if __name__ == "__main__":
    main()
