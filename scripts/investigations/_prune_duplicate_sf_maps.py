"""
Delete competing MAPS_TO edges where the same SurfaceForm.normalized maps to
multiple concepts. Keep the intended target for NG12 guideline coding.

Pruned in this run:
- chest x ray findings suggestive of mesothelioma: keep 1290960005, drop 60046008
- chest signs compatible with pleural disease: keep 272016000, drop 88075009
"""
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

# (phrase, keep_cid, drop_cid)
PRUNES = [
    ("chest X-ray findings suggestive of mesothelioma", "1290960005", "60046008"),
    ("chest signs compatible with pleural disease", "272016000", "88075009"),
]

_DELETE = """
MATCH (sf:SurfaceForm {normalized: $norm})-[r:MAPS_TO]->(c:Concept {id: $drop})
DELETE r
RETURN count(r) AS deleted
"""


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    with driver.session() as s:
        for phrase, keep, drop in PRUNES:
            norm = normalize_surface(phrase)
            rows = list(s.run(_DELETE, norm=norm, drop=drop))
            n = rows[0]["deleted"] if rows else 0
            print(f"  norm={norm!r} drop={drop} deleted_edges={n} (keep {keep})")
    driver.close()


if __name__ == "__main__":
    main()
