"""Print all MAPS_TO targets for specific normalized surface forms."""

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
from libs.terminology.surface_normalize import normalize_surface  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
pwd = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

_TERMS = [
    "chest x ray findings suggestive of mesothelioma",
    "chest signs compatible with pleural disease",
]

_Q = """
MATCH (sf:SurfaceForm {normalized: $n})-[:MAPS_TO]->(c:Concept)
RETURN sf.form AS form, c.id AS cid, c.fsn AS fsn
"""


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    with driver.session() as s:
        for t in _TERMS:
            n = normalize_surface(t)
            print(f"\n{n!r}")
            rows = list(s.run(_Q, n=n))
            if not rows:
                print("  (no rows)")
                continue
            for r in rows:
                print(f"  {r['cid']} | {r['fsn'][:60]} | form={r['form']!r}")
    driver.close()


if __name__ == "__main__":
    main()
